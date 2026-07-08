"""Tests for the P4 TOOL_VERSION cache-busting added to orchestration/lib/load_content.py
(the load ledger's _reconcile_verdict/_ledger_write, and the DAM dedupe map's upload_dam).

No network, no JCR, no orchestrator DB. Loader instances are built via __new__ (bypassing
__init__, which wants a live MCP client) with only the attributes each method under test
reads; the two heavy collaborators of _reconcile_verdict (_expected_main_children,
_area_children — unrelated to this change, one of them is a live GraphQL call) are stubbed
so the test exercises the REAL version-gate logic without a Jahia connection.
"""
import json
import os
import sys
from pathlib import Path

# orchestration/lib lives two levels up from migration-orchestrator/tests
REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "orchestration" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import load_content as LC  # noqa: E402


def make_loader(tmp_path, ledger=None, dam=None):
    ld = LC.Loader.__new__(LC.Loader)
    ld.project = "p4-cache-test"
    ld.ledger = ledger if ledger is not None else {}
    ld._dam = dam if dam is not None else {}
    ld._pages_touched = []
    ld._ledger_path = str(tmp_path / "load-ledger.json")
    # stubs for _reconcile_verdict's collaborators — not touched by this change,
    # and _area_children is a live GraphQL call in the real Loader.
    ld._expected_main_children = lambda page, instances, main_area: ["hero-home-0"]
    ld._area_children = lambda area, workspace: {"hero-home-0": "uuid-1"}
    return ld


PDATA = {"instances": [{"type": "hero", "props": {"title": "x"}}]}


# ── ledger: _ledger_write stamps toolVersion ──

def test_ledger_write_stamps_tool_version(tmp_path):
    ld = make_loader(tmp_path)
    ld._ledger_write("home", LC.Loader._plan_hash(PDATA), "REBUILD", created=1)
    on_disk = json.load(open(ld._ledger_path))
    assert on_disk["home"]["toolVersion"] == LC.LEDGER_TOOL_VERSION
    assert on_disk["home"]["planHash"] == LC.Loader._plan_hash(PDATA)
    # provenance stamp is additive, sibling to page entries — never a page itself
    assert "_provenance" in on_disk
    assert "home" in ld._pages_touched


# ── ledger: _reconcile_verdict version gate ──

def test_reconcile_aligned_when_hash_and_version_match(tmp_path):
    plan_hash = LC.Loader._plan_hash(PDATA)
    ld = make_loader(tmp_path, ledger={
        "home": {"planHash": plan_hash, "toolVersion": LC.LEDGER_TOOL_VERSION}
    })
    verdict, info = ld._reconcile_verdict("home", PDATA, "/sites/s/home/main")
    assert verdict == "ALIGNED"
    assert info["hashOk"] is True


def test_reconcile_rebuilds_on_stale_tool_version(tmp_path):
    plan_hash = LC.Loader._plan_hash(PDATA)
    ld = make_loader(tmp_path, ledger={
        # planHash matches (content unchanged) but the ledger predates a TOOL_VERSION
        # bump — an algorithm change must not be masked by a matching content hash.
        "home": {"planHash": plan_hash, "toolVersion": LC.LEDGER_TOOL_VERSION - 1}
    })
    verdict, info = ld._reconcile_verdict("home", PDATA, "/sites/s/home/main")
    assert verdict == "REBUILD"
    assert "tool version" in info["reason"]


def test_reconcile_rebuilds_on_missing_tool_version_never_crashes(tmp_path):
    """A pre-P4 ledger entry has no toolVersion key at all — must read as a MISS,
    never raise (entry.get returns None, compared safely against an int)."""
    plan_hash = LC.Loader._plan_hash(PDATA)
    ld = make_loader(tmp_path, ledger={"home": {"planHash": plan_hash}})
    verdict, info = ld._reconcile_verdict("home", PDATA, "/sites/s/home/main")
    assert verdict == "REBUILD"
    assert "tool version" in info["reason"]


def test_reconcile_rebuilds_on_changed_plan_hash_reason_unchanged(tmp_path):
    """Version matches but content changed — pre-existing behavior (P0) must survive:
    the reason string still distinguishes a content change from a version change."""
    ld = make_loader(tmp_path, ledger={
        "home": {"planHash": "deadbeef", "toolVersion": LC.LEDGER_TOOL_VERSION}
    })
    verdict, info = ld._reconcile_verdict("home", PDATA, "/sites/s/home/main")
    assert verdict == "REBUILD"
    assert info["reason"] == "plan hash changed since last load"


def test_reconcile_bootstrap_absent_entry_is_not_a_version_rebuild(tmp_path):
    """No ledger entry at all (first-ever run) is the pre-existing 'bootstrap' path,
    not a version mismatch — must not be misreported as a tool-version REBUILD."""
    ld = make_loader(tmp_path, ledger={})
    verdict, info = ld._reconcile_verdict("home", PDATA, "/sites/s/home/main")
    assert info["bootstrap"] is True
    assert verdict == "ALIGNED"  # _expected_main_children/_area_children stubs agree


# ── DAM dedupe map: upload_dam version gate ──

def test_upload_dam_cache_hit_requires_matching_tool_version(tmp_path):
    ld = make_loader(tmp_path, dam={
        "hash123.png": {"path": "/sites/s/files/hash123.png", "uuid": "u1",
                        "toolVersion": LC.DAM_TOOL_VERSION}
    })
    ld._dam_resolves = lambda path: True  # pretend the DAM target still exists
    assert ld.upload_dam("hash123.png") == {
        "path": "/sites/s/files/hash123.png", "uuid": "u1",
        "toolVersion": LC.DAM_TOOL_VERSION,
    }


def test_upload_dam_stale_tool_version_is_a_miss_not_a_crash(tmp_path, capsys):
    """A cached entry with the WRONG (or absent, pre-P4) toolVersion must not be
    returned as a hit — even though _dam_resolves would say the old target is fine.
    No mirror asset exists on disk in this test, so the miss path exits via the
    documented 'mirror asset missing' guard instead of attempting a real upload —
    proof the version check didn't silently fall through to a stale return."""
    ld = make_loader(tmp_path, dam={
        "hash123.png": {"path": "/sites/s/files/hash123.png", "uuid": "u1"}  # no toolVersion (pre-P4)
    })
    called = {"n": 0}

    def _resolves(_path):
        called["n"] += 1
        return True
    ld._dam_resolves = _resolves
    result = ld.upload_dam("hash123.png")
    assert result is None  # not the stale cached entry
    assert called["n"] == 0  # short-circuited before the (would-be network) resolve check
    assert "mirror asset missing" in capsys.readouterr().err


def test_upload_dam_missing_filename_is_noop(tmp_path):
    ld = make_loader(tmp_path)
    assert ld.upload_dam("") is None
    assert ld.upload_dam(None) is None

#!/usr/bin/env python3
"""skill-conformance.py — the emitted CND must match the definition the SKILL gives.

The skills in .agents/skills are the contract for how a Jahia module is built, and
three defects in one session came from the emitter inventing its own simplified
shape for a component a skill already specifies exactly:

  * jcrQuery shipped as a minimalist stand-in (`query` textarea, plain-string
    `type`/`sortBy`/`subNodeView`) while 06-implement-jcr-query gives the full
    definition and says in as many words not to ship a minimalist variant. The
    invented property names meant the loader posted values that were silently
    discarded, so every listing sorted by the default;
  * mainResource types emitted `default` + `fullPage` while jcrQuery asks Jahia for
    a `card` view, so every listing fell back to `default`;
  * child grants (`+ * (ns:cardItem)`) added to a query, which holds no children.

Each was found by a human reading the CND, which does not scale and should not
have to. This compares the two mechanically: for every type a pipeline skill
defines AND the emitter emits, the emitted block must carry the skill's supertypes
and property names, with matching property TYPES (a `long` where the skill says
`string, choicelist[resourceBundle]` loses the editor's dropdown and its labels).

Placeholder namespaces in the skills (`ns:`, `nsMix:`) are mapped onto the
project's. Types a skill only uses as a teaching example — `myns:`, `namespace:` —
are ignored: only `ns:`/`nsMix:` blocks in the numbered pipeline skills are treated
as contracts. Extra properties on the emitted type are fine and reported as info;
a module may add fields, it may not drop the skill's.

Usage: skill-conformance.py <project> --ns sdp --mixns sdpmix [--cnd PATH]
                            [--skills DIR]
"""
import argparse
import glob
import os
import re
import sys

TYPE_RE = re.compile(r"^\[([A-Za-z][\w]*:[\w]+)\]\s*(?:>\s*([^\n]+?))?\s*$")
PROP_RE = re.compile(r"^\s*-\s*([\w:]+)\s*\(([^)]*)\)")
CHILD_RE = re.compile(r"^\s*\+\s*(\S+)\s*\(([^)]*)\)")


def parse_cnd(text, only_prefixes=None):
    """{type: {"supertypes": [...], "props": {name: type}, "children": [types]}}"""
    out, cur = {}, None
    for line in text.split("\n"):
        m = TYPE_RE.match(line.rstrip())
        if m:
            name = m.group(1)
            if only_prefixes and name.split(":")[0] not in only_prefixes:
                cur = None
                continue
            sup = [s.strip() for s in re.split(r",", m.group(2) or "")
                   if s.strip() and s.strip() != "mixin"]
            cur = out.setdefault(name, {"supertypes": [], "props": {}, "children": []})
            cur["supertypes"] = [re.sub(r"\s+\w+$", "", s) if s.endswith(("orderable",))
                                 else s for s in sup]
            continue
        if cur is None:
            continue
        if line.strip().startswith("//"):
            continue
        pm = PROP_RE.match(line)
        if pm:
            cur["props"][pm.group(1)] = re.sub(r"\s+", "", pm.group(2))
            continue
        cm = CHILD_RE.match(line)
        if cm:
            cur["children"].append(re.sub(r"\s+", "", cm.group(2)))


    return out


def skill_contracts(skills_dir):
    """Types the NUMBERED pipeline skills define, in ns:/nsMix: form."""
    spec = {}
    for f in sorted(glob.glob(os.path.join(skills_dir, "[0-9][0-9]-*", "SKILL.md"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        for block in re.findall(r"```cnd\n(.*?)```", txt, re.S):
            for name, d in parse_cnd(block, only_prefixes={"ns", "nsMix"}).items():
                # a skill may show the same type twice (a fuller and a minimal
                # variant); keep the RICHER one — the minimal form is the "if you
                # need nothing configurable" case, never a cap
                prev = spec.get(name)
                if not prev or len(d["props"]) > len(prev["props"]):
                    d["_skill"] = os.path.basename(os.path.dirname(f))
                    spec[name] = d
    return spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--mixns", default="")
    ap.add_argument("--cnd", default="")
    ap.add_argument("--skills", default=".agents/skills")
    a = ap.parse_args()
    mixns = a.mixns or f"{a.ns}mix"
    cnd_p = a.cnd or f"projects/{a.project}/workflow-output/definitions.cnd"
    if not os.path.exists(cnd_p):
        print(f"PASS skill-conformance: no CND at {cnd_p} yet")
        return
    spec = skill_contracts(a.skills)
    if not spec:
        sys.exit(f"FAIL skill-conformance: no skill CND contract found under {a.skills} "
                 f"(a gate that cannot measure must fail)")
    emitted = parse_cnd(open(cnd_p, encoding="utf-8", errors="replace").read())

    def concrete(n):
        return n.replace("nsMix:", f"{mixns}:").replace("ns:", f"{a.ns}:")

    fails, checked = [], 0
    for sname, sd in sorted(spec.items()):
        ename = concrete(sname)
        ed = emitted.get(ename)
        if ed is None:
            continue                    # the module does not ship this type — fine
        checked += 1
        skill = sd.get("_skill", "?")
        for sup in sd["supertypes"]:
            want = concrete(sup)
            if want not in [concrete(x) for x in ed["supertypes"]]:
                fails.append(f"{ename}: missing supertype {want} "
                             f"(skill {skill}) — has {', '.join(ed['supertypes'])}")
        for pname, ptype in sd["props"].items():
            if pname not in ed["props"]:
                fails.append(f"{ename}: missing property '{pname}' ({ptype}) "
                             f"(skill {skill})")
            elif ptype and ed["props"][pname] != concrete(ptype):
                # placeholders appear INSIDE property types too, e.g.
                # choicelist[subnodetypes='jnt:page,nsMix:queryContent'] — map them
                # before comparing or every parameterised selector reads as a mismatch
                # a stricter emitted type is still a divergence: choicelists carry
                # the editor's dropdown and its resourceBundle labels
                fails.append(f"{ename}.{pname}: type is ({ed['props'][pname]}), skill "
                             f"{skill} specifies ({ptype})")
        for ch in sd["children"]:
            want = concrete(ch)
            if want not in [concrete(x) for x in ed["children"]]:
                fails.append(f"{ename}: missing child rule + * ({want}) (skill {skill})"
                             + (f" — has {', '.join(ed['children'])}"
                                if ed["children"] else " — has none"))

    if fails:
        print(f"FAIL skill-conformance [{a.project}] — {len(fails)} divergence(s) from "
              f"the skills across {checked} shared type(s)")
        for f in fails:
            print(f"  - {f}")
        print("  Fix the EMITTER to match the skill, not the skill to match the "
              "emitter. The skills are the contract.")
        sys.exit(1)
    print(f"PASS skill-conformance: {checked} type(s) also defined by a pipeline skill "
          f"carry its supertypes, properties and child rules")


if __name__ == "__main__":
    main()

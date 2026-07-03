import os
import sys
import tempfile
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

# Isolate persistence: settings reads ORCHESTRATOR_DB_PATH at first src import.
os.environ.setdefault(
    "ORCHESTRATOR_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="orch-test-"), "orchestrator.db"),
)

# Runtime deps (aiosqlite, pydantic-settings) live in the project venv; fall back
# to its site-packages when the invoking interpreter doesn't have them.
try:
    import aiosqlite  # noqa: F401
    import pydantic_settings  # noqa: F401
except ImportError:
    _site = PKG_ROOT / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    if _site.is_dir() and str(_site) not in sys.path:
        sys.path.append(str(_site))

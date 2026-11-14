import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
# The app bundle is read-only on iOS, so the writable data directory can be
# overridden; the desktop keeps using .private next to the project.
DATA = Path(os.environ.get("CAMPUS_DATA_DIR") or PROJECT / ".private").expanduser()
RUNTIME = DATA / "runtime"
WEB = PROJECT / "web"
MODULES = PROJECT / "modules"
DATA.mkdir(parents=True, exist_ok=True)

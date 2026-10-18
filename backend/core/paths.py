import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("CAMPUS_DATA_DIR", PROJECT / ".private")).resolve()
RUNTIME = DATA / "runtime"
WEB = PROJECT / "web"
MODULES = PROJECT / "modules"
DATA.mkdir(parents=True, exist_ok=True)

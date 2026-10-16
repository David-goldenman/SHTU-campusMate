from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / ".private"
RUNTIME = DATA / "runtime"
WEB = PROJECT / "web"
MODULES = PROJECT / "modules"
DATA.mkdir(parents=True, exist_ok=True)

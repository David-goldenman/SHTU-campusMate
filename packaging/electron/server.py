"""Desktop process owns stdin; closing it requests normal FastAPI shutdown."""
import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn
from backend.main import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--launch-id", required=True)
options = parser.parse_args()
app = create_app(active_port=options.port)
app.state.launch_id = options.launch_id
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=options.port, access_log=False))

def stop_on_close():
    sys.stdin.readline()
    server.should_exit = True

threading.Thread(target=stop_on_close, daemon=True).start()
server.run()


"""Run the module's transport lifecycle regression in the shared check entrypoint."""
import subprocess
import shutil
from pathlib import Path

node = shutil.which('node') or shutil.which('node.exe')
if not node:
    raise RuntimeError('Node.js 22+ is required for the chat session check.')
subprocess.run([node, str(Path(__file__).with_suffix('.mjs'))], check=True)

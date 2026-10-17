"""Keep course recording evidence checks in the shared regression entrypoint."""
import shutil
import subprocess
from pathlib import Path

subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_suffix('.mjs'))], check=True)

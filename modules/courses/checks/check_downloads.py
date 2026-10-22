"""Include browser folder-download behavior in the canonical synthetic checks."""
import shutil
import subprocess
from pathlib import Path

subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_suffix('.mjs'))], check=True)

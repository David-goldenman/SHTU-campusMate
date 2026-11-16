"""Include browser folder-download behavior in the canonical synthetic checks."""
import shutil
import subprocess
from pathlib import Path

subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_suffix('.mjs'))], check=True)
subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_name('check_download_layout.mjs'))], check=True)
subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_name('check_global_downloads.mjs'))], check=True)
subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_name('check_download_auto.mjs'))], check=True)
subprocess.run([shutil.which('node') or 'node', str(Path(__file__).with_name('check_download_background.mjs'))], check=True)

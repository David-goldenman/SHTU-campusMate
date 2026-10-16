"""Browser identity survives ordinary closes; forgetting removes only its profile."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.auth.browser import VerificationBrowser

with tempfile.TemporaryDirectory() as name:
    browser = VerificationBrowser(Path(name))
    browser._run = lambda *args, **kwargs: {'closed': True}
    profile = browser._directory('ids')
    profile.mkdir()
    marker = profile / 'trusted-device'
    marker.write_text('synthetic browser identity')
    sibling = browser._directory('coremail')
    sibling.mkdir()
    browser.close('ids')
    browser.close_all()
    assert marker.read_text() == 'synthetic browser identity'
    browser.forget('ids')
    assert not profile.exists() and sibling.is_dir()
print('auth browser: persistent identity and explicit account removal passed')

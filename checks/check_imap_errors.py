"""Network failures must never invalidate saved IMAP credentials."""
import imaplib
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.auth import AuthService, ImapUnavailable, LoginRequired
from backend.services.auth import imap as access
from checks.module_support import Memory, sandbox


def expect(kind, call):
    try:
        call()
    except kind:
        return
    raise AssertionError('Expected ' + kind.__name__)


with patch.object(access.imaplib, 'IMAP4_SSL', side_effect=OSError('synthetic offline')):
    expect(ImapUnavailable, lambda: access.connect('fixture', 'synthetic-password'))
for error, kind in ((imaplib.IMAP4.abort('closed'), ImapUnavailable),
                    (OSError('offline'), ImapUnavailable),
                    (imaplib.IMAP4.error('[UNAVAILABLE] server busy'), ImapUnavailable),
                    (imaplib.IMAP4.error('LOGIN command error: BAD'), ImapUnavailable),
                    (imaplib.IMAP4.error('[AUTHENTICATIONFAILED] Invalid credentials'), LoginRequired)):
    mailbox = Mock()
    mailbox.login.side_effect = error
    with patch.object(access.imaplib, 'IMAP4_SSL', return_value=mailbox):
        expect(kind, lambda: access.connect('fixture', 'synthetic-password'))
    mailbox.logout.assert_called_once()
mailbox = Mock()
mailbox.select.return_value = ('NO', [])
with patch.object(access.imaplib, 'IMAP4_SSL', return_value=mailbox):
    expect(ImapUnavailable, lambda: access.connect('fixture', 'synthetic-password'))
mailbox.logout.assert_called_once()

with sandbox('imap-errors') as context:
    vault = Memory()
    vault.transaction = nullcontext
    vault.save('auth:imap:coremail', {'username': 'fixture@example.edu', 'password': 'synthetic-password'})
    service = AuthService(vault, context.store, context.data_dir)
    try:
        with patch.object(access, 'connect', side_effect=ImapUnavailable()):
            def connect():
                with service.imap_connection():
                    pass
            expect(ImapUnavailable, connect)
        assert service.get_status('coremail')['status'] == 'error'
        assert vault.get('auth:imap:coremail')['password'] == 'synthetic-password'
        mailbox = Mock()
        with patch.object(access, 'connect', return_value=mailbox):
            try:
                with service.imap_connection():
                    context.store.write('auth:session_revision:coremail', 'new-session')
                    service._record('coremail', 'ready', message='new credentials verified')
                    raise LoginRequired('old connection rejected')
            except LoginRequired:
                pass
        assert service.get_status('coremail')['status'] == 'ready'
        mailbox.logout.assert_called_once()
    finally:
        service.close()
print('imap errors: transport/abort/server-busy vs password rejection, preserved credentials and stale-session status passed')

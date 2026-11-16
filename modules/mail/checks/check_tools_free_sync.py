"""Tools-free mail review sees the newly published inbox, using synthetic data."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

package = load('mail')


class InlineThread:
    def __init__(self, *, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def inbox(mailbox, previous):
    return {'messages': [{'id': 'mail:1', 'source': 'mail', 'source_id': '1',
                          'title': 'Synthetic notice', 'sender': '', 'received_at': None,
                          'unread': True, 'url': 'https://example.invalid/', 'body_text': ''}],
            'metadata': {'uid_validity': '1', 'transport': 'imap'}, 'issues': []}


for tools, expected in ((False, ['mail:1']), (True, [])):
    with sandbox('mail') as context, patch.object(package, 'imap_inbox', inbox):
        context.auth.mailbox = object()
        context.ai.supports_tools = tools
        package.create_router(context)
        source, reviewed = package._source, []

        def review(identity, origin, force=False):
            snapshot = source.snapshot()
            assert snapshot['status'] == 'ready'
            assert snapshot['data']['messages'][0]['id'] == identity
            reviewed.append(identity)

        try:
            with patch.object(package.threading, 'Thread', InlineThread), \
                 patch.object(package.time, 'sleep'), \
                 patch.object(package._intelligence, 'review', review):
                source.run()
            assert reviewed == expected, 'Tools-free review must start after the new inbox is published'
        finally:
            package.stop(context)

print('tools-free mail sync: review after publication; native tool path unchanged; synthetic only')

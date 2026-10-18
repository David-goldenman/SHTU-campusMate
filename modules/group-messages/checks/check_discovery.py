"""Synthetic Weixin process discovery; never read personal process memory."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

process = load('group-messages').wechat.process


def check():
    executable = '"C:/Program Files/Tencent/Weixin/Weixin.exe"'
    rows = [
        {'ProcessId': 101, 'CommandLine': executable, 'WorkingSetSize': 1024 * 100},
        {'ProcessId': 102, 'CommandLine': executable + ' --multi-instance', 'WorkingSetSize': 1024 * 80},
        *({'ProcessId': 110 + index, 'CommandLine': executable + ' ' + flag, 'WorkingSetSize': 1024 * 200}
          for index, flag in enumerate(('--type=wxocr', '--type=wxutility', '--type=wxpublic',
                                        '--type=xplayer', '--type renderer', '"--type=future-helper"',
                                        '"--type" "wxocr"'))),
        {'ProcessId': 201, 'CommandLine': executable, 'WorkingSetSize': 1024 * 300},
        {'ProcessId': 202, 'CommandLine': executable, 'WorkingSetSize': 1024 * 300},
        {'ProcessId': 203, 'CommandLine': None, 'WorkingSetSize': 1024 * 300},
    ]
    kernel = SimpleNamespace(CloseHandle=Mock())

    def open_process(pid, *, memory):
        assert memory is False, 'Detection must not read process memory'
        if pid in (201, 202):  # Another Windows user, or exited since enumeration.
            raise process.NativeError('wechat_live_process_invalid')
        return kernel, pid

    def enumerate_processes(command, **options):
        assert options['timeout'] <= 10
        return SimpleNamespace(stdout=json.dumps(rows), returncode=0)

    with patch.object(process, 'available', return_value=True), \
         patch.object(process.subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
         patch.object(process.subprocess, 'run', side_effect=enumerate_processes) as query, \
         patch.object(process, 'open_weixin', side_effect=open_process) as opened:
        found = process.discover_processes()
        assert [row['pid'] for row in found] == [101, 102], 'Only genuine main instances should be listed'
        assert all(set(row) == {'pid', 'name', 'memory_kb'} for row in found), 'Command lines stay local'
        assert kernel.CloseHandle.call_count == 2
        assert {call.args[0] for call in opened.call_args_list} == {101, 102, 201, 202}
        assert query.call_count == 1
        rows.clear()
        assert process.discover_processes() == []
    with patch.object(process, 'available', return_value=False), patch.object(process.subprocess, 'run') as query:
        assert process.discover_processes() == []
        query.assert_not_called()
    print('PASS: main instances retained, helper roles excluded, ownership/exit checks and metadata-only discovery')


if __name__ == '__main__':
    check()

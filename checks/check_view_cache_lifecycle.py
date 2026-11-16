"""Browser-only cache channels must not keep non-browser consumers alive."""
from pathlib import Path
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]


def main():
    script = "globalThis.window = new EventTarget(); await import('./web/shared.js'); console.log('cache import completed');"
    try:
        result = subprocess.run([shutil.which('node'), '--input-type=module', '-e', script],
                                cwd=PROJECT, capture_output=True, text=True, timeout=4)
    except subprocess.TimeoutExpired:
        raise AssertionError('Importing the browser cache in a non-browser host must not retain a native channel') from None
    assert result.returncode == 0, result.stderr
    assert 'cache import completed' in result.stdout
    browser = """
import assert from 'node:assert/strict';
const sent = [];
globalThis.window = {BroadcastChannel: class {
  constructor(name) { assert.equal(name, 'campus.view-cache'); }
  postMessage(value) { sent.push(value); }
}};
const cache = await import('./web/view-cache.js');
cache.invalidateViews();
cache.invalidateViews(false);
assert.deepEqual(sent, ['invalidate']);
"""
    result = subprocess.run([shutil.which('node'), '--input-type=module', '-e', browser],
                            cwd=PROJECT, capture_output=True, text=True, timeout=4)
    assert result.returncode == 0, result.stderr
    print('view cache lifecycle: non-browser imports exit without a retained channel')


if __name__ == '__main__':
    main()

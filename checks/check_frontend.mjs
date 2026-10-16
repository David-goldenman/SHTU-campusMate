import assert from 'node:assert/strict';
import {useStyle, escape} from '../web/shared.js';

const mounted = new Set();
globalThis.document = {
  createElement:() => ({remove() { mounted.delete(this); }}),
  head:{append(node) { mounted.add(node); }},
};
const first = new AbortController(), sibling = new AbortController();
const cleanup = useStyle('/first.css',first.signal);
useStyle('/sibling.css',sibling.signal);
assert.equal(mounted.size,2);
first.abort();
assert.equal(mounted.size,1);
cleanup(); cleanup();
assert.equal(mounted.size,1);
sibling.abort();
assert.equal(mounted.size,0);
useStyle('/already-aborted.css',first.signal);
assert.equal(mounted.size,0);
assert.equal(escape('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
console.log('frontend: independent abort cleanup, idempotent style removal, pre-aborted mounts and untrusted navigation text passed');

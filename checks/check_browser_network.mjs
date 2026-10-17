import assert from 'node:assert/strict';
import {proxyArguments} from '../scripts/browser-network.mjs';

for (const url of ['https://shanghaitech.edu.cn/', 'https://ids.shanghaitech.edu.cn/authserver/login',
  'https://elearning.shanghaitech.edu.cn:8443/', 'https://elrc.shanghaitech.edu.cn/',
  'https://mail.shanghaitech.edu.cn/coremail/', 'https://faculty.sist.shanghaitech.edu.cn/']) {
  assert.deepEqual(proxyArguments(url), ['--no-proxy-server']);
}
for (const url of ['https://www.gradescope.com/login', 'https://piazza.com/class',
  'https://notshanghaitech.edu.cn/', 'https://shanghaitech.edu.cn.example.org/',
  'https://shanghaitech.edu.cn@example.org/']) {
  assert.deepEqual(proxyArguments(url), []);
}
console.log('browser network: school-only direct routing, external providers and lookalike domains preserved');

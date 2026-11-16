import assert from 'node:assert/strict';
import {renderRuntime, diagnosticSummary} from '../web/runtime-status.js';

const module = {id:'synthetic',name:'合成来源',status:'ready',runtime:{
  active_requests:0,pending_calls:0,last_success_at:'2026-10-28T01:00:00Z',
  last_request:{status:200,duration_ms:2},workers:[],
  sources:{sync:{status:'error',phase:'sync',code:'source_parse_error',operation_id:'0123456789ab',
    request_id:'abcdef123456',cached_at:'2026-10-27T01:00:00Z',last_success_at:'2026-10-27T01:00:00Z',
    action:'检查来源状态后重试',message:'private mail content must not be copied',
    account:'private-account',cookie:'private-cookie'}},
}};
const html=renderRuntime(module.runtime);
assert.match(html,/同步失败/);
assert.match(html,/最近同步成功/);
assert.match(html,/缓存/);
assert.match(html,/0123456789ab/);
assert(!html.includes('private mail content'));
const summary=diagnosticSummary([module]);
for(const expected of ['synthetic','source_parse_error','0123456789ab','abcdef123456'])assert(summary.includes(expected));
for(const secret of ['private mail content','private-account','private-cookie'])assert(!summary.includes(secret));
module.runtime.sources.sync.status='partial';
assert.match(renderRuntime(module.runtime),/部分更新/);
module.runtime.sources.sync.status='cancelled';
assert.match(renderRuntime(module.runtime),/已取消/);
module.runtime.sources.sync.action='<img onerror=alert(1)>';
assert(!renderRuntime(module.runtime).includes('<img'));
assert.doesNotThrow(()=>renderRuntime({workers:[]}));
assert.equal(renderRuntime(null),'');
console.log('runtime status: successful HTTP polling cannot conceal source failure; diagnostic copy uses safe metadata only');

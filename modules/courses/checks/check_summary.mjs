import assert from 'node:assert/strict';
import {courseSummaries, termLabel} from '../web/summary.js';

const data = {
  courses:[
    {id:'merged',course_ids:['bb:1','elrc:1','elrc:1'],sources:[{id:'bb:1',source:'blackboard',grades:[{title:'Exam',score:80}]},{id:'elrc:1',source:'elrc'}]},
    {id:'empty',course_ids:['elrc:2'],sources:[{id:'elrc:2',source:'elrc'}]},
    {id:'unlinked',course_ids:['bb:3'],sources:[{id:'bb:3',source:'blackboard'}]},
  ],
  lessons:[{id:'video:1',source:'elrc',course_id:'elrc:1'}],
  materials:[{id:'m:1',source:'blackboard',course_id:'bb:1'},{id:'m:2',source:'elrc',course_id:'elrc:2'}],
  assignments:[
    {id:'a:1',course_id:'bb:1',source:'blackboard',submitted:false,actionable:true},
    {id:'a:2',course_id:'bb:1',source:'blackboard',submitted:null,actionable:true},
    {id:'a:3',course_id:'bb:1',source:'blackboard',submitted:true,actionable:true},
  ],
  metadata:{source_metadata:{elrc:{status:'ready'}}},issues:[],
};
const before = structuredClone(data);
let result = courseSummaries(data);
assert.deepEqual(result.map(item=>item.recording.state),['available','empty','unknown']);
assert.equal(result[0].recording.count,1,'Merged source IDs do not double-count recordings');
assert.deepEqual(result[0].contents.materials.map(item=>item.id),['m:1'],'Course contents remain isolated');
assert.equal(result[0].pending,1,'Only confirmed actionable, unsubmitted work is pending');
assert.equal(result[0].contents.grades[0].source,'blackboard');
assert.deepEqual(data,before,'Snapshot remains unchanged');
const states = structuredClone(data);
states.assignments = [
  ...['not_submitted','draft','exempt','unknown','submitted','needs_grading','graded'].map(state => ({
    id:state, source:'ecourse', course_id:'bb:1', submitted:false, actionable:true, submission_status:state,
  })),
  {id:'explicit-exemption',source:'ecourse',course_id:'bb:1',submitted:false,actionable:true,submission_status:'not_submitted',exempt:true},
  {id:'closed',source:'ecourse',course_id:'bb:1',submitted:false,actionable:false,submission_status:'not_submitted'},
];
assert.equal(courseSummaries(states)[0].pending,2,'Ecourse pending counts match the catalog: unsubmitted/draft only, never exempt, uncertain or completed');
for (const status of ['syncing','partial','error','cached','not_connected','login_required']) {
  data.metadata.source_metadata.elrc.status=status;
  result=courseSummaries(data);
  assert.equal(result[0].recording.state,'available','Positive cached evidence remains visible');
  assert.equal(result[1].recording.state,'unknown',`${status} must not be presented as no recording`);
}
data.metadata.source_metadata.elrc.status='ready';
data.issues=['elrc：录播目录暂时不可读，保留缓存。'];
assert.equal(courseSummaries(data)[1].recording.state,'unknown');
data.issues=['blackboard：资料暂时不可读'];
assert.equal(courseSummaries(data)[1].recording.state,'empty','Unrelated source failures do not hide known recording state');
data.lessons.push({id:'unmatched',source:'elrc',course_id:null});
assert.equal(courseSummaries(data)[1].recording.state,'unknown','Unmatched recordings cannot prove absence');
delete data.metadata.source_metadata.elrc;
assert.equal(courseSummaries(data)[1].recording.state,'unknown');
assert.equal(termLabel('2026-fall'),'2026 年秋季');
assert.equal(termLabel('2026-spring'),'2026 年春季');
assert.equal(termLabel(''),'学期待确认');
assert.deepEqual(courseSummaries({courses:[]}),[]);
console.log('PASS course summaries: merged records, course isolation, pending states, known/empty/unknown recording evidence and source failures');

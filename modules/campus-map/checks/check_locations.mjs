import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {matchLocation, eventTime, shiftDay, validDay, projectCampus} from '../web/locations.js';
const data=JSON.parse(await readFile(new URL('../data/places.json',import.meta.url),'utf8'));
for(const [room,name] of [['信息学院1D-102','信息学院1号楼'],['信息学院2-215','信息学院2号楼'],['信息学院3-101-1','信息学院3号楼'],['生命学院A101','生命学院'],['数学所506','数学科学研究所'],['教学中心203','教学中心'],['图书馆视听鉴赏厅305','图书馆'],['体育馆B107（健美操房）','体育馆'],['图书馆一楼东门电梯口','图书馆'],['H2-101','H2楼,学生科创中心']]) {
  const result=matchLocation(room,data.buildings);assert.equal(result.status,'matched',room);assert.equal(result.buildings[0].name,name);
}
assert.equal(matchLocation('信息学院12-101',data.buildings).status,'unknown');
assert.equal(matchLocation('PH2-101',data.buildings).status,'unknown');
assert.equal(matchLocation('信息学院1或信息学院2',data.buildings).status,'ambiguous');
assert.equal(matchLocation('地下车库',data.buildings).status,'unknown');
assert.equal(matchLocation('',data.buildings).status,'missing');
assert.equal(eventTime({event_type:'deadline',at:'2026-10-20T16:30:00Z'}),'截止 00:30');
assert.equal(eventTime({event_type:'class',period_start:3,period_end:4}),'第 3–4 节 · 钟点待同步');
assert.equal(eventTime({event_type:'exam',source:'eams',at:'2026-10-20T00:00:00+08:00'}),'时间待公布');
assert.equal(eventTime({event_type:'exam',source:'local',at:'2026-10-20T10:00:00+08:00'}),'10:00');
assert.equal(eventTime({all_day:true,at:'2026-10-20T00:00:00+08:00'}),'全天');
assert.equal(eventTime({at:'invalid'}),'时间待定');
assert.equal(shiftDay('2026-12-31',1),'2027-01-01');
assert(!validDay('2026-02-30'));assert(validDay('2028-02-29'));
const map=projectCampus(data);assert(map.width>0&&map.height>0);
for(const b of data.buildings) {assert(b.polygon.length>=3);assert(map.center(b.polygon).every(Number.isFinite));assert(!map.polygon(b.polygon).includes('NaN'));}
assert.equal(new Set(data.buildings.map(b=>b.id)).size,data.buildings.length);
for(const el of data.elevators) assert(data.buildings.some(b=>b.id===el.building_id)&&el.source_url.startsWith('https://'));
console.log('campus-map: explicit room matching, ambiguous/unknown locations, time semantics and map geometry passed');

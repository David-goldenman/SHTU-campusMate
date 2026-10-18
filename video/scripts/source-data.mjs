import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const base='http://127.0.0.1:16666/api/v1';
const get=async path=>{const r=await fetch(base+path);assert(r.ok,path);return r.json();};
const [mail,assignments,index,bootstrap]=await Promise.all(['/modules/mail/snapshot','/modules/assignments/snapshot','/modules/academic-assistant/conversations','/bootstrap'].map(get));
const find=word=>{const item=mail.data.messages.find(x=>x.title.includes(word));assert(item,word);return item;};
const shape=find('当前宏观经济形势'),homework=find('Homework 2 Released'),signal=find('第二次作业已发布'),chip=find('CMOS图像传感器');
let saved=[];
try {
  const selected=index.items.find(x=>x.title.includes('形策'));assert(selected);
  const r=await fetch(base+'/modules/academic-assistant/conversations/'+selected.id+'/select',{method:'POST',headers:{'X-Framework-Token':bootstrap.csrf_token}});assert(r.ok);
  saved=(await r.json()).messages;
} finally {
  if(index.active_id){const restored=await fetch(base+'/modules/academic-assistant/conversations/'+index.active_id+'/select',{method:'POST',headers:{'X-Framework-Token':bootstrap.csrf_token}});assert(restored.ok);}
}
const paragraph=text=>text.replace(/\n+/g,' ').replace(/\s+/g,' ').trim();
const data={
  collected:'2026-10-18',
  notices:[
    {title:shape.title,sender:'人文科学研究院',received_at:shape.received_at,bucket:'focus',category:'形策讲座',summary:'10 月 21 日 18:00，会议中心。本科生签到可计入形策课考勤；今日校园报名截止 17:00。',body:paragraph(shape.body_text),provenance:'本机学校邮箱缓存中的群发原件；正文仅合并换行。'},
    {title:homework.title,sender:'CS100 课程组 · Piazza',received_at:homework.received_at,bucket:'focus',category:'课程作业',summary:'Homework 2 已发布，10 月 22 日 23:59 截止，通过 git 提交至 Gradescope。',body:'Homework 2 于 2026 年 10 月 13 日 20:00 在 Gradescope 开放，截止时间为 10 月 22 日 23:59，通过 git 提交。',provenance:'本机 Piazza 群发邮件；保留标题及作业安排，删去订阅身份和个人信息。'},
    {title:signal.title,sender:'信号与系统课程组 · Blackboard',received_at:signal.received_at,bucket:'focus',category:'课程通知',summary:'第二次作业已发布；10 月 20 日 18:00 截止，须按通知要求手写并上传。',body:paragraph(signal.body_text),provenance:'本机 Blackboard 群发课程通知；发件人改为课程组。'},
    {title:chip.title,sender:'材料器件中心',received_at:chip.received_at,bucket:'recommend',category:'科研讲座',summary:'10 月 21 日 15:30—17:30；10 月 20 日 13:00 前报名，地点由确认邮件通知。',body:'《造芯大讲堂》2026 年第 12 讲：CMOS 图像传感器（CIS）历史演变及未来发展方向。面向对此技术感兴趣的师生及用户。',provenance:'本机群发培训通知，省略电话、二维码与人员联系方式。'},
    {title:'〖第六届人文季〗 一笔一画，无限可能：禅绕画与艺术疗愈',sender:'人文科学研究院',received_at:'2026-09-27T09:00:00+08:00',bucket:'digest',category:'身心关怀 · 已结束',summary:'10 月 10 日 15:00—17:00，图书馆 501。活动已结束，保留摘要供回顾。',body:'学校活动页公布的艺术疗愈体验活动，由张菁主讲，地点为图书馆 501，时间为 2026 年 10 月 10 日 15:00—17:00。',url:'https://www.shanghaitech.edu.cn/2026/0927/c15107a1127674/page.htm',provenance:'学校官方公开活动页。用于展示历史通知摘要；未将此活动声称为心理课程考勤。'},
    {title:'〖人文-心理讲座〗如何理解自己的心理与生活状态',sender:'人文科学研究院',received_at:'2026-03-25T09:00:00+08:00',bucket:'digest',category:'心理讲座 · 已结束',summary:'3 月 28 日 18:00—20:30，图书馆 302。历史活动归入摘要。',body:'学校活动页公布：李煦主讲，2026 年 3 月 28 日 18:00—20:30，图书馆 302。',url:'https://www.shanghaitech.edu.cn/2026/0325/c14749a1120182/page.htm',provenance:'学校官方公开活动页；历史心理讲座示例，发布时间只保留日期。'}
  ],
  assignments:assignments.data.assignments.filter(a=>['HW2_p1','HW2_p2','普物第二次作业','HW1_p1','HW1 Writing'].includes(a.title)).map(a=>({title:a.title,course:a.course_title,source:a.source,due_at:a.due_at})),
  materials:assignments.data.materials.filter(m=>['Book-Introduction to Probability by BT','Homework_2_pdf','Lecture Slides L2','Lecture Slides L3','Signals and systems Chapter 2','HW2'].includes(m.title)).map(m=>({title:m.title,source:m.source})),
  scheduleConversation:saved.map(m=>({role:m.role,text:m.text,...(m.role==='assistant'?{citations:(m.citations||[]).map((c,i)=>({source_id:'public:shape:'+i,record_id:'public:shape',title:c.title,quote:c.quote,kind:'text'})),changes:(m.changes||[]).map(c=>({applied:c.applied,domain:'timetable',action:c.action,before:null,after:{title:c.after.title,event_type:c.after.event_type,starts_at:c.after.starts_at,ends_at:c.after.ends_at,location:c.after.location,notes:c.after.notes},affected_count:1,conflicts:{items:[],complete:true}}))}:{})})),
  demonstration:{date:'2026-10-19T08:20:00+08:00',profile:'合成学生档案；在修课程、完成状态和课表为演示编排',responses:'日程对话取自已保存真实答复；复习和选课为使用真实课程/作业名称编写的演示回复，按原生流式协议重放。'}
};
assert(data.assignments.some(a=>a.title==='HW2_p1'));
assert(data.scheduleConversation.some(m=>m.role==='assistant'&&m.changes.length));
const serialized=JSON.stringify(data,null,2);
assert(!/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(serialized));
assert(!/\/submissions\/\d+/.test(serialized));
await writeFile(fileURLToPath(new URL('../production/source-data.json',import.meta.url)),serialized+'\n');
console.log('Saved '+data.notices.length+' public notices, '+data.assignments.length+' assignment titles, and one redacted saved conversation. Original active conversation restored.');

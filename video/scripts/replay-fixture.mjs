// The base fixture blocks every business API; this layer supplies redacted source material and an NDJSON replay.
export async function installReplayFixture(source,mode,exampleReplies) {
  const offlineFetch=window.fetch, state=window.filmDemo;
  sessionStorage.setItem('campus.opening-line.v1','想法负责仰望星空，日历负责指出：明天早八。');
  const nativeTimeout=window.setTimeout.bind(window),nativeClear=window.clearTimeout.bind(window),polls=new Map();
  window.setTimeout=(callback,ms,...args)=>{if(![5000,6000].includes(ms))return nativeTimeout(callback,ms,...args);const id=nativeTimeout(()=>{},1000000000);polls.set(id,()=>callback(...args));return id;};
  window.clearTimeout=id=>{polls.delete(id);nativeClear(id);};
  state.poll=async()=>{for(const [id,callback] of [...polls]){polls.delete(id);nativeClear(id);await callback();}};
  const OriginalDate=Date, now='2026-10-19T08:20:00+08:00';
  window.Date=class extends OriginalDate {constructor(...args){super(...(args.length?args:[now]));}static now(){return new OriginalDate(now).valueOf();}};
  const at=(day,time='23:59')=>`2026-10-${day}T${time}:00+08:00`;
  const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  const baseline=await(await offlineFetch('/api/v1/modules/courses/snapshot')).json();
  const palette=[0,0,0,2,3,1].map(i=>baseline.data.courses[i].appearance);
  const specs=[['CS100','计算机编程'],['SI140A','面向信息科学的概率论与数理统计'],['EE150','信号与系统'],['PHYS1183','普通物理II'],['GEHA1279','莎士比亚《李尔王》'],['MATH1112','线性代数I']];
  const courses=specs.map(([code,title],i)=>({id:'course:'+i,code,title,term:'2026-2027-1',current:true,appearance:palette[i],course_ids:[`bb:${i}`,`gs:${i}`],sources:['blackboard','gradescope','elrc','piazza'].map(platform=>({id:(platform==='blackboard'?'bb':platform==='gradescope'?'gs':platform)+':'+i,code,title,term:'2026-2027-1',source:platform,url:{blackboard:'https://bb.shanghaitech.edu.cn/',gradescope:'https://www.gradescope.com/',elrc:'https://elrc.shanghaitech.edu.cn/',piazza:'https://piazza.com/'}[platform]}))}));
  const assignments=['HW2_p1','HW2_p2','普物第二次作业','HW1_p1'].map((title,i)=>{
    const real=source.assignments.find(a=>a.title===title),c=i===2?3:0,completed=i>=2;
    return {id:'assignment:'+i,title,source:real.source,course_id:(real.source==='gradescope'?'gs:':'bb:')+c,course_title:courses[c].title,due_at:real.due_at,submitted:completed,submission_status:completed?'submitted':'not_submitted',submission_reason:'演示账号的完成状态',category:completed?'completed':'pending',current:true,pending:!completed,url:real.source==='gradescope'?'https://www.gradescope.com/':'https://bb.shanghaitech.edu.cn/'};
  });
  assignments.splice(2,0,{id:'assignment:signal',title:'HW2',source:'blackboard',course_id:'bb:2',course_title:'信号与系统',due_at:at(20,'18:00'),submitted:false,submission_status:'not_submitted',submission_reason:'演示账号尚未提交',category:'pending',pending:true,current:true,url:'https://bb.shanghaitech.edu.cn/'});
  const materials=source.materials.filter(m=>m.title!=='HW2').map((m,i)=>({id:'material:'+i,title:m.title,source:m.source,course_id:m.title.startsWith('Signals')?'bb:2':'bb:1',url:'https://bb.shanghaitech.edu.cn/',body_text:'课程平台已同步的资料。'}));
  const messages=source.notices.map((m,i)=>({id:'mail:'+i,title:m.title,sender:m.sender,received_at:m.received_at,url:m.url||'https://mail.shanghaitech.edu.cn/',source:'mail',unread:i<4,classification:{bucket:m.bucket,category:m.category,summary:m.summary,reason:i===0?'演示账号仍需完成形策；原文明确本科生签到可计入考勤。':i===4||i===5?'活动已结束，按照当前偏好保留摘要。':'结合在修课程、兴趣和原文内容分类。',by:'agent',review_pending:false,evidence:[{source:'body_text',quote:m.summary}]}}));
  const prefs={degree:'bachelor',year:2,major:'电子信息工程',courses:['CS100','SI140A','EE150'],shape:'required',mental:'required',interests:{research:'follow',clubs:'digest',career:'digest'},requirements:'关注人工智能与机器人讲座；形策和心理活动优先提醒。已经结束的活动保留摘要。'};
  const periods=baseline.data.timetable.length?Array.from({length:10},(_,i)=>({period:i+1,start:['08:15','09:10','10:15','11:10','13:00','13:55','15:00','15:55','18:00','18:55'][i],end:['09:00','09:55','11:00','11:55','13:45','14:40','15:45','16:40','18:45','19:40'][i]})):[];
  const classes=[[0,0,1,2,'教学中心 301'],[0,1,3,4,'教学中心 201'],[1,2,1,2,'信息学院 1A105'],[1,0,5,6,'计算机实验室 2'],[2,1,1,2,'教学中心 201'],[2,4,5,6,'教学中心 203'],[3,0,3,4,'教学中心 301'],[3,3,7,8,'教学中心 102'],[4,2,1,2,'信息学院 1A105']].map(([day,c,start,end,location],i)=>({id:'class:'+i,title:courses[c].title,course_title:courses[c].title,course_id:'bb:'+c,source:'timetable',event_type:'class',date:`2026-10-${19+day}`,original_date:`2026-10-${19+day}`,weekday:day+1,period_start:start,period_end:end,at:at(19+day,periods[start-1].start),ends_at:at(19+day,periods[end-1].end),location,weeks:[7],appearance:courses[c].appearance}));
  const pending=assignments.filter(a=>a.pending);
  state.scheduleAdded=mode==='notices';state.history=[];state.replayEvents=[];
  const lecture={id:'event:shape',title:'下一次形策讲座',event_type:'activity',source:'local',starts_at:at(21,'18:00'),at:at(21,'18:00'),ends_at:at(21,'19:30'),location:'会议中心',notes:'主题：当前宏观经济形势走势及热点问题。结束时间暂估；需另行通过今日校园报名。'};
  const events=()=>[...pending.map(a=>({...a,event_type:'deadline',at:a.due_at})),{id:'event:study',title:'概率论 · 条件概率复习',source:'local',event_type:'study',at:at(20,'19:00'),ends_at:at(20,'19:30'),location:'图书馆自习区'},{id:'event:chip',title:'造芯大讲堂 · CIS',source:'local',event_type:'lecture',at:at(21,'15:30'),ends_at:at(21,'17:30'),location:'地点待邮件通知',notes:'演示学生的参会计划；报名资格以确认邮件为准。'},...(state.scheduleAdded?[lecture]:[])];
  const days=()=>Array.from({length:7},(_,i)=>({date:`2026-10-${19+i}`,events:[...classes,...events()].filter(e=>e.at?.slice(0,10)===`2026-10-${19+i}`)}));
  const metadata={...baseline.data.metadata,semester:'2026—2027 学年 秋季学期',source_metadata:Object.fromEntries(['timetable','blackboard','gradescope','piazza','elrc','mail'].map(id=>[id,{status:'ready',updated_at:at(19,'08:10')}]))};
  const data={...baseline.data,courses,assignments,materials,messages,timetable:classes,metadata,posts:[{id:'post:1',title:'[Announcement] Homework 2 Released',source:'piazza',course_id:'piazza:0',url:'https://piazza.com/',body_text:source.notices[1].summary}],announcements:[{id:'announcement:1',title:'信号与系统：第二次作业已发布',source:'blackboard',course_id:'bb:2',url:'https://bb.shanghaitech.edu.cn/',body_text:source.notices[2].summary}],lessons:[{id:'lesson:1',title:'第一章',source:'elrc',course_id:'elrc:1',url:'https://elrc.shanghaitech.edu.cn/',body_text:'课程录播'}]};
  const snapshot=()=>({status:'ready',data,updated_at:at(19,'08:10'),account_revision:'film-demo'});
  const proposal={id:'proposal:shape',state:'pending',event:lecture,quote:'2026 年 10 月 21 日 18:00，会议中心。今日校园 App 报名截止 17:00。'};
  const notices=[{id:'notice:1',title:'本周作业汇总 · 先处理周二截止',summary:'**信号与系统 HW2**：10 月 20 日 18:00 截止。\n\n**CS100 HW2_p1 / HW2_p2**：10 月 22 日 23:59 截止。建议先核对题目要求，再安排每天的练习时间。',importance:'important',read:false,event_at:at(20,'18:00'),citations:[{source:'blackboard',title:'信号与系统：第二次作业已发布',url:'https://bb.shanghaitech.edu.cn/'},{source:'gradescope',title:'CS100 · HW2_p1 / HW2_p2',url:'https://www.gradescope.com/'}]},
    {id:'notice:2',title:'形策讲座 · 报名截止 10 月 21 日 17:00',summary:'**当前宏观经济形势走势及热点问题**\n\n10 月 21 日 18:00，会议中心。本科生签到可计入形策课考勤；请先到今日校园 App 报名。',importance:'important',read:false,event_at:lecture.at,proposal_id:proposal.id,why:'演示账号仍需形策考勤，讲座时间与已知课程不冲突。',citations:[{source:'mail',title:messages[0].title,url:messages[0].url}]}];
  notices.forEach((n,i)=>{n.source_revision='film:'+i;n.summary=n.summary.replaceAll('**','');});
  state.notify=async()=>{notices[0].source_revision='film:update';await state.poll();};
  const scheduleReply=structuredClone(source.scheduleConversation.find(m=>m.role==='assistant'));
  const replies={schedule:{prompt:source.scheduleConversation.find(m=>m.role==='user').text,...scheduleReply},...exampleReplies};
  state.reply=replies[mode];
  let stream;
  state.emit=event=>{
    if(!stream)throw new Error('Replay stream has not started');
    state.replayEvents.push(event.type);stream.enqueue(new TextEncoder().encode(JSON.stringify(event)+'\n'));
    if(event.type==='complete'){state.history=[{role:'user',text:state.reply.prompt},event.message];stream.close();stream=null;}
  };
  state.complete=()=>{
    const message={role:'assistant',model:'deepseek-flash',created_at:at(19,'08:20'),conversation_id:'demo-conversation',...state.reply};
    delete message.prompt;
    if(mode==='schedule')state.scheduleAdded=true;
    state.emit({type:'complete',message});
  };
  window.fetch=async(url,options={})=>{
    const target=new URL(url instanceof Request?url.url:url,location.origin),path=target.pathname.replace('/api/v1',''),method=options.method||'GET';
    if(path==='/modules/academic-assistant/chat/stream'){
      if(!state.reply)throw new Error('Missing replay answer');
      state.streamStarted=true;
      return new Response(new ReadableStream({start(controller){stream=controller;}}),{headers:{'Content-Type':'application/x-ndjson'}});
    }
    if(path==='/modules/academic-assistant/chat')return json({messages:state.history,conversation_id:'demo-conversation',owner:'film-demo'});
    if(path==='/modules/academic-assistant/conversations')return json({items:[{id:'demo-conversation',title:state.history.length?'本周的学习安排':'新对话',archived:false,updated_at:at(19,'08:20')}],active_id:'demo-conversation'});
    if(path==='/modules/academic-assistant/profile')return json({profile:{major:'电子信息工程',cohort_year:2025,direction:'人工智能与机器人',weekly_hours:12,notes:'循序渐进，先理解再练习。'},academic:{plan_title:source.curriculum.title}});
    if(path==='/modules/mail/intelligence')return json({messages,preferences:prefs,effective_preferences:prefs,buckets:{focus:'重点关注',recommend:'兴趣推荐',digest:'摘要',filter:'已筛选'},interests:{research:'科研讲座',clubs:'社团活动',career:'实习就业'},review_status:{available:true,enabled:true}});
    if(path==='/modules/mail/message'){
      const i=Number(target.searchParams.get('message_id').split(':').at(-1)),m=source.notices[i];
      return json({body_html:'<p>'+m.body.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</p>'});
    }
    if(path==='/modules/mail/preferences'&&method==='PUT'){Object.assign(prefs,JSON.parse(options.body));return json({preferences:prefs,effective_preferences:prefs});}
    if(['/modules/courses/snapshot','/modules/mail/snapshot'].includes(path))return json(snapshot());
    if(path==='/modules/courses/appearance')return json({palette,courses:courses.map(c=>({id:c.id,appearance:c.appearance}))});
    if(path==='/modules/courses/course'){
      const course=courses.find(c=>c.id===target.searchParams.get('course_id'));
      return json({course,...data,grades:[],materials:materials.filter(m=>course.sources.some(s=>s.id===m.course_id)),posts:data.posts.filter(p=>course.sources.some(s=>s.id===p.course_id)),announcements:data.announcements.filter(p=>course.sources.some(s=>s.id===p.course_id)),lessons:data.lessons.filter(p=>course.sources.some(s=>s.id===p.course_id)),timetable:classes.filter(c=>c.course_title===course.title),assignments:assignments.filter(a=>a.course_title===course.title)});
    }
    if(path==='/modules/assignments/snapshot')return json({...snapshot(),pending,summary:{total:assignments.length,unsubmitted:3,pending:3},order:{}});
    if(path==='/modules/dashboard/snapshot')return json({...snapshot(),stats:{courses:6,pending:3,materials:materials.length,ready_sources:6},pending,notifications:notices,agenda:days().slice(0,2)});
    if(path==='/modules/timetable/schedule')return json({...snapshot(),calendar:{week_start:'2026-10-19',week_end:'2026-10-25',week_one:'2026-09-07',week_one_source:'school',teaching_week:7,periods,days:days(),conflicts:[]},palette,sources:metadata.source_metadata});
    if(path==='/modules/timetable/calendar-settings')return json({week_one:'2026-09-07',source:'school',url:'https://www.shanghaitech.edu.cn/',checked_at:at(19,'08:10')});
    if(path==='/modules/notifications/snapshot')return json({items:notices,configured:true,auto_generate:true});
    if(path==='/modules/campus-agent/status'||path==='/modules/notifications/agent/status')return json({available:true,owner:'film-demo',enabled:true,running:false,last_checked:at(19,'08:10'),summary:'已检查邮件、课程和作业更新',notices,proposals:[{...proposal,state:state.scheduleAdded?'accepted':'pending'}]});
    if(path.endsWith('/proposals/proposal:shape/accept')){state.scheduleAdded=true;return json({...proposal,state:'accepted'});}
    if(path==='/modules/eams/snapshot')return json({...snapshot(),data:{...data,assignments:[{title:'信号与系统 · 期中考试',date:'2026-11-03',window:'18:00—20:00',location:'教学中心 301',exam_kind:'期中考试',note:'演示安排'}],metadata:{...metadata,semester:'2026—2027 秋季学期',semesters:[{id:'fall',name:'2026—2027 秋季学期'}],semester_id:'fall',study_plan:{title:source.curriculum.title,groups:source.curriculum.groups.filter(g=>g.path[0]==='专业课程'||g.path.at(-1)==='自然科学基础选修课')}}}});
    return offlineFetch(url,options);
  };
}

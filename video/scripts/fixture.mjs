// Capture-only data. The browser blocks real API traffic before this function runs.
export function installFixture(bootstrap, themes, theme, chatMode='study') {
  const NativeDate=Date, moment=new NativeDate('2026-10-12T08:20:00+08:00').valueOf();
  window.Date=class extends NativeDate {constructor(...args){super(...(args.length?args:[moment]));}static now(){return moment;}};
  localStorage.setItem('campus.appearance.v1',JSON.stringify({theme,companions:{observatory:'female','star-notes':'female'}}));
  const savedFetch=window.fetch.bind(window), at=(day,time='23:59')=>`2026-10-${day}T${time}:00+08:00`;
  const state=window.filmDemo={unexpected:[],calls:[],accepted:false};
  const modules=bootstrap.modules.map(item=>({...item,enabled:true,status:'ready'}));
  const palette=[{key:'sist',label:'信息科学与技术学院',accent:'#5e81ac',tint:'#edf2f9',ink:'#253c58'},{key:'math',label:'数学科学研究所',accent:'#a16b98',tint:'#f4edf4',ink:'#603b59'},{key:'physics',label:'物质科学与技术学院',accent:'#789663',tint:'#eff4e9',ink:'#3f5730'},{key:'humanities',label:'人文科学研究院',accent:'#ca9b3e',tint:'#faf4e6',ink:'#705223'}];
  const specifications=[['CS100','计算机编程',0],['MATH111','线性代数',1],['PHYS111','普通物理 I',2],['GE101','科学、技术与社会',3],['CS101','计算机科学导论',0],['ENG101','大学英语',3]];
  const courses=specifications.map(([code,title,color],i)=>({id:`course:${i}`,code,title,term:'2026-2027-1',current:true,appearance:palette[color],course_ids:[`bb:${i}`,`gs:${i}`],sources:[{id:`bb:${i}`,code,title,term:'2026-2027-1',source:'blackboard',url:'https://bb.shanghaitech.edu.cn/'},{id:`gs:${i}`,code,title,term:'2026-2027-1',source:'gradescope',url:'https://www.gradescope.com/'},{id:`elrc:${i}`,code,title,term:'2026-2027-1',source:'elrc',url:'https://elrc.shanghaitech.edu.cn/'},{id:`piazza:${i}`,code,title,term:'2026-2027-1',source:'piazza',url:'https://piazza.com/'}]}));
  const assignmentSpecs=[['Lab 03 · 循环与函数',0,12,'gradescope'],['Problem Set 04 · 线性方程组',1,14,'blackboard'],['Homework 05 · 牛顿运动定律',2,15,'gradescope'],['阅读回应 · 技术与社会',3,16,'blackboard'],['Project 01 · 数据可视化',4,18,'gradescope']];
  const assignments=assignmentSpecs.map(([title,course,day,source],i)=>({id:`assignment:${i}`,title,course_title:courses[course].title,course_id:`${source==='blackboard'?'bb':'gs'}:${course}`,source,due_at:at(day),submitted:false,submission_status:'not_submitted',submission_reason:'来源显示尚未提交',category:'pending',availability:'open',current:true,url:source==='gradescope'?'https://www.gradescope.com/':'https://bb.shanghaitech.edu.cn/'}));
  assignments.push({id:'assignment:done',title:'Lab 02 · 条件与分支',course_title:courses[0].title,course_id:'gs:0',source:'gradescope',due_at:at('09'),submitted:true,submission_status:'graded',category:'graded',score:92,max_score:100,current:true,url:'https://www.gradescope.com/'});
  const materials=[['Lecture 05 · Loops and Functions.pdf','循环、函数调用与程序分解。'],['Lab 03 · Instructions.pdf','本次实验练习循环控制与函数设计。'],['Course Syllabus · Fall 2026.pdf','课程目标、考核安排与学习要求。'],['Week 05 · 示例程序.zip','课堂代码与练习参考。']].map(([title,body_text],i)=>({id:`material:${i}`,course_id:'bb:0',source:'blackboard',title,body_text,url:'https://bb.shanghaitech.edu.cn/',download_url:'/api/v1/modules/blackboard/file?material_id=demo'}));
  const lessons=[{id:'lesson:1',course_id:'elrc:0',source:'elrc',title:'第 5 周 · 循环结构与函数',body_text:'课堂录播与章节要点。',url:'https://elrc.shanghaitech.edu.cn/'}];
  const posts=[{id:'post:1',course_id:'piazza:0',source:'piazza',title:'Lab 03：函数参数与返回值讨论',body_text:'请先检查函数的输入和返回值，再用小例子验证。',url:'https://piazza.com/'}];
  const announcements=[{id:'announcement:1',course_id:'bb:0',source:'blackboard',title:'Week 06 · 实验课安排',body_text:'本周实验课请携带电脑，提前阅读 Lab 03。',url:'https://bb.shanghaitech.edu.cn/'}];
  const prefs={degree:'bachelor',year:1,major:'计算机科学与技术',courses:['CS100','MATH111','PHYS111'],shape:'required',mental:'required',interests:{research:'follow',clubs:'digest',career:'digest'},requirements:'关注人工智能与机器人相关讲座。形策和心理活动优先提醒；已经结束的活动只保留摘要。'};
  const mailSpecs=[
    ['关于开展「科技创新与青年责任」形策报告的通知','学生事务处','focus','形策活动','周三 18:30，教学中心 101。报告提供形策考勤，需提前报名。'],
    ['心理健康主题工作坊 · 与压力相处','心理健康教育中心','focus','心理活动','周五 15:30，学生中心 202。面向本科生，计入心理活动记录。'],
    ['CS100 · Lab 03 已发布','CS100 课程组','focus','课程作业','循环与函数实验已发布，10 月 12 日 23:59 截止。'],
    ['人工智能与机器人前沿论坛','学术交流中心','recommend','科研讲座','周四 16:00，报告厅 2。主题与你关注的人工智能与机器人相关。'],
    ['关于调整图书馆周末开放时间的通知','图书馆','digest','校园服务','本周末图书馆延长开放至 23:00。'],
    ['2026 秋季校园摄影征集','校园文化中心','digest','校园活动','用照片记录校园日常，作品征集将持续至月底。'],
    ['研究生海外交流项目宣讲','研究生院','filter','交流项目','本次项目面向在读研究生，按当前本科背景筛选收起。']
  ];
  const messages=mailSpecs.map(([title,sender,bucket,category,summary],i)=>({id:`mail:${i}`,title,sender,received_at:at('12',`0${7-i%3}:30`),source:'mail',unread:i<4,url:'https://mail.shanghaitech.edu.cn/',classification:{bucket,category,summary,reason:i===0?'本科一年级，尚需完成形策要求；正文明确写明考勤。':i===1?'本科一年级，尚需完成心理活动。':i===3?'符合已保存的人工智能与机器人兴趣。':'按当前背景与课程偏好分类。',by:'agent',review_pending:false,evidence:[{source:'body_text',quote:summary}]}}));
  const event={title:'科技创新与青年责任 · 形策报告',starts_at:at('14','18:30'),ends_at:at('14','20:00'),location:'教学中心 101',event_type:'lecture'};
  const proposal={id:'proposal:shape',state:'pending',event,quote:'报告时间：2026 年 10 月 14 日 18:30—20:00，地点：教学中心 101。本场报告提供形策考勤。'};
  const notices=[{id:'notice:1',title:'今晚截止 · CS100 Lab 03',summary:'**循环与函数实验**今晚 23:59 截止。建议先完成基础题，再检查边界输入。',importance:'urgent',read:false,event_at:at('12'),source_revision:'demo:1',citations:[{source:'gradescope',title:'Lab 03 · 循环与函数',url:'https://www.gradescope.com/'}]},
    {id:'notice:2',title:'可参加的形策报告 · 周三晚',summary:'「科技创新与青年责任」与你当前的形策要求相关，请确认是否参加。',importance:'important',read:false,proposal_id:proposal.id,event_at:event.starts_at,why:'本科一年级，形策要求仍需完成。活动时间与已知课表没有重叠。',source_revision:'demo:2',citations:[{source:'mail',title:messages[0].title,url:messages[0].url}]},
    {id:'notice:3',title:'心理健康工作坊 · 本周五',summary:'「与压力相处」工作坊开放报名，已保留时间、地点与原始通知。',importance:'important',read:false,event_at:at('16','15:30'),source_revision:'demo:3',citations:[{source:'mail',title:messages[1].title,url:messages[1].url}]}];
  const classSpecs=[[0,0,1,2,'教学中心 301'],[0,1,3,4,'教学中心 201'],[1,2,1,2,'教学中心 102'],[1,0,5,6,'计算机实验室 2'],[2,1,1,2,'教学中心 201'],[2,3,5,6,'教学中心 203'],[3,0,3,4,'教学中心 301'],[3,2,7,8,'教学中心 102'],[4,4,1,2,'教学中心 305'],[4,1,5,6,'教学中心 201']];
  const periods=[['08:15','09:00'],['09:10','09:55'],['10:15','11:00'],['11:10','11:55'],['13:00','13:45'],['13:55','14:40'],['15:00','15:45'],['15:55','16:40'],['18:00','18:45'],['18:55','19:40']].map(([start,end],i)=>({period:i+1,start,end}));
  const days=Array.from({length:7},(_,i)=>({date:`2026-10-${12+i}`,events:[]}));
  const timetable=classSpecs.map(([day,c,start,end,location],i)=>({id:`class:${i}`,title:courses[c].title,course_title:courses[c].title,course_id:`bb:${c}`,source:'timetable',event_type:'class',date:days[day].date,original_date:days[day].date,weekday:day+1,period_start:start,period_end:end,at:at(12+day,periods[start-1].start),ends_at:at(12+day,periods[end-1].end),location,teacher:['陈老师','李老师','王老师','张老师'][c%4],weeks:[6],appearance:courses[c].appearance}));
  const events=[...assignments.filter(x=>x.category==='pending').map(x=>({...x,event_type:'deadline',at:x.due_at})),{id:'event:study',title:'线性代数 · 复习与自测',event_type:'study',source:'local',at:at('13','19:00'),ends_at:at('13','20:00'),location:'图书馆自习区'},{id:'event:mental',title:'心理健康工作坊',event_type:'activity',source:'local',at:at('16','15:30'),location:'学生中心 202'}];
  for(const day of days)day.events=[...timetable,...events].filter(x=>x.at?.slice(0,10)===day.date);
  const source_metadata=Object.fromEntries(['timetable','blackboard','gradescope','piazza','elrc','mail'].map(id=>[id,{status:'ready',updated_at:at('12','08:10')}]));
  const data={courses,assignments,materials,lessons,posts,announcements,timetable,messages,issues:[],metadata:{current_semester:'2026-2027-1',semester:'2026—2027 学年 秋季学期',week_count:18,source_metadata}};
  const snapshot=(extra={})=>({status:'ready',updated_at:at('12','08:10'),data,account_revision:'film-demo',...extra});
  const ai={enabled:true,provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',key_saved:true,custom:false,providers:[{provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',key_saved:true,custom:false},{provider:'openai',display_name:'OpenAI',model:'gpt-4.1',base_url:'https://api.openai.com/v1',key_saved:false,custom:false}],vision:{enabled:false,key_saved:false,ready:false}};
  const providers=['ids','coremail','gradescope','piazza'].map(id=>({id,name:{ids:'学校 IDS',coremail:'学校邮箱',gradescope:'Gradescope',piazza:'Piazza'}[id],username:'student@example.edu',has_password:true,has_session:true,status:'ready',identity_verified:true,automatic_recovery:id!=='coremail',...(id==='ids'?{targets:['blackboard','elrc','ecourse','timetable'],target:'blackboard',device:{configured:true,enabled:true,pending:false,setup:{status:'ready'}}}:{})}));
  const studyMessages=[{role:'user',text:'这周作业比较多，帮我结合课件安排复习。线性代数的消元法还不太熟。',created_at:at('12','08:12')},{role:'assistant',model:'deepseek-flash',created_at:at('12','08:13'),text:'## 先处理今晚的截止，再留时间理解难点\n\n**今天：CS100 Lab 03**\n先完成循环与函数的基础题，再用空输入和重复输入自测。今晚 23:59 截止。\n\n**明晚：线性代数，45 分钟**\n从课件第 8 页的增广矩阵开始，手算一次高斯消元，重点解释每一步行变换。[1]\n\n**周三：整理 Problem Set 04**\n把不会的题对应到课件，做完后用代回原方程的方法检查。\n\n建议先独立尝试；卡住时可以继续问我具体步骤。',citations:[{source_id:'demo:slide:8',record_id:'demo:slides',title:'Lecture 04 · 线性方程组.pdf',quote:'初等行变换保持方程组的解集不变；通过消元将增广矩阵化为阶梯形。',page:8,kind:'pdf',evidence_type:'original_text',url:'https://bb.shanghaitech.edu.cn/'}]}];
  const actionMessages=[{role:'user',text:'明晚 19 点在图书馆安排一小时线代复习。另外，邮件里帮我优先关注机器人相关讲座。',created_at:at('12','08:15')},{role:'assistant',model:'deepseek-flash',created_at:at('12','08:15'),text:'已安排 **周二 19:00—20:00 · 线性代数复习**，地点是图书馆自习区。\n\n邮件偏好已补充：**优先关注机器人相关讲座**。已有手动分类继续保留。\n\n复习时可以先做一次消元，再检查增广矩阵中的主元位置。',changes:[{applied:true,domain:'timetable',action:'create',after:{title:'线性代数 · 复习与自测',starts_at:at('13','19:00'),ends_at:at('13','20:00'),location:'图书馆自习区'},before:null}],citations:[]}];
  const advisingMessages=[{role:'user',text:'结合我的培养方案、本学期课程和机器人方向的兴趣，下学期选课可以怎么考虑？',created_at:at('12','08:17')},{role:'assistant',model:'deepseek-flash',created_at:at('12','08:17'),text:'## 先把基础接好，再留出探索的空间\n\n本学期你在修 **计算机编程、线性代数、普通物理 I**，关注方向是人工智能与机器人。可以这样核对下学期的安排：\n\n| 优先级 | 查看什么 | 为什么 |\n| --- | --- | --- |\n| 1 | 本专业必修与先修要求 | 把基础课程的学习顺序接好 |\n| 2 | 数学与计算机基础课程 | 为后续算法、建模和控制打基础 |\n| 3 | 一门相关通识或兴趣课程 | 兼顾探索与每周可用时间 |\n\n培养方案与课程目录可以继续逐项查询。[1] **正式开课与时间安排以学校公布为准。**',citations:[{source_id:'demo:curriculum',record_id:'demo:curriculum',title:'计算机科学与技术 · 本科培养方案',quote:'修读计划应结合必修要求、课程先修关系与每学期实际开课安排。',kind:'text',url:'https://eams.shanghaitech.edu.cn/'}]}];
  const history=()=>chatMode==='empty'?[]:chatMode==='actions'?actionMessages:chatMode==='advising'?advisingMessages:studyMessages;
  const agent=()=>({available:true,owner:'film-demo',enabled:true,running:false,last_checked:at('12','08:10'),summary:'已检查课程、作业与邮件更新',notices,proposals:[{...proposal,state:state.accepted?'accepted':'pending'}],pending_count:0});
  const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const target=new URL(url instanceof Request?url.url:url,location.origin);
    if(!target.pathname.startsWith('/api/v1/'))return savedFetch(url,options);
    const path=target.pathname.replace('/api/v1',''),method=options.method||'GET';state.calls.push({path,method});
    if(path==='/bootstrap')return json({...bootstrap,version:'2026.10',csrf_token:'film-demo',modules});
    if(path==='/themes')return json(themes);
    if(path==='/modules')return json({modules,categories:bootstrap.categories});
    if(path==='/settings')return json({port:16666,active_port:16666,restart_required:false,storage:{directory:'.private',encryption:'Windows DPAPI'}});
    if(path==='/data/backups')return json({backups:[]});
    if(path==='/auth/providers')return json({providers});
    if(path==='/auth/network')return json({mode:'direct',proxy_url:'',targets:[]});
    if(path==='/ai/settings')return json(ai);
    if(path==='/ai/catalog')return json({providers:[{id:'deepseek',name:'DeepSeek',models:['deepseek-flash','deepseek-v4-pro']},{id:'openai',name:'OpenAI',models:['gpt-4.1']},{id:'anthropic',name:'Anthropic',models:['claude-sonnet-4']}],protocols:['openai-completions','openai-responses','anthropic-messages']});
    if(path==='/modules/campus-agent/status'||path==='/modules/notifications/agent/status')return json(agent());
    if(path==='/modules/mail/intelligence')return json({messages,preferences:prefs,effective_preferences:prefs,buckets:{focus:'重点关注',recommend:'兴趣推荐',digest:'摘要',filter:'已筛选'},interests:{research:'科研讲座',clubs:'社团活动',career:'实习就业'},review_status:{available:true,enabled:true}});
    if(path==='/modules/mail/message')return json({body_html:`<p>各位同学：</p><p>${messages.find(x=>x.id===target.searchParams.get('message_id'))?.classification.summary||messages[0].classification.summary}</p><p>请有意参加的同学提前登记，并携带校园卡。活动安排以本通知及后续更新为准。</p><p>学生事务处<br>2026 年 10 月 12 日</p>`});
    if(path==='/modules/mail/snapshot')return json(snapshot());
    if(path==='/modules/courses/groups')return json({groups:[]});
    if(path==='/modules/courses/appearance')return json({palette,courses:courses.map(x=>({id:x.id,appearance:x.appearance}))});
    if(path==='/modules/courses/snapshot')return json(snapshot());
    if(path==='/modules/courses/course'){const course=courses.find(x=>x.id===target.searchParams.get('course_id'))||courses[0];return json({course,...data,grades:[],assignments:assignments.filter(x=>x.course_title===course.title)});}
    if(path==='/modules/assignments/snapshot')return json(snapshot({pending:assignments.filter(x=>x.category==='pending'),summary:{total:6,unsubmitted:5,pending:5},order:{}}));
    if(path==='/modules/dashboard/snapshot')return json(snapshot({stats:{courses:6,pending:5,materials:38,ready_sources:6},pending:assignments.filter(x=>x.category==='pending'),notifications:notices,agenda:days.slice(0,2)}));
    if(path==='/modules/timetable/schedule')return json(snapshot({calendar:{week_start:days[0].date,week_end:days[6].date,week_one:'2026-09-07',week_one_source:'school',teaching_week:6,periods,days,conflicts:[]},palette,sources:source_metadata}));
    if(path==='/modules/timetable/calendar-settings')return json({week_one:'2026-09-07',source:'school',url:'https://www.shanghaitech.edu.cn/',checked_at:at('12','08:10')});
    if(path==='/modules/notifications/snapshot')return json({items:notices,configured:true,auto_generate:true});
    if(path.startsWith('/modules/notifications/proposals/')&&path.endsWith('/accept')){state.accepted=true;return json({...proposal,state:'accepted'});}
    if(path==='/modules/academic-assistant/chat')return json({messages:history(),conversation_id:'demo-conversation',owner:'film-demo'});
    if(path==='/modules/academic-assistant/conversations')return json({items:[{id:'demo-conversation',title:chatMode==='actions'?'安排复习与邮件偏好':'本周作业与线代复习',archived:false,updated_at:at('12','08:13')}],active_id:'demo-conversation'});
    if(path==='/modules/academic-assistant/profile')return json({profile:{major:'计算机科学与技术',cohort_year:2026,direction:'人工智能与机器人',weekly_hours:12,notes:'先自己尝试，再讨论难点。'},academic:{plan_title:'计算机科学与技术本科培养方案'}});
    if(path==='/modules/academic-assistant/presets')return json({items:[{label:'安排本周作业',prompt:'帮我安排本周作业'},{label:'结合课件复习',prompt:'结合课件解释这个知识点'},{label:'下学期选课建议',prompt:'结合培养方案给出下学期选课建议'}]});
    if(path==='/modules/academic-assistant/reader/settings')return json({mode:'auto',fallback:true,ocr_backend:'windows',docling_python:'',max_pages:4,vision:ai.vision});
    if(path==='/modules/eams/snapshot')return json(snapshot());
    state.unexpected.push(method+' '+path);return json({detail:'Film fixture route missing: '+path},404);
  };
}

export async function installFeatures(source){
  const previous=window.fetch,state=window.filmDemo,json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  const snapshot=await(await previous('/api/v1/modules/courses/snapshot')).json(),data=snapshot.data;
  data.courses.forEach(course=>course.course_ids=course.sources.map(s=>s.id));
  data.assignments.forEach(item=>Object.assign(item,{actionable:item.pending===true,availability:'open'}));
  const appearance={revision:1,resetRevision:0,value:JSON.parse(localStorage.getItem('campus.appearance.v1'))};
  const theme=appearance.value.theme;
  appearance.value.options={observatory:{moments:{dashboard:true,timetable:true},rotation:{autoplay:false,seconds:20}},'star-notes':{moments:{dashboard:true,timetable:true},rotation:{autoplay:false,seconds:20}}};
  Math.random=()=>.37;
  const chat=source.groupChats[0],quote=chat.messages.find(m=>m.role==='ta').text;
  const groups=[{id:'demo-cs100',name:'CS100 课程交流群（演示）',message_count:28},{id:'demo-si140',name:'SI140A 课程群（演示）',message_count:16}];
  const chosen={id:groups[0].id,name:groups[0].name,course_id:'course:0',trusted_senders:['demo-ta'],auto_extract:false,auto_apply:false};
  const qqGroup={id:'demo-signals',name:source.groupChats[1].title+'（演示）',message_count:18};
  const groupState={account_revision:'film-demo',ai:{enabled:true,model:'deepseek-flash'},running:null,queued:false,sources:{wechat:{connected:true,connection:'film-connection',revision:'film:1',enabled:true,groups,selected:[chosen],interval_seconds:300,history_days:7,allow_ai:true,coverage:{},account_label:'演示账号',last_synced_at:'2026-10-19T08:10:00+08:00'},qq:{connected:true,connection:'film-qq',revision:'film:1',enabled:true,groups:[qqGroup],selected:[{...qqGroup,course_id:source.groupChats[1].course_id,trusted_senders:[],auto_extract:false,auto_apply:false}],interval_seconds:300,history_days:7,allow_ai:true,coverage:{},account_label:'演示账号',last_synced_at:'2026-10-19T08:10:00+08:00'}}};
  let items=[];
  const dayOf=(offset)=>new Date(Date.parse('2026-10-19T12:00:00+08:00')+offset*86400000).toISOString().slice(0,10);
  window.fetch=async(url,options={})=>{
    const target=new URL(url instanceof Request?url.url:url,location.origin),path=target.pathname.replace('/api/v1',''),method=options.method||'GET',body=options.body?JSON.parse(options.body):null;
    if(path==='/bootstrap'){const value=await(await previous(url,options)).json();value.settings={...value.settings,appearance};return json(value);}
    if(path==='/settings')return json({port:17666,active_port:17666,restart_required:false,appearance,storage:{directory:'.private',encryption:'Windows DPAPI'}});
    if(path==='/settings/appearance'&&method==='PATCH'){Object.assign(appearance.value,body.patch);appearance.revision++;return json(appearance);}
    if(path==='/modules/courses/snapshot')return json(snapshot);
    if(path==='/modules/assignments/snapshot'){const value=await(await previous(url,options)).json();value.data=data;return json(value);}
    if(path==='/auth/providers'){const value=await(await previous(url,options)).json();const school=value.providers.find(p=>p.id==='ids');school.services=['blackboard','elrc','ecourse','timetable'].map(id=>({id,status:'ready'}));school.connection={status:'complete',completed:4};value.providers.find(p=>p.id==='coremail').imap={configured:true,host:'imap.shanghaitech.edu.cn',port:993,ssl:true,username:'student@example.edu',password_saved:true};return json(value);}
    if(path==='/modules/timetable/schedule'){
      const value=await(await previous(url,options)).json();
      value.overview={week_start:'2026-10-19',pending:data.assignments.filter(a=>a.pending).length,late:0,weeks:[-1,0,1,2].map(offset=>({offset,week_start:dayOf(offset*7),week_end:dayOf(offset*7+6),teaching_week:7+offset,days:Array.from({length:7},(_,i)=>({date:dayOf(offset*7+i),events:data.assignments.filter(a=>a.pending&&a.due_at.slice(0,10)===dayOf(offset*7+i)).map(a=>({...a,event_type:'deadline',at:a.due_at,homework:true,platform:a.source==='gradescope'?'Gradescope':'Blackboard'}))}))}))};
      return json(value);
    }
    if(path.startsWith('/modules/campus-map/')){
      const route=path.slice('/modules/campus-map'.length);
      if(route==='/places')return json(source.map);
      if(route==='/walking-network')return json(source.walking);
      if(route==='/day'){const schedule=await(await previous('/api/v1/modules/timetable/schedule')).json();const date=target.searchParams.get('date')||'2026-10-19';return json({date,available:true,status:'ready',updated_at:snapshot.updated_at,issues:[],events:schedule.calendar.days.find(d=>d.date===date)?.events||[]});}
      if(route==='/conditions')return json({items:[],version:0,account_revision:'film-demo',history:[],undo_available:false});
      if(route==='/discovery')return json({items:[],settings:{enabled:false,official:true,mail:false},running:false,sources:{official:{message:'按需检查校方公告'},mail:{message:'由你选择是否检查邮箱'}},coverage:'仅查看选定来源。',account_revision:'film-demo'});
    }
    if(path.startsWith('/modules/group-messages/')){
      const route=path.slice('/modules/group-messages'.length);
      if(route==='/status')return json(groupState);
      if(route==='/courses')return json({items:data.courses});
      if(route==='/items')return json({items,account_revision:'film-demo'});
      if(route==='/messages'){const thread=source.groupChats.find(c=>c.source===target.searchParams.get('source'));return json({items:thread.messages.map(m=>({sender_id:m.role==='ta'?'demo-ta':m.id,sender_name:m.sender+'（演示）',text:m.text,sent_at:'2026-10-19T'+m.time+':00+08:00'})),total:thread.source==='wechat'?28:18});}
      if(route==='/senders')return json({items:[{id:'demo-ta',name:'林助教（演示）'}]});
      if(route==='/extract'){items=[{id:'demo-hw2',revision:'item:1',source:'wechat',group_name:groups[0].name,kind:'assignment',action:'new',title:'复核 HW2 提交要求',summary:'HW2_p1 / HW2_p2：10 月 22 日 23:59 截止。核对 Gradescope 的提交要求，再安排检查与提交。',reason:'课程平台已有作业；这条本地准备待办由你确认。',status:'pending',course:{id:'course:0',title:'计算机编程'},due_at:'2026-10-22T23:59:00+08:00',time_verified:true,citations:[{message_id:'wx-2',quote,sender_name:'林助教（演示）',sent_at:'2026-10-19T08:00:00+08:00'}]}];return json({queued:true});}
      if(route==='/items/demo-hw2/decision'){const item=items[0];item.revision+=':next';item.status=body.action==='apply'?'applied':body.action==='undo'?'dismissed':'accepted';item.receipt=body.action==='apply'?{applied:true,local_only:true}:null;return json(item);}
    }
    return previous(url,options);
  };
}

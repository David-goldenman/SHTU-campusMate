import {defineTool} from '@deepseek-ai/dsh-tools';
import {writeFile} from 'node:fs/promises';
import {readFileSync, readdirSync} from 'node:fs';
import {join} from 'node:path';

export const name = 'campus-academic-assistant';
export const inject = ['tools', 'skills'];

export function apply(ctx) {
  for (const name of readdirSync(new URL('./skills/', import.meta.url))) {
    const source = readFileSync(new URL('./skills/' + name + '/SKILL.md', import.meta.url), 'utf8');
    const description = source.match(/^description: (.+)$/m)[1];
    ctx.effect(() => ctx.skills.register({name, description, content:source.replace(/^---[\s\S]*?---\s*/, ''), source:'runtime'}));
  }
  let sequence = 0;
  const workspace = process.cwd();
  register('study_attend','attend','用户本次明确表示参加某项活动或要求加入日程时使用。先查询通知取得 proposal_id，quote 必须直接复制用户本次明确意愿；结合整条消息保留否定、条件与疑问，不得截取短句绕过确认。仅确认已存在的活动建议，不代替报名。',{
    proposal_id:{type:'string',required:true},quote:{type:'string',required:true},
  });
  function register(name, endpoint, description, parameters) {
    ctx.tools.register(defineTool({
      name, description, parameters,
      output:{schema:{type:'string'},render:(_args,value) => [{type:'text',text:value}]},
      async execute(args, execution) {
        execution.signal.throwIfAborted();
        const url = process.env.CAMPUS_PLUGIN_STUDY_URL;
        const token = process.env.CAMPUS_PLUGIN_STUDY_TOKEN;
        if (!url || !token) throw new Error('请从首页学习助手发起任务，以使用已连接资料。');
        const response = await fetch(url + '/tools/' + endpoint,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer ' + token},body:JSON.stringify(args),signal:execution.signal});
        const value = await response.json();
        if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : value.detail.map(item => item.loc.join('.') + ': ' + item.msg).join('; '));
        const filename = `study-${++sequence}-${endpoint}.json`;
        await writeFile(join(workspace,filename),JSON.stringify({tool:name,arguments:args,result:value},null,2));
        return JSON.stringify({...value,workspace_file:filename});
      },
    }));
  }
  const string = {type:'string'};
  const pagination = {offset:{type:'integer'},limit:{type:'integer'}};
  const timing = {starts_at:{type:'string',description:'带时区的 ISO 时间，北京时间使用 +08:00。'},ends_at:string,date:{type:'string',description:'按节次安排的 YYYY-MM-DD 日期。'},period_start:{type:'integer'},period_end:{type:'integer'},location:string,notes:string};
  register('study_capabilities','capabilities','查询当前助手实际支持的阅读、日程和学习事务能力及可用状态。',{});
  register('study_work_edit','work-edit','按本次明确指令管理本地作业进度、提醒和学习计划。quote 完整复制本次消息。create 新增 reminder/plan；update/delete 前先 query workspace，update 只传需要修改的 title/status/due_at/notes，不传 kind 或记录元数据；set_assignment 前先 query assignments，record_id 用原作业 ID，仅更新本地 status/notes，不代表学校平台提交。提醒必须有带时区的 due_at；计划正文放 notes。',{
    action:{type:'string',required:true,enum:['create','update','delete','set_assignment']},quote:{type:'string',required:true},record_id:string,
    item:{type:'object',additionalProperties:false,properties:{kind:{type:'string',enum:['reminder','plan']},title:string,status:{type:'string',enum:['todo','in_progress','done','cancelled']},due_at:timing.starts_at,notes:string}},
  });
  register('study_schedule_edit','schedule-edit','按用户本次明确指令编辑本地时间表。quote 完整复制本次消息。修改前先 query timetable，record_id 必须来自本次结果；目标、日期或单次/后续范围不清楚时先询问。create/update/delete 操作个人安排；adjust_class 操作具体课程。结果是实际保存回执，不能宣称学校端已审批或报名。',{
    action:{type:'string',required:true,enum:['create','update','delete','adjust_class']},quote:{type:'string',required:true},record_id:string,
    event:{type:'object',additionalProperties:false,properties:{title:string,event_type:{type:'string',enum:['quiz','exam','tutorial','study','presentation','activity','lecture']},course_title:string,...timing}},
    adjustment:{type:'object',additionalProperties:false,properties:{action:{type:'string',required:true,enum:['leave','cancel','move','restore']},scope:{type:'string',enum:['once','following']},until_date:string,to_date:string,starts_at:timing.starts_at,ends_at:string,period_start:timing.period_start,period_end:timing.period_end,location:string,notes:string}},
  });
  register('study_query','query','查询已同步课程、作业、时间表、历史课程、本专业培养方案、通知、邮件和个人档案。返回可引用原文。pending=true 仅查询明确可做且未提交的当前作业；其他提交状态不可推测。可按 q、course_id 和分页缩小范围。',{
    area:{type:'string',required:true,enum:['courses','assignments','timetable','course_history','degree_plan','notifications','mail','profile','workspace']},q:string,course_id:string,pending:{type:'boolean'},week_start:{type:'string',description:'查询时间表时可用 YYYY-MM-DD 指定一周，默认本周。'},...pagination,
  });
  register('study_search','search','在课程资料、讨论和录播原文中检索。先 query courses 获取课程中心的 record_id 并作为 course_id；q 只搜索材料标题和正文，列出课程文件时留空，不用课程名搜索文件。检索转写使用 collection=lessons 和 q。材料结果的 record_id 可交给 study_document 读取真实页码。',{
    collection:{type:'string',enum:['materials','lessons','posts']},q:string,course_id:string,...pagination,
  });
  register('study_document','document','按 record_id 下载作业题目或课程文件并读取 PDF/PPTX 页级文字。record_id 必须来自本次查询或检索；可以使用作业 ID。q 用于在页内定位知识点；page 从 1 开始。扫描图片不推测内容。',{
    record_id:{type:'string',required:true},q:string,page:{type:'integer'},limit:pagination.limit,
  });
  register('study_course_search','course-search','查询学校课程目录，q 为课程名或代码；提供 syllabus_id 则读取该课程教学大纲及先修信息。目录查询不代表未来某学期已确定开课。结果包含大纲 ID 与可核对来源。',{
    q:string,page:{type:'integer'},syllabus_id:{type:'integer'},
  });
  register('study_remember','remember','用户明确要求记住本次消息中的个人信息时保存学习档案。quote 必须是用户本次原文，profile 仅包含原文明确出现的新字段；不能推测年级或方向。',{
    quote:{type:'string',required:true},profile:{type:'object',required:true,additionalProperties:false,properties:{major:string,cohort_year:{type:'integer'},direction:string,weekly_hours:{type:'number'},notes:string}},
  });
  register('study_navigate','navigate','用户明确要求打开工作台页面时使用，回答完成后进入指定分类。普通建议保留在聊天中。',{
    category:{type:'string',required:true,enum:['dashboard','mail','timetable','courses','assignments','eams','notifications','assistant','settings']},
  });
  register('study_finish','finish','回答前核对本次来源与引用。quote 只复制实际来源 text 的原文短句，校验失败时修正并再次调用；accepted=true 后用 Markdown 正常输出完整中文回答，不再调用其他工具。无需在此工具传正文。',{
    citations:{type:'array',required:true,items:{type:'object',additionalProperties:false,properties:{source_id:{type:'string',required:true},quote:{type:'string',required:true}}}},insufficient_context:{type:'boolean'},basis:{type:'string',enum:['sources','general'],description:'纯通用知识、代码、写作或规划用 general；引用具体校园资料用 sources。'},
  });
}

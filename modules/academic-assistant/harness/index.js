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
  register('study_query','query','查询已同步课程、作业、时间表、历史课程、本专业培养方案、通知、邮件和个人档案。返回可引用原文。pending=true 仅查询明确可做且未提交的当前作业；其他提交状态不可推测。可按 q、course_id 和分页缩小范围。',{
    area:{type:'string',required:true,enum:['courses','assignments','timetable','course_history','degree_plan','notifications','mail','profile']},q:string,course_id:string,pending:{type:'boolean'},week_start:{type:'string',description:'查询时间表时可用 YYYY-MM-DD 指定一周，默认本周。'},...pagination,
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
    text:{type:'string'},citations:{type:'array',required:true,items:{type:'object',additionalProperties:false,properties:{source_id:{type:'string',required:true},quote:{type:'string',required:true}}}},insufficient_context:{type:'boolean'},
  });
}

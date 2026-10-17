import {defineTool} from '@deepseek-ai/dsh-tools';

export const name='campus-background-agent';
export const inject=['tools'];
export function apply(ctx) {
  const string={type:'string',required:true};
  function register(name,path,description,properties) {
    ctx.tools.register(defineTool({name,description,parameters:properties,output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},async execute(args,scope){
      const response=await fetch(process.env.CAMPUS_PLUGIN_AGENT_URL+'/tools/'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+process.env.CAMPUS_PLUGIN_AGENT_TOKEN},body:JSON.stringify(args),signal:scope.signal});
      const value=await response.json();
      if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'参数不符合接口格式，请依据 schema 修正。');
      return JSON.stringify(value);
    }}));
  }
  register('campus_read','read','按 services 中列出的只读接口查询校园资料；支持接口文档中的查询参数，缩小到必要范围。',{module_id:string,path:string});
  register('campus_mail','mail','获取本轮待复核邮件的正文、完整偏好、证据要求与分类 JSON schema。',{message_id:string});
  register('campus_classify','classify','提交邮件语义分类。decision 按 campus_mail 返回的 schema 填写，引用实际原文。',{message_id:string,fingerprint:string,decision:{type:'object',required:true,additionalProperties:true}});
  register('campus_propose','propose','从已读取来源提出有明确时间的未来安排，等待用户确认参加。event 包含 title、event_type、starts_at（带时区）、可选 ends_at、location、quote 原文。',{module_id:string,source_id:string,event:{type:'object',required:true,additionalProperties:true}});
  register('campus_notice','notice','依据实际来源与原文提醒用户重要事项；普通摘要无需重复通知。',{module_id:string,source_id:string,quote:string,title:string,summary:string,importance:{type:'string',enum:['normal','important','urgent']}});
  register('campus_sync','sync','同步失败时重试该服务一次；需要验证时请提醒用户。',{module_id:string});
}

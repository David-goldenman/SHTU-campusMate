import {defineTool} from '@deepseek-ai/dsh-tools';
export const name='campus-mail-intelligence';
export const inject=['tools'];
export function apply(ctx) {
  ctx.tools.register(defineTool({name:'mail_submit',description:'提交当前邮件的分类、摘要、原文依据与可选活动信息。遵守 context 中的 schema。',
    parameters:{decision:{type:'object',required:true,additionalProperties:true}},output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},
    async execute(args,{signal}) {
      const response=await fetch(process.env.CAMPUS_PLUGIN_MAIL_URL+'/tools/review',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+process.env.CAMPUS_PLUGIN_MAIL_TOKEN},body:JSON.stringify(args),signal});
      const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail.map(item=>({loc:item.loc,msg:item.msg}))));
      return JSON.stringify(value);
    }}));
}

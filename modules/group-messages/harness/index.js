import {defineTool} from '@deepseek-ai/dsh-tools';
export const name = 'campus-group-messages';
export const inject = ['tools'];
export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'group_match_submit',
    description: '提交仅根据群名和本学期课程身份得到的匹配候选；不读取聊天、不执行关联。',
    parameters: {result: {type: 'object', required: true, additionalProperties: true}},
    output: {schema: {type: 'string'}, render: (_args, value) => [{type: 'text', text: value}]},
    async execute({result}, {signal}) {
      signal.throwIfAborted();
      if (!Array.isArray(result.matches) || result.matches.length > 40 || JSON.stringify(result).length > 100000 || result.matches.some(row => !row.group_id || !Array.isArray(row.candidates) || row.candidates.length > 3 || row.candidates.some(value => !value.course_id || !value.evidence || !value.reason || !['synonym','abbreviation','translation','related','unknown'].includes(value.relation)))) {
        throw new Error('每批至多40个群，每群至多3个带群名依据的课程候选。');
      }
      return JSON.stringify(result);
    },
  }));
  ctx.tools.register(defineTool({
    name: 'group_submit',
    description: '提交当前选中群新增消息的事项提取。遵守 context 中的 schema；仅返回候选，不执行任何写入。',
    parameters: {result: {type: 'object', required: true, additionalProperties: true}},
    output: {schema: {type: 'string'}, render: (_args, value) => [{type: 'text', text: value}]},
    async execute({result}, {signal}) {
      signal.throwIfAborted();
      if (!Array.isArray(result.items) || result.items.length > 30 || JSON.stringify(result).length > 100000 || result.items.some(item => !item.title || !Array.isArray(item.citations) || !item.citations.length || item.citations.some(ref => !ref.message_id || !ref.quote))) {
        throw new Error('需要至多 30 项事项，每项包含标题和原文引用；无新事项时提交空数组。');
      }
      return JSON.stringify(result);
    },
  }));
}

import {defineTool} from '@deepseek-ai/dsh-tools';
export const name = 'campus-group-messages';
export const inject = ['tools'];
export function apply(ctx) {
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

import {defineTool} from '@deepseek-ai/dsh-tools';

export const name = 'campus-deadlines';
export const inject = ['tools'];

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'order_deadlines',
    description: '按明确截止时间从早到晚排列所选事项，保留资料 ID。排序只说明时间先后，提交状态与开放能力以资料为准。',
    parameters: {
      items: {type: 'array', required: true, items: {type: 'object', additionalProperties: false, properties: {
        id: {type: 'string', required: true},
        title: {type: 'string', required: true},
        due_at: {type: 'string', required: true},
      }}},
    },
    output: {
      schema: {type: 'string'},
      render: (_args, value) => [{type: 'text', text: value}],
    },
    async execute({items}, execution) {
      execution.signal.throwIfAborted();
      if (items.length > 400 || items.some(item => !item.id || item.id.length > 160 || !item.title || item.title.length > 1000 || item.due_at.length > 64 || !/(Z|[+-]\d{2}:\d{2})$/.test(item.due_at) || !Number.isFinite(Date.parse(item.due_at)))) {
        throw new Error('需要至多 400 项资料，每项包含 ID、标题和带时区的有效截止时间。');
      }
      return JSON.stringify([...items].sort((left, right) => Date.parse(left.due_at) - Date.parse(right.due_at)));
    },
  }));
}

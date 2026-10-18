import {writeFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';

export const inject = ['llm'];

export async function apply(ctx, config) {
  await new Promise((resolve, reject) => {
    let started = false;
    async function complete() {
      if (started || !ctx.llm.listProviders().some(row => row.id === config.provider)) return;
      started = true;
      try {
        const messages = [];
        for (const message of config.messages) {
          const parts = typeof message.content === 'string' ? [{type:'text',text:message.content}] : message.content;
          const content = [];
          for (const part of parts) {
            if (part.type === 'text') content.push(part);
            else if (part.type === 'image') {
              if (!ctx.attachments) throw new Error('Image storage unavailable');
              content.push({type:'image', attachment:await ctx.attachments.saveImage({data:Buffer.from(part.data,'base64'),mediaType:part.mediaType})});
            }
          }
          messages.push({id:randomUUID(),role:message.role,
          content,source:message.role === 'assistant'
            ? {kind:'model',provider:config.provider,model:config.model}
            : {kind:message.role === 'system' ? 'system-prompt' : 'user'}});
        }
        let content = '', finish;
        let usage = {prompt_tokens:0,completion_tokens:0,total_tokens:0};
        for await (const chunk of ctx.llm.stream({provider:config.provider,model:config.model,messages,maxTokens:6000})) {
          if (chunk.type === 'text-delta') content += chunk.text;
          if (chunk.type === 'finish') finish = chunk.reason.kind;
          if (chunk.type === 'usage') {
            const value = chunk.usage;
            const input = (value.inputTokens || 0) + (value.cacheReadTokens || 0) + (value.cacheWriteTokens || 0);
            usage = {prompt_tokens:input,completion_tokens:value.outputTokens || 0,total_tokens:value.totalTokens ?? input + (value.outputTokens || 0)};
          }
        }
        writeFileSync(config.output,JSON.stringify({content,finish,usage}),'utf8');
        resolve();
      } catch { reject(new Error('Model request failed')); }
    }
    ctx.on('llm/adapters-updated',complete);
    queueMicrotask(complete);
  });
}

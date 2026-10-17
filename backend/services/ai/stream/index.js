export const name = 'campus-harness-stream';

export function apply(ctx) {
  // The pinned SDK forwards durable events; this plugin adds live frames on its JSON-RPC transport.
  ctx.on('agent/assistant-stream', ({agent, frame}) => {
    process.stdout.write(JSON.stringify({jsonrpc:'2.0',method:'campus.stream',params:{sessionId:agent.session.id,frame}}) + '\n');
  });
}

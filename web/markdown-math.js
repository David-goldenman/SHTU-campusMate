// Recognize TeX before Markdown consumes backslashes, underscores or asterisks.
// Code spans/fences and escaped dollar signs remain the Markdown parser's job.
function closingDelimiter(source,delimiter,start) {
  for (let pos=start;pos<source.length;pos++) {
    if (source.startsWith(delimiter,pos)) return pos;
    if (source[pos] === '\\') pos++;
  }
  return -1;
}

function inlineMath(state,silent) {
  const start=state.pos, source=state.src;
  let open, close, display=false;
  if (source.startsWith('$$',start)) {open=close='$$';display=true;}
  else if (source[start] === '$') {open=close='$';}
  else if (source.startsWith('\\(',start)) {open='\\(';close='\\)';}
  else if (source.startsWith('\\[',start)) {open='\\[';close='\\]';display=true;}
  else return false;
  const end=closingDelimiter(source,close,start+open.length);
  if (end<0) return false;
  const content=source.slice(start+open.length,end);
  if (!content.trim() || (!display && content.includes('\n'))) return false;
  // Avoid treating the price pair "$5 and $10" as a formula.
  if (open === '$' && /\d/.test(source[end+1] || '')) return false;
  if (!silent) {
    const token=state.push('math_inline','',0);
    token.content=content;
    token.meta={display};
  }
  state.pos=end+close.length;
  return true;
}

function blockMath(state,startLine,endLine,silent) {
  if (state.sCount[startLine]-state.blkIndent>=4) return false;
  const start=state.bMarks[startLine]+state.tShift[startLine];
  const first=state.src.slice(start,state.eMarks[startLine]);
  const open=first.startsWith('$$')?'$$':first.startsWith('\\[')?'\\[':null;
  if (!open) return false;
  const close=open==='$$'?'$$':'\\]';
  let content=first.slice(open.length), next=startLine;
  let end=closingDelimiter(content,close,0);
  while (end<0 && next+1<endLine) {
    next++;
    if (state.sCount[next]<state.blkIndent && !state.isEmpty(next)) return false;
    const line=state.src.slice(state.bMarks[next]+state.tShift[next],state.eMarks[next]);
    const offset=content.length+1;
    content+='\n'+line;
    const found=closingDelimiter(line,close,0);
    if (found>=0) end=offset+found;
  }
  if (end<0 || content.slice(end+close.length).trim() || !content.slice(0,end).trim()) return false;
  if (silent) return true;
  const token=state.push('math_block','',0);
  token.block=true;
  token.content=content.slice(0,end);
  token.map=[startLine,next+1];
  state.line=next+1;
  return true;
}

export function mathPlugin(markdown) {
  markdown.inline.ruler.before('escape','math',inlineMath);
  markdown.block.ruler.before('fence','math',blockMath,{alt:['paragraph','reference','blockquote','list']});
  const slot=(content,display,tag)=>`<${tag} class="markdown-math${display?' markdown-math-display':''}" data-math-display="${display?'block':'inline'}">${markdown.utils.escapeHtml(content)}</${tag}>`;
  markdown.renderer.rules.math_inline=(tokens,index)=>slot(tokens[index].content,tokens[index].meta.display,'span');
  markdown.renderer.rules.math_block=(tokens,index)=>slot(tokens[index].content,true,'div')+'\n';
}

import MarkdownIt from './vendor/markdown-it/markdown-it.mjs';
import katex from './vendor/katex/katex.mjs';
import {mathPlugin} from './markdown-math.js';

const markdown = new MarkdownIt({html:false,linkify:true,breaks:true});
markdown.use(mathPlugin);
const link = markdown.renderer.rules.link_open || ((tokens,index,options,env,renderer) => renderer.renderToken(tokens,index,options));
markdown.renderer.rules.link_open = (tokens,index,options,env,renderer) => {
  tokens[index].attrSet('target','_blank');
  tokens[index].attrSet('rel','noopener noreferrer');
  return link(tokens,index,options,env,renderer);
};
// Course answers link to their sources without loading remote images in the conversation.
markdown.renderer.rules.image = (tokens,index) => markdown.utils.escapeHtml(tokens[index].content || '图片');

export function renderMarkdown(text) { return markdown.render(text); }

/** Typeset only parser-created math slots, after inserting the Markdown HTML. */
export function renderMath(container) {
  for (const node of container.querySelectorAll('[data-math-display]')) {
    const source = node.textContent;
    const displayMode = node.dataset.mathDisplay === 'block';
    node.removeAttribute('data-math-display');
    try {
      // The DOM API sets layout through CSSOM, respecting style-src 'self'.
      katex.render(source,node,{displayMode,throwOnError:true,trust:false,strict:'ignore',maxSize:20,maxExpand:1000,macros:{}});
    } catch {
      node.textContent = source;
      node.classList.add('markdown-math-error');
      node.title = '公式暂时无法排版，已保留原文。';
    }
  }
}

export function renderMarkdownInto(container,text) {
  container.innerHTML = renderMarkdown(text);
  renderMath(container);
}

import MarkdownIt from './vendor/markdown-it/markdown-it.mjs';

const markdown = new MarkdownIt({html:false,linkify:true,breaks:true});
const link = markdown.renderer.rules.link_open || ((tokens,index,options,env,renderer) => renderer.renderToken(tokens,index,options));
markdown.renderer.rules.link_open = (tokens,index,options,env,renderer) => {
  tokens[index].attrSet('target','_blank');
  tokens[index].attrSet('rel','noopener noreferrer');
  return link(tokens,index,options,env,renderer);
};
// Course answers link to their sources without loading remote images in the conversation.
markdown.renderer.rules.image = (tokens,index) => markdown.utils.escapeHtml(tokens[index].content || '图片');

export function renderMarkdown(text) { return markdown.render(text); }

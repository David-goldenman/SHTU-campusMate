import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {renderMarkdown,renderMath,renderMarkdownInto} from '../web/markdown.js';

const force=String.raw`\mathbf F=q(\mathbf E+\mathbf u\times\mathbf B)`;
const hasMath=text=>renderMarkdown(text).includes('data-math-display=');
for (const [input,display] of [
  [`$ ${force} $`,'inline'],[String.raw`\(${force}\)`,'inline'],
  [`$$${force}$$`,'block'],[String.raw`\[${force}\]`,'block'],
  ['$$\n\\begin{aligned}\na&=b\\\\\nc&=d\n\\end{aligned}\n$$','block'],
  ['前文\n$$\nx^2\n$$\n后文','block'],['> $$\nx^2\n$$','block'],
]) assert.match(renderMarkdown(input),new RegExp(`data-math-display="${display}"`));
assert(renderMarkdown(`$ ${force} $`).includes(force),'TeX backslashes must survive Markdown');
for (const source of ['`$x$`','```tex\n$$x$$\n```','    $x$','\\$5 和 \\$10','价格 $5 和 $10','$x','$$\nx^2','\\(x','\\[x']) {
  assert(!hasMath(source),`Code, currency, escaped or unfinished math stays readable: ${source}`);
}
assert(hasMath('**重点**：$x_1 + x_2$'));
assert(hasMath('| 公式 |\n| --- |\n| $x^2$ |'));
assert(hasMath('- $$\n  x^2\n  $$'));
assert(!renderMarkdown('$<img src=x onerror=alert(1)>$').includes('<img'));
// Every streaming prefix can be parsed; a completed formula appears immediately.
const streamed=`正文 $ ${force} $ 后文`;
for (let index=0;index<=streamed.length;index++) assert.doesNotThrow(()=>renderMarkdown(streamed.slice(0,index)));
assert(hasMath(streamed));

// Exercise the real KaTeX DOM renderer with a minimal DOM sink. In particular,
// layout must use style properties, never a CSP-blocked style attribute/string.
class Element {
  constructor(tag,text='') {this.tag=tag;this.text=text;this.children=[];this.attrs={};this.style={};this.className='';this.dataset={};this.classList={add:value=>{this.className+=' '+value;}};}
  appendChild(node) {this.children.push(node);return node;}
  setAttribute(name,value) {assert.notEqual(name,'style');this.attrs[name]=value;}
  removeAttribute(name) {delete this.attrs[name];if(name==='data-math-display')delete this.dataset.mathDisplay;}
  get textContent() {return this.text+this.children.map(node=>node.textContent).join('');}
  set textContent(value) {this.text=value;this.children=[];}
  set innerHTML(value) {assert.equal(value,'');this.textContent='';}
}
const originalDocument=globalThis.document;
try {
  globalThis.document={compatMode:'CSS1Compat',createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),createTextNode:text=>new Element('#text',text),createDocumentFragment:()=>new Element('#fragment')};
  const visit=node=>[node,...node.children.flatMap(visit)];
  const render=(source,display='inline')=>{
    const node=new Element('span',source);node.dataset.mathDisplay=display;
    const container={querySelectorAll:()=>node.dataset.mathDisplay?[node]:[]};
    renderMath(container);
    const previous=node.children[0];renderMath(container);assert.equal(node.children[0],previous,'Hydration must be idempotent');
    return node;
  };
  const forceNode=render(force), nodes=visit(forceNode);
  assert(nodes.some(node=>node.className==='katex'));
  assert(nodes.some(node=>node.tag==='math'));
  assert(nodes.some(node=>node.className.includes('mathbf')),'Vectors retain their bold typeface');
  assert(nodes.some(node=>Object.keys(node.style).length),'Layout is applied through DOM style properties');
  const fraction=visit(render(String.raw`\frac{1}{2}+\sqrt{x}+\begin{pmatrix}a&b\\c&d\end{pmatrix}`,'block'));
  for (const tag of ['mfrac','msqrt','mtable']) assert(fraction.some(node=>node.tag===tag));
  for (const source of [String.raw`\frac{1}{`,String.raw`\def\a{\a}\a`]) {
    const node=render(source);assert.equal(node.textContent,source);assert(node.className.includes('markdown-math-error'));
  }
  for (const source of [String.raw`\href{javascript:alert(1)}{x}`,String.raw`\includegraphics{https://example.edu/tracker.png}`,String.raw`\htmlStyle{background:url(https://example.edu/tracker)}{x}`,'<script>alert(1)</script>']) {
    const nodes=visit(render(source));
    assert(!nodes.some(node=>['a','img','script'].includes(node.tag)||node.attrs.href||node.attrs.src));
    assert(!nodes.some(node=>Object.values(node.style).some(value=>String(value).includes('url('))));
  }
  render(String.raw`\gdef\secret{injected}\secret`);
  assert(render(String.raw`\secret`).className.includes('markdown-math-error'),'Formula macros cannot leak into other messages');
  let markup;
  renderMarkdownInto({set innerHTML(value){markup=value;},querySelectorAll:()=>[]},'$x$');
  assert(markup.includes('data-math-display'));
} finally {
  if (originalDocument===undefined) delete globalThis.document;else globalThis.document=originalDocument;
}
const shell=await readFile(new URL('../web/index.html',import.meta.url),'utf8');
assert(shell.includes('/assets/markdown.css'));
const css=await readFile(new URL('../web/markdown.css',import.meta.url),'utf8');
assert(css.includes('vendor/katex/katex.min.css'));
console.log('math: TeX delimiters, streaming, code/currency, DOM layout, accessible math, fractions/matrices, safe failures and macro isolation passed');

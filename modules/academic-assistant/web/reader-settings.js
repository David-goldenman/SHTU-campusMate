export async function showReaderSettings(context) {
  const value = await context.api('/reader/settings');
  if(context.signal.aborted)return;
  const e = context.ui.escape, form = document.createElement('form');
  form.className = 'campus-form';
  form.innerHTML = `<label>图片与扫描课件<select name="mode"><option value="auto">自动选择</option><option value="vision">优先直接识图</option><option value="local">仅文字提取与本地 OCR</option></select></label>
    <p class="field-hint">自动模式仅使用已确认支持图片且效果合适的模型，其余情况使用本地解析。此选项控制图片处理；提取的文字仍会随问题交给对话模型。</p>
    <p class="field-hint">${value.vision.ready ? '图片模型：' + e(value.vision.model) + ' · ' + e(value.vision.base_url) : '图片模型尚未就绪。'} <a href="#settings?tab=ai" data-model-settings>配置图片模型 →</a></p>
    <label class="checkbox-label"><input type="checkbox" name="fallback" ${value.fallback ? 'checked' : ''}>识图不可用或失败时，回退到本地解析</label>
    <label>本地 OCR<select name="ocr_backend"><option value="windows">Windows 系统 OCR</option><option value="docling">Docling 增强解析</option></select></label>
    <div data-docling><label>Docling 的 Python 环境<input name="docling_python" value="${e(value.docling_python)}" maxlength="2048" placeholder="已安装 Docling 的 Python 可执行文件绝对路径"></label><p class="field-hint">留空使用应用环境。Docling 需要单独安装并准备模型；它在本机运行。首次准备方法见项目的文档读取说明。</p></div>
    <label>每次最多处理页数<select name="max_pages">${[1,2,3,4].map(n=>`<option value="${n}">${n} 页</option>`).join('')}</select></label>
    <p class="field-hint">较少的页数可缩短等待并减少识图用量。未读页会明确列出，继续读取时复用已有结果。</p>
    <p class="danger-text" data-reader-error role="alert"></p><button type="submit" class="button button-primary">保存读取设置</button>`;
  const dialog = context.ui.dialog('资料读取', form), fields = form.elements;
  context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
  for(const key of ['mode','ocr_backend','max_pages'])fields[key].value=String(value[key]);
  const update=()=>{form.querySelector('[data-docling]').hidden=fields.ocr_backend.value!=='docling';fields.fallback.disabled=fields.mode.value==='local';};
  fields.ocr_backend.onchange=fields.mode.onchange=update;update();
  form.querySelector('[data-model-settings]').onclick=()=>dialog.close();
  form.onsubmit=context.ui.safeAction(form.querySelector('[type=submit]'),async()=>{
    const body={mode:fields.mode.value,fallback:fields.fallback.checked,ocr_backend:fields.ocr_backend.value,
      docling_python:fields.docling_python.value.trim(),max_pages:Number(fields.max_pages.value)};
    try {await context.api('/reader/settings',{method:'PUT',body});context.ui.toast('资料读取设置已保存。');dialog.close();}
    catch(cause){if(!context.signal.aborted)form.querySelector('[data-reader-error]').textContent=cause.message;}
  });
}

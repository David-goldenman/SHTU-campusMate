export function qqConnection(config, escape) {
  return `<div class="gm-qq-setup">
    <p class="gm-hint">QQ 通过本机连接助手 NapCat 接入。首次使用先完成下方配置，随后连接并选择课程群。</p>
    <details class="gm-qq-guide" ${config.connected?'':'open'}>
      <summary>首次连接：3 步准备</summary>
      <ol>
        <li><strong>启动 NapCat，登录本人 QQ</strong><p>按启动提示打开管理页面，扫码或确认登录。<a href="https://napneko.github.io/guide/boot/Shell" target="_blank" rel="noopener noreferrer">Windows 安装与启动说明 ↗</a></p></li>
        <li><strong>开启 HTTP 服务端</strong><p>进入“网络配置 → 新建 → HTTP 服务端”。Host 填 <code>127.0.0.1</code>，端口可用 <code>3000</code>；在 Token 中设置一段连接口令，保存并启用。</p></li>
        <li><strong>填写同一地址和连接口令</strong><p>把刚设置的 HTTP 服务端 Token 填到下方。这里使用的是接口连接口令，与 QQ 密码、管理页面登录口令分开。</p></li>
      </ol>
      <div class="gm-source-actions"><a class="button button-secondary" href="http://127.0.0.1:6099/webui/" target="_blank" rel="noopener noreferrer">打开 NapCat 管理页 ↗</a><a href="https://napneko.github.io/config/basic" target="_blank" rel="noopener noreferrer">官方配置说明 ↗</a></div>
      <p class="gm-hint">管理页通常使用 6099 端口；打不开时，请查看 NapCat 启动提示中的实际地址。已有 OneBot HTTP 服务可直接填写下方信息。</p>
    </details>
    <form data-connect="qq">
      <label for="gm-qq-url">QQ 接口地址</label>
      <input id="gm-qq-url" name="base_url" type="url" value="${escape(config.base_url||'http://127.0.0.1:3000')}" aria-describedby="gm-qq-url-help" required>
      <p class="gm-hint" id="gm-qq-url-help">填写 HTTP 服务端地址，例如 http://127.0.0.1:3000。端口与 NapCat 中设置的一致。</p>
      <label for="gm-qq-token">连接口令（Access Token）</label>
      <div class="gm-secret-row"><input id="gm-qq-token" name="access_token" type="password" autocomplete="new-password" spellcheck="false" placeholder="粘贴 HTTP 服务端的 Token" aria-describedby="gm-qq-token-help" required><button type="button" class="button button-secondary" data-toggle-token aria-controls="gm-qq-token" aria-pressed="false">显示口令</button></div>
      <p class="gm-hint" id="gm-qq-token-help">在 NapCat“网络配置 → HTTP 服务端 → Token”中设置或复制。连接成功后加密保存在本机。</p>
      <label class="gm-check"><input name="consent" type="checkbox" required>我授权读取本人 QQ 中随后选择的群聊。</label>
      <button class="button button-primary" type="submit">连接 QQ 并选择群聊</button>
      <p class="gm-feedback" role="status" aria-live="polite" data-connection-feedback></p>
    </form>
  </div>`;
}

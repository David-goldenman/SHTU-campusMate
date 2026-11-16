# KaTeX

Version 0.19.0, MIT. The ESM bundle, minified stylesheet, fonts and LICENSE are copied unchanged from the official npm release:
https://registry.npmjs.org/katex/-/katex-0.19.0.tgz

Served locally; no CDN or external font requests are required. Update these files together. `web/markdown-math.js` recognizes math delimiters; `web/markdown.js` calls the DOM renderer with untrusted input disabled, bounded sizes/expansion and per-expression macros. DOM style properties preserve the application's `style-src 'self'` policy. Do not replace the DOM call with `renderToString()` inserted into live HTML: CSP would block its inline layout styles.

Official API and security guidance: https://katex.org/docs/api.html and https://katex.org/docs/security.html

import {sourcePanel, records, link} from '/assets/campus.js';

export function mount(container, context) {
  const e = context.ui.escape;
  return sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = '<details><summary>已加入课程</summary>' + records(snapshot.data.courses,e) + '</details><div class="campus-list">' + snapshot.data.posts.map(item => `<article class="campus-item"><h4>${link(item.url,item.title,e)}</h4><button class="text-button" type="button" data-post="${e(item.id)}">阅读正文与回复</button></article>`).join('') + '</div><div class="campus-detail" data-detail aria-live="polite"></div>';
    body.querySelectorAll('[data-post]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
      const item = snapshot.data.posts.find(item => item.id === button.dataset.post);
      const post = await context.api('/post?' + new URLSearchParams({course_id:item.source_course_id,post_id:item.source_id}));
      body.querySelector('[data-detail]').innerHTML = `<article class="campus-item"><h3>${e(post.title)}</h3><p>${e(post.body_text)}</p>${post.replies.map(reply => '<p>' + e(reply.text) + '</p>').join('')}</article>`;
    }));
  });
}

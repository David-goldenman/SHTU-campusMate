// Inspired by the dry reversals in the user-provided openclaw-quirks.md.
// These Chinese lines are adapted for the campus workspace.
const lines = [
  "知识没有尽头，浏览器的内存有。",
  "你的计划很完整。现实正在申请修改权限。",
  "我把存在主义危机排到了周末。工作日已经满了。",
  "宇宙还在膨胀，你的待办清单也不甘示弱。",
  "你负责提出宏大的问题，我负责先找到那个 PDF。",
  "你说“最后一个问题”时，宇宙又多了一条支线。",
  "“以后会用到”——收藏夹里最受欢迎的科幻题材。",
  "理论上，时间是相对的。截止日期显然没读过这篇论文。",
  "有些问题交给时间。时间回复：今晚十二点。",
  "人类能观测百亿年前的星光，偶尔找不到昨天的文件。",
  "你的收藏夹已经博览群书。你们俩可以交流一下。",
  "我负责找资料，你负责维持“我早就知道”的表情。",
  "想法负责仰望星空，日历负责指出：明天早八。",
  "宇宙没有标准答案。幸好它也不收作业。",
  "我不评判文件名。final_最终版_真的不改了_v8 除外。",
  "有些计划是路线图，有些是平行宇宙的旅游攻略。",
  "别担心，“完全没看懂”也是一种完整的阅读体验。",
  "资料不会自己变成知识。这项功能宇宙还没做完。",
  "你的待办清单很有想象力，尤其是在估计用时的时候。",
  "为了防止知识溜走，你又把它存进了一个找不到的文件夹。"
];
let selectedLine;

export function openingLine() {
  if (selectedLine) return selectedLine;
  const key = 'campus.opening-line.v1';
  try { selectedLine = sessionStorage.getItem(key); } catch {}
  if (!lines.includes(selectedLine)) {
    selectedLine = lines[Math.floor(Math.random() * lines.length)];
    try { sessionStorage.setItem(key, selectedLine); } catch {}
  }
  return selectedLine;
}

const node = document.querySelector('[data-opening-line]');
if (node) node.textContent = openingLine();

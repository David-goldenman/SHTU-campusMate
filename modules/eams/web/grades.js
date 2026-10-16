const SEASONS = {1: '秋季', 2: '春季', 3: '夏季'};
const ORDER = {point: 0, pass: 1, np: 2};

export const TERMS = [['all', '全部学期'], ['秋季', '秋季学期'], ['春季', '春季学期'], ['夏季', '夏季学期']];
export const KINDS = [['all', '全部成绩'], ['point', '绩点'], ['pass', 'P'], ['np', 'NP']];
export const SORTS = [['point', '绩点（高到低，P、NP 在后）'], ['semester', '学期（新在前）'], ['credits', '学分（高到低）'], ['credits-low', '学分（低到高）']];

function split(item) {
  const values = String(item.term || '').split('-');
  return values.length === 3 && /^\d{4}$/.test(values[0]) && SEASONS[values[2]] ? values : null;
}

export function season(item) {
  const values = split(item);
  return values ? SEASONS[values[2]] : '';
}

export function label(item) {
  const values = split(item);
  return values ? values[0] + '-' + values[1] + '学年' + SEASONS[values[2]] : String(item.term || '');
}

export function kind(item) {
  if (typeof item.point === 'number') return 'point';
  return /^P/i.test(String(item.score || '').trim()) ? 'pass' : 'np';
}

const sizeOf = item => (typeof item.credits === 'number' ? item.credits : -1);
const pointOf = item => (typeof item.point === 'number' ? item.point : -1);
const rankOf = item => { const values = split(item); return values ? Number(values[0]) * 10 + Number(values[2]) : -1; };
const byTitle = (a, b) => String(a.title || '').localeCompare(String(b.title || ''), 'zh');
const ORDERS = {
  point: (a, b) => ORDER[kind(a)] - ORDER[kind(b)] || pointOf(b) - pointOf(a) || sizeOf(b) - sizeOf(a) || byTitle(a, b),
  semester: (a, b) => rankOf(b) - rankOf(a) || byTitle(a, b),
  credits: (a, b) => sizeOf(b) - sizeOf(a) || pointOf(b) - pointOf(a) || byTitle(a, b),
  'credits-low': (a, b) => sizeOf(a) - sizeOf(b) || pointOf(b) - pointOf(a) || byTitle(a, b),
};

export function list(courses, options = {}) {
  const term = options.term || 'all';
  const wanted = options.kind || 'all';
  return (courses || [])
    .filter(item => (term === 'all' || season(item) === term) && (wanted === 'all' || kind(item) === wanted))
    .sort(ORDERS[options.sort] || ORDERS.point);
}

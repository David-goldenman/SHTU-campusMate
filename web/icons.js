const paths = {
  '◫':'M3 3h18v18H3z M3 9h18 M9 9v12',
  '✉':'M3 5h18v14H3z M3 6l9 7 9-7',
  '▦':'M3 5h18v16H3z M3 11h18 M8 3v4 M16 3v4 M8 11v10 M16 11v10',
  '▤':'M4 3h16v18H4z M8 7h8 M8 11h8 M8 15h5',
  '✓':'M9 4h11v16H4V9 M2 5l3 3 6-6',
  '◎':'M4 9l8-6 8 6 M5 10v10h14V10 M9 20v-6h6v6',
  '◌':'M5 16V9a7 7 0 0 1 14 0v7l2 3H3z M10 22h4',
  '✦':'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  '✧':'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  '▥':'M3 4h7v16H3z M14 4h7v16h-7z M6 8h1 M17 8h1',
  '◷':'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l4 2',
  '✎':'M4 20l4-1 12-12-3-3L5 16z M14 7l3 3 M12 20h9',
  '☷':'M5 16V9a7 7 0 0 1 14 0v7l2 3H3z M10 22h4',
  '⚙':'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
};

export function icon(glyph) {
  return '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + (paths[glyph] || 'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h5') + '"/></svg>';
}

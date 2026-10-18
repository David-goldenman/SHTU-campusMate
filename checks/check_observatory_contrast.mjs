import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Measure the theme's actual tokens, including composite course and urgency fills.
const css = await readFile(new URL('../web/themes/observatory.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/(--[\w-]+):\s*(#[\da-f]{6})\b/gi)].map(([, name, color]) => [name, color]));
const rgb = color => color.slice(1).match(/../g).map(channel => parseInt(channel, 16) / 255);
const luminance = color => rgb(color).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
const contrast = (foreground, background) => {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
  return (values[1] + .05) / (values[0] + .05);
};
const mix = (accent, surface, amount) => '#' + rgb(accent).map((channel, index) => Math.round((channel * amount + rgb(surface)[index] * (1 - amount)) * 255).toString(16).padStart(2, '0')).join('');
let minimum = Infinity;
const readable = (foreground, background, label, threshold = 4.5) => {
  const ratio = contrast(foreground, background);
  if (threshold === 4.5) minimum = Math.min(minimum, ratio);
  assert.ok(ratio >= threshold, `${label}: ${ratio.toFixed(2)}:1 below ${threshold}:1`);
};
const surfaces = ['--bg', '--paper', '--surface-low', '--surface', '--surface-raised', '--primary-container'];
for (const surface of surfaces) {
  for (const text of ['--text', '--muted', '--link']) readable(tokens[text], tokens[surface], `${text} on ${surface}`);
}
readable(tokens['--night-button-text'], tokens['--night-button-bg'], 'Primary button');
readable(tokens['--rail-text'], tokens['--rail-bg'], 'Sidebar text');
readable(tokens['--rail-muted'], tokens['--rail-bg'], 'Sidebar secondary text');
readable(tokens['--rail-active-text'], tokens['--rail-active-bg'], 'Sidebar selected label');
for (const [foreground, background] of [['--nord11', '--night-danger-bg'], ['--nord13', '--night-warning-bg'], ['--nord14', '--night-success-bg']]) readable(tokens[foreground], tokens[background], `${foreground} feedback`);
for (const surface of ['--paper', '--surface-raised']) readable(tokens['--outline'], tokens[surface], `Control boundary on ${surface}`, 3);
for (const accent of ['#ffffff', '#000000', '#ff0000', '#00ff00', '#0000ff', tokens['--nord13']]) {
  for (const text of ['--text', '--muted']) readable(tokens[text], mix(accent, tokens['--paper'], .18), `${text} on a semantic course fill`);
}
assert.match(css, /:root\[data-art-theme="observatory"\]/);
assert.match(css, /color-scheme:dark/);
console.log(`Observatory contrast: passed (minimum normal text ${minimum.toFixed(2)}:1).`);

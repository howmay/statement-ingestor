#!/usr/bin/env python3
"""Render output/expenses_*.csv into a single self-contained output/report.html.

Usage: python scripts/report.py [output_dir]
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime

COLUMNS = ['date', 'income', 'expense', 'currency', 'expense_name', 'expense_type', 'source', 'source_file', 'balance']


def load_rows(output_dir: str) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(output_dir, 'expenses_*.csv'))):
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                rows.append({k: (r.get(k) or '') for k in COLUMNS})
    return rows


TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expense Report</title>
<style>
:root { color-scheme: light; --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --s1:#2a78d6; --s2:#eb6834; --good:#006300; --bad:#d03b3b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --s1:#3987e5; --s2:#d95926; --good:#0ca30c; --bad:#e66767; } }
:root[data-theme="dark"] { color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10); --s1:#3987e5; --s2:#d95926; --good:#0ca30c; --bad:#e66767; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink); font: 14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 0 0 10px; color: var(--ink2); font-weight: 600; }
.sub { color: var(--muted); margin-bottom: 16px; }
.filters { display:flex; flex-wrap:wrap; gap:8px; margin: 0 0 16px; }
.filters select, .filters input { font: inherit; padding: 6px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--ink); min-width: 120px; }
.filters input { flex: 1 1 160px; }
.grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.tile .label { color: var(--muted); font-size: 12px; } .tile .value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile .value.in { color: var(--good); } .tile .value.out { color: var(--bad); }
.num { font-variant-numeric: tabular-nums; text-align: right; }
table { width:100%; border-collapse: collapse; } th, td { padding: 6px 8px; border-bottom: 1px solid var(--grid); text-align:left; vertical-align: top; }
th { color: var(--muted); font-weight: 500; font-size: 12px; position: sticky; top: 0; background: var(--surface); white-space: nowrap; }
tfoot td { font-weight: 600; border-top: 2px solid var(--axis); }
td:first-child { white-space: nowrap; }
.tablewrap { max-height: 520px; overflow: auto; }
svg text { fill: var(--muted); font-size: 11px; } svg .axis { stroke: var(--axis); } svg .grid { stroke: var(--grid); }
.legend { display:flex; gap:14px; font-size:12px; color:var(--ink2); margin-bottom:6px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
.tip { position: fixed; pointer-events:none; background: var(--surface); color: var(--ink); border:1px solid var(--border); border-radius:6px; padding:6px 8px; font-size:12px; box-shadow: 0 2px 8px rgba(0,0,0,.15); display:none; z-index: 9; }
.note { color: var(--muted); font-size: 12px; margin-top: 8px; }
.hbar rect:hover, .vbar rect:hover { opacity: .8; }
</style>
</head>
<body>
<main>
<h1>收支報表</h1>
<div class="sub" id="sub"></div>
<div class="filters">
  <select id="f-cur"></select><select id="f-month"></select><select id="f-src"></select><select id="f-type"></select>
  <input id="f-q" type="search" placeholder="關鍵字（消費名目）">
</div>
<div class="grid">
  <div class="card tile"><div class="label">收入</div><div class="value in" id="t-in"></div></div>
  <div class="card tile"><div class="label">支出</div><div class="value out" id="t-out"></div></div>
  <div class="card tile"><div class="label">淨額（收入 − 支出）</div><div class="value" id="t-net"></div></div>
  <div class="card tile"><div class="label">筆數</div><div class="value" id="t-n"></div></div>
</div>
<div class="grid">
  <div class="card" style="grid-column: 1 / -1"><h2>帳戶餘額（各帳戶最近一筆對帳單餘額）</h2><div id="bal"></div><div class="note" id="bal-note"></div></div>
</div>
<div class="card" style="margin-bottom:12px"><h2>每月收支</h2>
  <div class="legend"><span><i style="background:var(--s1)"></i>收入</span><span><i style="background:var(--s2)"></i>支出</span></div>
  <div id="c-month"></div></div>
<div class="grid">
  <div class="card"><h2>支出依類型</h2><div id="c-type"></div></div>
  <div class="card"><h2>支出依來源</h2><div id="c-src"></div></div>
</div>
<div class="card"><h2>明細</h2><div class="tablewrap"><table id="tbl"></table></div></div>
</main>
<div class="tip" id="tip"></div>
<script>
const ROWS = __DATA__;
const $ = s => document.querySelector(s);
const fmt = n => n.toLocaleString('zh-Hant', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const num = s => s ? parseFloat(s) : 0;
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const month = r => r.date.slice(0, 7);
const uniq = (arr, key) => [...new Set(arr.map(key).filter(Boolean))].sort();

function fill(sel, values, all, counts) {
  sel.innerHTML = `<option value="">${all}</option>` + values.map(v => `<option value="${esc(v)}">${esc(v)}${counts ? ` (${counts[v]})` : ''}</option>`).join('');
}
const curCounts = {}; ROWS.forEach(r => curCounts[r.currency] = (curCounts[r.currency] || 0) + 1);
const currencies = uniq(ROWS, r => r.currency).sort((a, b) => curCounts[b] - curCounts[a]);
fill($('#f-cur'), currencies, '全部幣別', curCounts); $('#f-cur').value = currencies[0] || '';
fill($('#f-month'), uniq(ROWS, month), '全部月份');
fill($('#f-src'), uniq(ROWS, r => r.source), '全部來源');
fill($('#f-type'), uniq(ROWS, r => r.expense_type), '全部類型');
const dates = uniq(ROWS, r => r.date);
$('#sub').textContent = `期間 ${dates[0] || '-'} ～ ${dates[dates.length - 1] || '-'}，共 ${ROWS.length} 筆。不同幣別分開計算，不做匯率換算。`;

function filtered() {
  const c = $('#f-cur').value, m = $('#f-month').value, s = $('#f-src').value, t = $('#f-type').value, q = $('#f-q').value.trim().toLowerCase();
  return ROWS.filter(r => (!c || r.currency === c) && (!m || month(r) === m) && (!s || r.source === s) && (!t || r.expense_type === t) && (!q || r.expense_name.toLowerCase().includes(q)));
}

const tip = $('#tip');
function hover(el, html) {
  el.addEventListener('mousemove', e => { tip.innerHTML = html; tip.style.display = 'block'; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY + 12) + 'px'; });
  el.addEventListener('mouseleave', () => tip.style.display = 'none');
}

function monthChart(rows) {
  const by = {}; rows.forEach(r => { const m = month(r); by[m] = by[m] || {i: 0, o: 0}; by[m].i += num(r.income); by[m].o += num(r.expense); });
  const months = Object.keys(by).sort(); const W = 1040, H = 220, L = 70, B = 30, T = 10;
  const max = Math.max(1, ...months.flatMap(m => [by[m].i, by[m].o]));
  const bw = (W - L - 10) / Math.max(1, months.length), y = v => T + (H - T - B) * (1 - v / max);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" class="vbar">`;
  for (let k = 0; k <= 4; k++) { const v = max * k / 4, yy = y(v); s += `<line class="grid" x1="${L}" x2="${W - 10}" y1="${yy}" y2="${yy}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end">${v >= 1000 ? (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : v.toFixed(0)}</text>`; }
  s += `<line class="axis" x1="${L}" x2="${W - 10}" y1="${y(0)}" y2="${y(0)}"/>`;
  months.forEach((m, i) => {
    const x0 = L + i * bw + bw * 0.15, w = Math.max(2, bw * 0.32);
    const bar = (v, x, c, label) => `<rect data-tip="${esc(m)} ${label} ${fmt(v)}" x="${x}" y="${y(v)}" width="${w}" height="${Math.max(0, y(0) - y(v))}" fill="var(${c})" rx="3"/>`;
    s += bar(by[m].i, x0, '--s1', '收入') + bar(by[m].o, x0 + w + 2, '--s2', '支出');
    s += `<text x="${L + i * bw + bw / 2}" y="${H - 10}" text-anchor="middle">${esc(m)}</text>`;
  });
  return s + '</svg>';
}

function hbarChart(rows, key) {
  const by = {}; rows.forEach(r => { const k = r[key] || '—'; by[k] = (by[k] || 0) + num(r.expense); });
  const items = Object.entries(by).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const max = Math.max(1, ...items.map(([, v]) => v)), W = 480, rh = 26, L = 150, H = items.length * rh + 6;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" class="hbar">`;
  items.forEach(([k, v], i) => {
    const w = (W - L - 70) * v / max, yy = i * rh + 4;
    s += `<text x="${L - 8}" y="${yy + 15}" text-anchor="end">${esc(k.length > 18 ? k.slice(0, 17) + '…' : k)}</text>`;
    s += `<rect data-tip="${esc(k)} ${fmt(v)}" x="${L}" y="${yy}" width="${Math.max(2, w)}" height="${rh - 8}" fill="var(--s2)" rx="3"/>`;
    s += `<text x="${L + Math.max(2, w) + 6}" y="${yy + 15}">${fmt(v)}</text>`;
  });
  return s + (items.length ? '' : '<text x="8" y="18">無支出</text>') + '</svg>';
}

function balances() {
  const latest = {};
  ROWS.filter(r => r.balance !== '').forEach(r => { const k = r.source + '|' + r.currency; if (!latest[k] || r.date >= latest[k].date) latest[k] = r; });
  const items = Object.values(latest).sort((a, b) => a.currency.localeCompare(b.currency) || a.source.localeCompare(b.source));
  if (!items.length) { $('#bal').innerHTML = '<div class="note">目前的 CSV 沒有餘額欄位。重新執行 main.py 後，台新、富邦帳戶、HSBC SG／DBS SG 帳戶的對帳單餘額會寫入 balance 欄。</div>'; return; }
  const sums = {}; items.forEach(r => sums[r.currency] = (sums[r.currency] || 0) + num(r.balance));
  $('#bal').innerHTML = `<table><thead><tr><th>帳戶</th><th>幣別</th><th>對帳單日期</th><th class="num">餘額</th></tr></thead><tbody>` +
    items.map(r => `<tr><td>${esc(r.source)}</td><td>${esc(r.currency)}</td><td>${esc(r.date)}</td><td class="num">${fmt(num(r.balance))}</td></tr>`).join('') +
    `</tbody><tfoot>` + Object.entries(sums).map(([c, v]) => `<tr><td colspan="3">資產合計 ${esc(c)}</td><td class="num">${fmt(v)}</td></tr>`).join('') + `</tfoot></table>`;
  $('#bal-note').textContent = '只列對帳單文字裡有餘額欄的帳戶（台新、富邦、HSBC SG、DBS SG）；HSBC Taiwan Bank 的 parser 尚未抓餘額，信用卡帳單沒有餘額概念。';
}

function render() {
  const rows = filtered();
  const inc = rows.reduce((a, r) => a + num(r.income), 0), out = rows.reduce((a, r) => a + num(r.expense), 0);
  $('#t-in').textContent = fmt(inc); $('#t-out').textContent = fmt(out); $('#t-net').textContent = fmt(inc - out); $('#t-n').textContent = rows.length;
  $('#c-month').innerHTML = monthChart(rows); $('#c-type').innerHTML = hbarChart(rows, 'expense_type'); $('#c-src').innerHTML = hbarChart(rows, 'source');
  document.querySelectorAll('rect[data-tip]').forEach(el => hover(el, esc(el.dataset.tip)));
  const sorted = [...rows].sort((a, b) => b.date.localeCompare(a.date));
  $('#tbl').innerHTML = `<thead><tr><th>日期</th><th>消費名目</th><th>類型</th><th>來源</th><th>幣別</th><th class="num">收入</th><th class="num">支出</th><th class="num">餘額</th></tr></thead><tbody>` +
    sorted.map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.expense_name)}</td><td>${esc(r.expense_type)}</td><td>${esc(r.source)}</td><td>${esc(r.currency)}</td><td class="num">${r.income ? fmt(num(r.income)) : ''}</td><td class="num">${r.expense ? fmt(num(r.expense)) : ''}</td><td class="num">${r.balance ? fmt(num(r.balance)) : ''}</td></tr>`).join('') +
    `</tbody><tfoot><tr><td colspan="5">合計（${rows.length} 筆）</td><td class="num">${fmt(inc)}</td><td class="num">${fmt(out)}</td><td></td></tr></tfoot>`;
}
document.querySelectorAll('.filters select, .filters input').forEach(el => el.addEventListener('input', render));
balances(); render();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    output_dir = (argv or sys.argv[1:] or ['output'])[0]
    rows = load_rows(output_dir)
    data = json.dumps(rows, ensure_ascii=False).replace('</', '<\\/')
    html = TEMPLATE.replace('__DATA__', data)
    out = os.path.join(output_dir, 'report.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"{out}: {len(rows)} rows, generated {datetime.now():%Y-%m-%d %H:%M}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

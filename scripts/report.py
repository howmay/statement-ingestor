#!/usr/bin/env python3
"""Render output/expenses_*.csv + output/balances.csv into one self-contained output/report.html.

Usage: python scripts/report.py [output_dir]
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime

COLUMNS = ['date', 'income', 'expense', 'currency', 'expense_name', 'expense_type', 'source', 'source_file', 'balance']
BALANCE_COLUMNS = ['date', 'bank', 'account', 'currency', 'balance', 'kind', 'source_file']


def load(output_dir: str, pattern: str, columns: list[str]) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(output_dir, pattern))):
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                rows.append({k: (r.get(k) or '') for k in columns})
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
.sub { color: var(--muted); margin-bottom: 14px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; margin-bottom: 12px; }
.labels { display:flex; justify-content: space-between; font-weight: 600; }
.labels span { color: var(--muted); font-weight: 400; margin: 0 8px; }
.slider { position: relative; height: 32px; }
.slider input[type=range] { position:absolute; left:0; right:0; top:0; width:100%; margin:0; height: 32px; background: none; pointer-events: none; -webkit-appearance: none; appearance: none; }
.slider input[type=range]::-webkit-slider-runnable-track { height: 4px; background: var(--grid); border-radius: 2px; margin-top: 14px; }
.slider input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; pointer-events: auto; width: 20px; height: 20px; margin-top: -8px; border-radius: 50%; background: var(--s1); border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--border); cursor: grab; }
.slider input[type=range]::-moz-range-track { height: 4px; background: var(--grid); border-radius: 2px; }
.slider input[type=range]::-moz-range-thumb { pointer-events: auto; width: 18px; height: 18px; border-radius: 50%; background: var(--s1); border: 2px solid var(--surface); cursor: grab; }
.slider .fill { position:absolute; top: 14px; height: 4px; background: var(--s1); border-radius: 2px; pointer-events:none; }
.filters { display:flex; flex-wrap:wrap; gap:8px; margin-top: 10px; }
.filters select, .filters input { font: inherit; padding: 6px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--ink); min-width: 120px; }
.filters input { flex: 1 1 160px; }
.tiles { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.tile .label { color: var(--muted); font-size: 12px; } .tile .value { font-size: 22px; font-weight: 600; margin-top: 2px; }
.tile .value.in { color: var(--good); } .tile .value.out { color: var(--bad); }
.cur { font-size: 13px; font-weight: 600; color: var(--ink2); margin: 10px 0 6px; }
.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
table { width:100%; border-collapse: collapse; } th, td { padding: 6px 8px; border-bottom: 1px solid var(--grid); text-align:left; vertical-align: top; }
th { color: var(--muted); font-weight: 500; font-size: 12px; position: sticky; top: 0; background: var(--surface); white-space: nowrap; }
td:first-child { white-space: nowrap; }
tfoot td { font-weight: 600; border-top: 2px solid var(--axis); }
.tablewrap { max-height: 480px; overflow: auto; }
svg text { fill: var(--muted); font-size: 11px; } svg .axis { stroke: var(--axis); } svg .grid { stroke: var(--grid); }
.legend { display:flex; gap:14px; font-size:12px; color:var(--ink2); margin-bottom:6px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
.tip { position: fixed; pointer-events:none; background: var(--surface); color: var(--ink); border:1px solid var(--border); border-radius:6px; padding:6px 8px; font-size:12px; box-shadow: 0 2px 8px rgba(0,0,0,.15); display:none; z-index: 9; }
.note { color: var(--muted); font-size: 12px; margin-top: 8px; }
rect[data-tip]:hover, circle[data-tip]:hover { opacity: .8; }
details summary { cursor: pointer; color: var(--ink2); font-weight: 600; font-size: 15px; }
.liab { color: var(--bad); }
</style>
</head>
<body>
<main>
<h1>收支與資產</h1>
<div class="sub" id="sub"></div>

<div class="card">
  <div class="labels"><b id="r-from"></b><span>拖拉兩端選擇期間</span><b id="r-to"></b></div>
  <div class="slider"><div class="fill" id="r-fill"></div><input type="range" id="r-a" min="0" step="1"><input type="range" id="r-b" min="0" step="1"></div>
  <div class="filters">
    <select id="f-cur"></select><select id="f-src"></select>
    <input id="f-q" type="search" placeholder="關鍵字（消費名目）">
    <label style="display:flex;align-items:center;gap:6px"><input id="f-xfer" type="checkbox" checked> 收支排除轉帳（Transfer）</label>
  </div>
</div>

<div class="card"><h2>淨資產（期間結束時，各帳戶最近一期對帳單）</h2><div id="assets"></div>
  <div class="note">資產＝帳戶餘額、投資市值；負債＝信用卡本期應繳、借款。各幣別分開，不做匯率換算。銀行若同時給「總計」與各帳戶明細，只計總計一次。超過 6 個月沒有新對帳單的帳戶會列出但不計入合計。</div></div>

<div class="card"><h2>淨資產走勢</h2><div id="c-assets"></div></div>

<div class="card"><h2>期間收支</h2><div id="tiles"></div></div>

<div class="card"><h2>每月收支</h2>
  <div class="legend"><span><i style="background:var(--s1)"></i>收入</span><span><i style="background:var(--s2)"></i>支出</span></div>
  <div id="c-month"></div></div>

<div class="card"><h2>支出依來源</h2><div id="c-src"></div></div>

<div class="card"><details><summary>明細</summary><div class="tablewrap" style="margin-top:10px"><table id="tbl"></table></div></details></div>
</main>
<div class="tip" id="tip"></div>
<script>
const ROWS = __DATA__;
const BAL = __BALANCES__;
const $ = s => document.querySelector(s);
const fmt = n => n.toLocaleString('zh-Hant', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt0 = n => n.toLocaleString('zh-Hant', {maximumFractionDigits: 0});
const num = s => s ? parseFloat(s) : 0;
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const month = r => r.date.slice(0, 7);
const uniq = (arr, key) => [...new Set(arr.map(key).filter(Boolean))].sort();
const yTick = v => Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : Math.abs(v) >= 1000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(0);

// ---- month axis = union of transaction months and balance months ----
const MONTHS = uniq([...ROWS, ...BAL], month);
const a = $('#r-a'), b = $('#r-b');
a.max = b.max = Math.max(0, MONTHS.length - 1); a.value = 0; b.value = MONTHS.length - 1;
function rangeMonths() { const lo = Math.min(+a.value, +b.value), hi = Math.max(+a.value, +b.value); return [MONTHS[lo] || '', MONTHS[hi] || '']; }
function paintRange() {
  const [lo, hi] = rangeMonths(); $('#r-from').textContent = lo; $('#r-to').textContent = hi;
  const n = Math.max(1, MONTHS.length - 1), l = Math.min(+a.value, +b.value) / n * 100, r = Math.max(+a.value, +b.value) / n * 100;
  $('#r-fill').style.left = l + '%'; $('#r-fill').style.width = (r - l) + '%';
}

function fill(sel, values, all) { sel.innerHTML = `<option value="">${all}</option>` + values.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join(''); }
fill($('#f-cur'), uniq(ROWS, r => r.currency), '全部幣別');
fill($('#f-src'), uniq(ROWS, r => r.source), '全部來源');
$('#sub').textContent = `交易 ${ROWS.length} 筆（${MONTHS[0] || '-'} ～ ${MONTHS[MONTHS.length - 1] || '-'}），對帳單餘額 ${BAL.length} 筆。`;

function filtered() {
  const [lo, hi] = rangeMonths(), c = $('#f-cur').value, s = $('#f-src').value, q = $('#f-q').value.trim().toLowerCase(), xfer = $('#f-xfer').checked;
  return ROWS.filter(r => { const m = month(r); return m >= lo && m <= hi && (!c || r.currency === c) && (!s || r.source === s) && (!q || r.expense_name.toLowerCase().includes(q)) && !(xfer && r.expense_type === 'Transfer'); });
}

const tip = $('#tip');
function bindTips() {
  document.querySelectorAll('[data-tip]').forEach(el => {
    el.onmousemove = e => { tip.innerHTML = esc(el.dataset.tip); tip.style.display = 'block'; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY + 12) + 'px'; };
    el.onmouseleave = () => tip.style.display = 'none';
  });
}

// ---- net assets ----
// bank-level summary rows that already include that bank's account rows
const SUMMARY_ACCOUNTS = new Set(['Richart總資產', '存款合計', '總資產現值', '資產總計', 'Deposits & Investments']);
const STALE_MONTHS = 6; // no statement for this long -> shown but not counted
function latestPerAccount(uptoMonth) {
  const latest = {};
  BAL.filter(r => month(r) <= uptoMonth).forEach(r => { const k = r.bank + '|' + r.account + '|' + r.currency; if (!latest[k] || r.date >= latest[k].date) latest[k] = r; });
  const cutoff = new Date(uptoMonth + '-01'); cutoff.setMonth(cutoff.getMonth() - STALE_MONTHS);
  return Object.values(latest).map(r => ({...r, stale: new Date(r.date) < cutoff}));
}
function counts(items) {
  const t = {};
  items.forEach(r => {
    const c = r.currency; t[c] = t[c] || {asset: 0, liability: 0};
    if (r.stale) return;
    if (r.kind === 'asset' && !SUMMARY_ACCOUNTS.has(r.account) &&
        items.some(x => x.bank === r.bank && x.kind === 'asset' && SUMMARY_ACCOUNTS.has(x.account))) return; // detail under a summary
    t[c][r.kind] += num(r.balance);
  });
  return t;
}

function assets() {
  const [, hi] = rangeMonths(); const cur = $('#f-cur').value;
  const items = latestPerAccount(hi).filter(r => !cur || r.currency === cur)
    .sort((x, y) => x.currency.localeCompare(y.currency) || x.kind.localeCompare(y.kind) || x.bank.localeCompare(y.bank) || x.account.localeCompare(y.account));
  if (!items.length) { $('#assets').innerHTML = '<div class="note">沒有對帳單餘額資料（重新執行 main.py 會產生 output/balances.csv）。</div>'; return; }
  const totals = Object.fromEntries(Object.entries(counts(items)).filter(([, t]) => t.asset || t.liability));
  let html = '<div class="tiles">' + Object.entries(totals).map(([c, t]) => `<div class="tile"><div class="label">${esc(c)} 淨資產</div><div class="value">${fmt0(t.asset - t.liability)}</div><div class="note">資產 ${fmt0(t.asset)} · 負債 ${fmt0(t.liability)}</div></div>`).join('') + '</div>';
  html += `<table style="margin-top:10px"><thead><tr><th>銀行</th><th>帳戶</th><th>幣別</th><th>對帳單日期</th><th class="num">餘額</th></tr></thead><tbody>` +
    items.map(r => `<tr style="${r.stale ? 'color:var(--muted)' : ''}"><td>${esc(r.bank)}</td><td>${esc(r.account)}</td><td>${esc(r.currency)}</td><td>${esc(r.date)}${r.stale ? '（過期，不計入）' : ''}</td><td class="num${r.kind === 'liability' ? ' liab' : ''}">${r.kind === 'liability' ? '−' : ''}${fmt(num(r.balance))}</td></tr>`).join('') + '</tbody></table>';
  $('#assets').innerHTML = html;
}

function assetTrend() {
  const [lo, hi] = rangeMonths(); const cur = $('#f-cur').value;
  const months = MONTHS.filter(m => m >= lo && m <= hi);
  const series = {};
  months.forEach((m, i) => { Object.entries(counts(latestPerAccount(m))).forEach(([c, v]) => { if ((cur && c !== cur) || !(v.asset || v.liability)) return; (series[c] = series[c] || Array(months.length).fill(null))[i] = v.asset - v.liability; }); });
  const weight = c => BAL.filter(r => r.currency === c).length;
  const curs = Object.keys(series).sort((x, y) => weight(y) - weight(x));
  $('#c-assets').innerHTML = curs.map(c => lineChart(c, months, series[c])).join('') || '<div class="note">無資料</div>';
}

function lineChart(title, months, values) {
  const W = 1040, H = 170, L = 70, B = 26, T = 18, R = 10;
  const vals = values.filter(v => v !== null); if (!vals.length) return '';
  const max = Math.max(...vals, 0), min = Math.min(...vals, 0), span = (max - min) || 1;
  const x = i => L + (W - L - R) * (months.length > 1 ? i / (months.length - 1) : 0.5), y = v => T + (H - T - B) * (1 - (v - min) / span);
  let s = `<div class="cur">${esc(title)}</div><svg viewBox="0 0 ${W} ${H}" width="100%">`;
  for (let k = 0; k <= 3; k++) { const v = min + span * k / 3, yy = y(v); s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end">${yTick(v)}</text>`; }
  if (min < 0) s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
  const pts = values.map((v, i) => v === null ? null : [x(i), y(v)]).filter(Boolean);
  s += `<path d="${pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ')}" fill="none" stroke="var(--s1)" stroke-width="2"/>`;
  values.forEach((v, i) => { if (v !== null) s += `<circle data-tip="${esc(months[i])} ${esc(title)} ${fmt0(v)}" cx="${x(i)}" cy="${y(v)}" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>`; });
  const step = Math.ceil(months.length / 12);
  months.forEach((m, i) => { if (i % step === 0 || i === months.length - 1) s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(m)}</text>`; });
  return s + '</svg>';
}

// ---- income / expense ----
function tiles(rows) {
  const by = {}; rows.forEach(r => { const c = r.currency; by[c] = by[c] || {i: 0, o: 0, n: 0}; by[c].i += num(r.income); by[c].o += num(r.expense); by[c].n++; });
  const curs = Object.keys(by).sort((x, y) => by[y].n - by[x].n);
  $('#tiles').innerHTML = curs.map(c => `<div class="cur">${esc(c)}（${by[c].n} 筆）</div><div class="tiles">
    <div class="tile"><div class="label">收入</div><div class="value in">${fmt0(by[c].i)}</div></div>
    <div class="tile"><div class="label">支出</div><div class="value out">${fmt0(by[c].o)}</div></div>
    <div class="tile"><div class="label">淨額</div><div class="value">${fmt0(by[c].i - by[c].o)}</div></div></div>`).join('') || '<div class="note">此期間無交易</div>';
  return curs;
}

function monthChart(rows, currency) {
  const [lo, hi] = rangeMonths(); const months = MONTHS.filter(m => m >= lo && m <= hi);
  const by = {}; months.forEach(m => by[m] = {i: 0, o: 0});
  rows.filter(r => r.currency === currency).forEach(r => { const m = month(r); if (by[m]) { by[m].i += num(r.income); by[m].o += num(r.expense); } });
  const W = 1040, H = 190, L = 70, B = 26, T = 10, R = 10;
  const max = Math.max(1, ...months.flatMap(m => [by[m].i, by[m].o]));
  const bw = (W - L - R) / Math.max(1, months.length), y = v => T + (H - T - B) * (1 - v / max);
  let s = `<div class="cur">${esc(currency)}</div><svg viewBox="0 0 ${W} ${H}" width="100%">`;
  for (let k = 0; k <= 4; k++) { const v = max * k / 4, yy = y(v); s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end">${yTick(v)}</text>`; }
  s += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
  const step = Math.ceil(months.length / 12);
  months.forEach((m, i) => {
    const x0 = L + i * bw + bw * 0.12, w = Math.max(1.5, (bw * 0.76 - 2) / 2);
    const bar = (v, x, c, label) => `<rect data-tip="${esc(m)} ${label} ${fmt(v)}" x="${x}" y="${y(v)}" width="${w}" height="${Math.max(0, y(0) - y(v))}" fill="var(${c})" rx="2"/>`;
    s += bar(by[m].i, x0, '--s1', '收入') + bar(by[m].o, x0 + w + 2, '--s2', '支出');
    if (i % step === 0 || i === months.length - 1) s += `<text x="${L + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${esc(m)}</text>`;
  });
  return s + '</svg>';
}

function hbarChart(rows) {
  const by = {}; rows.forEach(r => { const k = `${r.source} (${r.currency})`; by[k] = (by[k] || 0) + num(r.expense); });
  const items = Object.entries(by).filter(([, v]) => v > 0).sort((x, y) => y[1] - x[1]).slice(0, 8);
  const max = Math.max(1, ...items.map(([, v]) => v)), W = 1040, rh = 26, L = 220, H = items.length * rh + 6;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%">`;
  items.forEach(([k, v], i) => { const w = (W - L - 110) * v / max, yy = i * rh + 4;
    s += `<text x="${L - 8}" y="${yy + 15}" text-anchor="end">${esc(k)}</text><rect data-tip="${esc(k)} ${fmt(v)}" x="${L}" y="${yy}" width="${Math.max(2, w)}" height="${rh - 8}" fill="var(--s2)" rx="3"/><text x="${L + Math.max(2, w) + 6}" y="${yy + 15}">${fmt0(v)}</text>`; });
  return s + (items.length ? '' : '<text x="8" y="18">無支出</text>') + '</svg>';
}

function table(rows) {
  const sorted = [...rows].sort((x, y) => y.date.localeCompare(x.date));
  const inc = rows.reduce((s, r) => s + num(r.income), 0), out = rows.reduce((s, r) => s + num(r.expense), 0);
  $('#tbl').innerHTML = `<thead><tr><th>日期</th><th>消費名目</th><th>來源</th><th>幣別</th><th class="num">收入</th><th class="num">支出</th></tr></thead><tbody>` +
    sorted.slice(0, 2000).map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.expense_name)}</td><td>${esc(r.source)}</td><td>${esc(r.currency)}</td><td class="num">${r.income ? fmt(num(r.income)) : ''}</td><td class="num">${r.expense ? fmt(num(r.expense)) : ''}</td></tr>`).join('') +
    `</tbody><tfoot><tr><td colspan="4">合計（${rows.length} 筆${rows.length > 2000 ? '，表格只列最新 2000 筆' : ''}）</td><td class="num">${fmt(inc)}</td><td class="num">${fmt(out)}</td></tr></tfoot>`;
}

function render() {
  paintRange();
  const rows = filtered();
  assets(); assetTrend();
  const curs = tiles(rows);
  $('#c-month').innerHTML = curs.map(c => monthChart(rows, c)).join('');
  $('#c-src').innerHTML = hbarChart(rows);
  table(rows);
  bindTips();
}
[a, b].forEach(el => el.addEventListener('input', render));
document.querySelectorAll('.filters select, .filters input').forEach(el => el.addEventListener('input', render));
$('#f-xfer').addEventListener('change', render);
render();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    output_dir = (argv or sys.argv[1:] or ['output'])[0]
    rows = load(output_dir, 'expenses_*.csv', COLUMNS)
    balances = load(output_dir, 'balances.csv', BALANCE_COLUMNS)
    html = (TEMPLATE
            .replace('__DATA__', json.dumps(rows, ensure_ascii=False).replace('</', '<\\/'))
            .replace('__BALANCES__', json.dumps(balances, ensure_ascii=False).replace('</', '<\\/')))
    out = os.path.join(output_dir, 'report.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"{out}: {len(rows)} transactions, {len(balances)} balances, generated {datetime.now():%Y-%m-%d %H:%M}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

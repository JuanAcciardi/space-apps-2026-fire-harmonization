/* Burning Activity Calendar — static front end over the exported binary products in data/ */
(async function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (v, d = 0) => (v == null || Number.isNaN(v)) ? '–' : v.toLocaleString('en-US', { maximumFractionDigits: d });
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // ---------- data ---------------------------------------------------------------------------
  const meta = await (await fetch('data/meta.json')).json();
  const NM = meta.months.length, NC = meta.cells.length;
  const YEARS = [...new Set(meta.months.map((m) => +m.slice(0, 4)))];
  const Y0 = YEARS[0];
  const TYPES = { int16: Int16Array, int32: Int32Array, float32: Float32Array, uint8: Uint8Array };
  const bins = {};
  async function load(name) {
    if (bins[name]) return bins[name];
    const s = meta.series[name];
    const buf = await (await fetch('data/' + s.file)).arrayBuffer();
    bins[name] = { a: new TYPES[s.dtype](buf), scale: s.scale, na: s.na, shape: s.shape };
    return bins[name];
  }
  await Promise.all(['hs_modis', 'hs_snpp', 'hs_noaa20', 'hs_noaa21', 'hs_harm', 'hs_lo', 'hs_hi', 'src'].filter((n) => meta.series[n]).map(load));
  if (!bins.hs_noaa21) bins.hs_noaa21 = { a: new Int16Array(NC * NM).fill(-1), scale: 1, na: -1 };
  const LAST_YEAR = YEARS[YEARS.length - 1];
  const S = bins;
  const val = (name, ci, mi) => { const b = S[name]; const v = b.a[ci * NM + mi]; return (v === b.na && name !== 'src') ? null : v / b.scale; };
  const cellIndex = new Map(meta.cells.map((c, i) => [c.h, i]));
  const provCells = meta.provinces.map((_, p) => meta.cells.map((c, i) => (c.p === p ? i : -1)).filter((i) => i >= 0));
  const allCells = meta.cells.map((_, i) => i);

  // uncertainty lookup: modelled sum -> [q05, q95]
  const UNC = meta.validation.aggregate_uncertainty_lookup;
  function band(modelled) {
    if (modelled <= 0) return [0, 0];
    let u = UNC.find((r) => modelled > r.pred_min && modelled <= r.pred_max) || UNC[UNC.length - 1];
    return [modelled * u.q05, modelled * u.q95];
  }

  // ---------- aggregation ---------------------------------------------------------------------
  // monthly series for a set of cells: harm, modis, snpp, noaa20, modelled part, lo/hi, source mix
  function monthly(cells) {
    const out = { harm: new Array(NM).fill(0), modis: new Array(NM).fill(null), snpp: new Array(NM).fill(null), noaa20: new Array(NM).fill(null), noaa21: new Array(NM).fill(null),
      modelled: new Array(NM).fill(0), lo: new Array(NM).fill(0), hi: new Array(NM).fill(0), src: Array.from({ length: NM }, () => [0, 0, 0, 0, 0, 0]) };
    for (const ci of cells) {
      for (let mi = 0; mi < NM; mi++) {
        const h = val('hs_harm', ci, mi); if (h != null) out.harm[mi] += h;
        const m = val('hs_modis', ci, mi); if (m != null) out.modis[mi] = (out.modis[mi] || 0) + m;
        const s = val('hs_snpp', ci, mi); if (s != null) out.snpp[mi] = (out.snpp[mi] || 0) + s;
        const n = val('hs_noaa20', ci, mi); if (n != null) out.noaa20[mi] = (out.noaa20[mi] || 0) + n;
        const n1 = val('hs_noaa21', ci, mi); if (n1 != null) out.noaa21[mi] = (out.noaa21[mi] || 0) + n1;
        const sc = S.src.a[ci * NM + mi]; out.src[mi][sc]++;
        if (sc >= 3 && h != null) out.modelled[mi] += h;
      }
    }
    for (let mi = 0; mi < NM; mi++) {
      const obs = out.harm[mi] - out.modelled[mi];
      const [lo, hi] = band(out.modelled[mi]);
      out.lo[mi] = obs + lo; out.hi[mi] = obs + hi;
    }
    // naive joined record: S-NPP where it exists, otherwise MODIS
    out.joined = out.snpp.map((s, i) => (s != null && meta.months[i] < meta.sensor_windows.SNPP[1].slice(0, 7) ? s : out.noaa20[i] != null ? out.noaa20[i] : out.modis[i]));
    return out;
  }
  function annual(mo) {
    const sum = (arr) => YEARS.map((y) => { let t = null; for (let mi = 0; mi < NM; mi++) if (+meta.months[mi].slice(0, 4) === y && arr[mi] != null) t = (t || 0) + arr[mi]; return t; });
    const harm = sum(mo.harm), modelled = sum(mo.modelled);
    const lo = [], hi = [];
    YEARS.forEach((y, i) => { const obs = (harm[i] || 0) - (modelled[i] || 0); const [l, h] = band(modelled[i] || 0); lo.push(obs + l); hi.push(obs + h); });
    return { harm, modis: sum(mo.modis), snpp: sum(mo.snpp), noaa20: sum(mo.noaa20), noaa21: sum(mo.noaa21), joined: sum(mo.joined), lo, hi, modelled };
  }
  function monthIdx(y, m) { return (y - Y0) * 12 + m; }
  function monthsOf(y, m) { return (m < 0 ? Array.from({ length: 12 }, (_, k) => monthIdx(y, k)) : [monthIdx(y, m)]).filter((mi) => mi >= 0 && mi < NM); }
  function median(arr) { const a = arr.filter((v) => v != null).sort((x, y) => x - y); if (!a.length) return null; const k = a.length >> 1; return a.length % 2 ? a[k] : (a[k - 1] + a[k]) / 2; }

  // ---------- state --------------------------------------------------------------------------
  const state = { cells: allCells, name: 'Argentina', provIdx: null, year: YEARS[YEARS.length - 1], month: -1, layer: 'harm', raw: false, drawing: false };
  $('year').max = state.year; $('year').value = state.year; $('year-out').value = state.year;
  $('last-day').textContent = meta.last_day || meta.months[NM - 1];

  // ---------- map ----------------------------------------------------------------------------
  const map = L.map('map', { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([-38.5, -64], 4);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', { maxZoom: 12, attribution: 'Basemap © Esri, HERE, Garmin, OpenStreetMap contributors' }).addTo(map);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 12, pane: 'shadowPane' }).addTo(map);
  const provGeo = await (await fetch('data/provincias.geojson')).json();
  L.geoJSON(provGeo, { style: { color: css('--ink-2'), weight: 0.8, fill: false, opacity: 0.6 }, interactive: false }).addTo(map);
  const cellLayer = L.layerGroup().addTo(map);
  const polys = meta.cells.map((c, i) => {
    const b = h3.cellToBoundary(c.h);
    const p = L.polygon(b, { weight: 0.5, color: css('--surface'), fillOpacity: 0.85, fillColor: '#ccc', className: 'cell-path' });
    p.on('click', (e) => { if (state.drawing) return; selectCells(e.originalEvent.shiftKey ? [...new Set([...state.cells.length === NC ? [] : state.cells, i])] : [i], e.originalEvent.shiftKey && state.cells.length !== NC ? 'Custom selection' : 'Cell ' + c.h, null); });
    p.on('mouseover', (e) => showTip(e.originalEvent, tipForCell(i)));
    p.on('mousemove', (e) => moveTip(e.originalEvent));
    p.on('mouseout', hideTip);
    p.addTo(cellLayer);
    return p;
  });
  let selLayer = L.layerGroup().addTo(map);

  // sequential one-hue ramp light->dark (fire orange), interpolated in OKLab-ish via simple sRGB gamma mix
  function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  function mix(a, b, t) { const g = (x) => Math.pow(x / 255, 2.2), ig = (x) => Math.round(255 * Math.pow(x, 1 / 2.2)); return `rgb(${ig(g(a[0]) + (g(b[0]) - g(a[0])) * t)},${ig(g(a[1]) + (g(b[1]) - g(a[1])) * t)},${ig(g(a[2]) + (g(b[2]) - g(a[2])) * t)})`; }
  const ramp = (t) => mix(hexToRgb(css('--fire-lo')), hexToRgb(css('--fire-hi')), Math.max(0, Math.min(1, t)));
  const SRC_COL = ['transparent', css('--src1'), css('--src2'), css('--src3'), css('--src4'), css('--noaa21')];
  const SRC_NAME = ['no data', 'S-NPP observed', 'NOAA-20 scaled', 'MODIS × k', 'Terra-only, bridged × k', 'NOAA-21 scaled'];

  function cellValue(ci, layer = state.layer) {
    const months = monthsOf(state.year, state.month);
    if (layer === 'src') { const c = [0, 0, 0, 0, 0, 0]; months.forEach((mi) => c[S.src.a[ci * NM + mi]]++); return c.indexOf(Math.max(...c)); }
    if (layer === 'k') { let m = 0, h = 0; months.forEach((mi) => { const mm = val('hs_modis', ci, mi), hh = val('hs_harm', ci, mi); if (mm != null && hh != null && S.src.a[ci * NM + mi] >= 3) { m += mm; h += hh; } }); return m > 0 ? h / m : null; }
    const name = { harm: 'hs_harm', modis: 'hs_modis', snpp: 'hs_snpp', noaa20: 'hs_noaa20', noaa21: 'hs_noaa21' }[layer];
    let t = null; months.forEach((mi) => { const v = val(name, ci, mi); if (v != null) t = (t || 0) + v; });
    return t;
  }
  function paintMap() {
    const vals = meta.cells.map((_, i) => cellValue(i));
    const leg = $('legend'); leg.textContent = '';
    if (state.layer === 'src') {
      polys.forEach((p, i) => p.setStyle({ fillColor: SRC_COL[vals[i]] || 'transparent', fillOpacity: vals[i] ? 0.8 : 0 }));
      [1, 2, 5, 3, 4].forEach((k) => { const sw = document.createElement('span'); sw.className = 'sw'; const i = document.createElement('i'); i.style.background = SRC_COL[k]; sw.append(i, document.createTextNode(SRC_NAME[k])); leg.append(sw); });
      return;
    }
    if (state.layer === 'k') {
      polys.forEach((p, i) => { const v = vals[i]; p.setStyle({ fillColor: v == null ? 'transparent' : ramp(Math.log(v) / Math.log(4) / 1.5 + 0.33), fillOpacity: v == null ? 0 : 0.85 }); });
      legendRamp(leg, 'k = 0.5', 'k = 4 (log)', 'Factor VIIRS/MODIS applied to pre-2012 months, by cell and calendar month');
      return;
    }
    const pos = vals.filter((v) => v > 0).sort((a, b) => a - b);
    const vmax = pos.length ? pos[Math.floor(pos.length * 0.98)] : 1;
    polys.forEach((p, i) => { const v = vals[i]; p.setStyle({ fillColor: v == null ? 'transparent' : v === 0 ? css('--surface') : ramp(Math.log1p(v) / Math.log1p(vmax)), fillOpacity: v == null ? 0 : v === 0 ? 0.25 : 0.85 }); });
    const unit = { harm: 'harmonized hot spots', modis: 'MODIS hot spots (raw)', snpp: 'S-NPP hot spots (raw)', noaa20: 'NOAA-20 hot spots (raw)', noaa21: 'NOAA-21 hot spots (raw)' }[state.layer];
    legendRamp(leg, '1', fmt(vmax) + '+', unit + ', ' + periodLabel() + ' (log scale; blank = sensor not flying)');
  }
  function legendRamp(leg, lo, hi, text) {
    const r = document.createElement('div'); r.className = 'ramp'; r.style.background = `linear-gradient(90deg, ${ramp(0)}, ${ramp(0.5)}, ${ramp(1)})`;
    leg.append(document.createTextNode(lo), r, document.createTextNode(hi), document.createElement('br'), document.createTextNode(text));
  }
  function periodLabel() { const partial = state.year === LAST_YEAR && meta.last_day ? ` (to ${meta.last_day.slice(5)})` : ''; return (state.month < 0 ? String(state.year) : MONTHS[state.month] + ' ' + state.year) + partial; }

  // selection outline
  function drawSelection() {
    selLayer.clearLayers();
    if (state.cells.length === NC) return;
    state.cells.forEach((ci) => L.polygon(h3.cellToBoundary(meta.cells[ci].h), { color: css('--ink'), weight: 2, fill: false, interactive: false }).addTo(selLayer));
  }
  function selectCells(cells, name, provIdx) {
    state.cells = cells; state.name = name; state.provIdx = provIdx;
    if (provIdx == null) $('aoi-select').value = name === 'Argentina' ? 'all' : '__custom__';
    drawSelection(); renderPanel();
  }

  // draw box
  let rect = null, start = null;
  $('draw-btn').onclick = () => { state.drawing = !state.drawing; $('draw-btn').classList.toggle('active', state.drawing); map.dragging[state.drawing ? 'disable' : 'enable'](); $('map').classList.toggle('map-drawing', state.drawing); };
  map.on('mousedown', (e) => { if (!state.drawing) return; start = e.latlng; rect = L.rectangle([start, start], { color: css('--ink'), weight: 1.5, fill: false }).addTo(map); });
  map.on('mousemove', (e) => { if (rect && start) rect.setBounds(L.latLngBounds(start, e.latlng)); });
  map.on('mouseup', (e) => {
    if (!rect) return; const b = L.latLngBounds(start, e.latlng); map.removeLayer(rect); rect = null; start = null;
    state.drawing = false; $('draw-btn').classList.remove('active'); map.dragging.enable(); $('map').classList.remove('map-drawing');
    const cells = meta.cells.map((c, i) => (b.contains([c.lat, c.lon]) ? i : -1)).filter((i) => i >= 0);
    if (cells.length) selectCells(cells, `Box ${b.getSouth().toFixed(1)}…${b.getNorth().toFixed(1)}°S, ${b.getWest().toFixed(1)}…${b.getEast().toFixed(1)}°W`, null);
  });
  $('clear-btn').onclick = () => { $('aoi-select').value = 'all'; selectCells(allCells, 'Argentina', null); map.setView([-38.5, -64], 4); };

  // ---------- tooltip ------------------------------------------------------------------------
  const tip = $('tooltip');
  function showTip(ev, node) { tip.textContent = ''; tip.append(node); tip.hidden = false; moveTip(ev); }
  function moveTip(ev) { const x = ev.clientX + 14, y = ev.clientY + 14; tip.style.left = Math.min(x, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = Math.min(y, innerHeight - tip.offsetHeight - 8) + 'px'; }
  function hideTip() { tip.hidden = true; }
  function tipForCell(ci) {
    const c = meta.cells[ci]; const d = document.createElement('div');
    const title = document.createElement('div'); title.textContent = (meta.provinces[c.p] || 'offshore') + ' · cell ' + c.h.slice(0, 7); title.className = 'muted'; d.append(title);
    const rows = [['hs_harm', 'harmonized', css('--harm')], ['hs_modis', 'MODIS raw', css('--modis')], ['hs_snpp', 'S-NPP raw', css('--snpp')], ['hs_noaa20', 'NOAA-20 raw', css('--noaa20')], ['hs_noaa21', 'NOAA-21 raw', css('--noaa21')]];
    const months = monthsOf(state.year, state.month);
    for (const [name, label, col] of rows) {
      let t = null; months.forEach((mi) => { const v = val(name, ci, mi); if (v != null) t = (t || 0) + v; });
      const r = document.createElement('div'); r.className = 'row'; const k = document.createElement('span'); k.className = 'key'; k.style.background = col;
      const b = document.createElement('b'); b.textContent = t == null ? 'not flying' : fmt(t, 0); const l = document.createElement('span'); l.textContent = label; l.className = 'muted';
      r.append(k, b, l); d.append(r);
    }
    const p = document.createElement('div'); p.className = 'muted'; p.textContent = periodLabel() + ' · hot spots'; d.append(p);
    return d;
  }

  // ---------- charts -------------------------------------------------------------------------
  const base = () => ({ paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12, color: css('--ink-2') },
    margin: { l: 56, r: 12, t: 8, b: 36 }, hovermode: 'x unified', hoverlabel: { bgcolor: css('--surface'), bordercolor: css('--axis'), font: { color: css('--ink') } },
    legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 12 } },
    xaxis: { gridcolor: 'rgba(0,0,0,0)', linecolor: css('--axis'), tickfont: { color: css('--muted') }, zeroline: false },
    yaxis: { gridcolor: css('--grid'), zeroline: false, linecolor: 'rgba(0,0,0,0)', tickfont: { color: css('--muted') }, rangemode: 'tozero', separatethousands: true } });
  const CFG = { displayModeBar: false, responsive: true };

  function chartAnnual(an) {
    const x = YEARS;
    const traces = [
      { x: [...x, ...x.slice().reverse()], y: [...an.hi, ...an.lo.slice().reverse()], fill: 'toself', fillcolor: css('--band'), line: { width: 0 }, hoverinfo: 'skip', showlegend: false, name: '90% band' },
      { x, y: an.modis, name: 'MODIS raw', mode: 'lines', line: { color: css('--modis'), width: 2 }, connectgaps: false },
      { x, y: an.snpp, name: 'VIIRS S-NPP raw', mode: 'lines', line: { color: css('--snpp'), width: 2 } },
      { x, y: an.noaa20, name: 'VIIRS NOAA-20 raw', mode: 'lines', line: { color: css('--noaa20'), width: 2 } },
      { x, y: an.noaa21, name: 'VIIRS NOAA-21 raw', mode: 'lines', line: { color: css('--noaa21'), width: 2 } },
      { x, y: an.harm, name: 'Harmonized (VIIRS scale)', mode: 'lines', line: { color: css('--harm'), width: 2.5 } },
    ];
    if (state.raw) traces.push({ x, y: an.joined, name: 'Naive joined record', mode: 'lines+markers', line: { color: css('--joined'), width: 2 }, marker: { size: 6 } });
    const lay = base(); lay.yaxis.title = { text: 'hot spots / year', font: { size: 12 } }; lay.shapes = [{ type: 'line', x0: 2012, x1: 2012, y0: 0, y1: 1, yref: 'paper', line: { color: css('--axis'), width: 1 } }];
    lay.annotations = [{ x: 2012, y: 0.02, yref: 'paper', text: 'VIIRS starts', showarrow: false, xanchor: 'left', yanchor: 'bottom', font: { size: 11, color: css('--muted') } },
      { x: LAST_YEAR, y: 0.02, yref: 'paper', text: meta.last_day ? 'partial year' : '', showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { size: 11, color: css('--muted') } }];
    Plotly.react('chart-annual', traces, lay, CFG);
  }
  function chartCalendar(mo) {
    const series = state.raw ? mo.joined : mo.harm;
    const z = YEARS.map((y) => MONTHS.map((_, m) => (monthIdx(y, m) < NM ? series[monthIdx(y, m)] : null)));
    const text = YEARS.map((y) => MONTHS.map((_, m) => { const mi = monthIdx(y, m); if (mi >= NM) return `${MONTHS[m]} ${y}<br>not yet`; const sm = mo.src[mi]; const dom = sm.indexOf(Math.max(...sm)); return `${MONTHS[m]} ${y}<br><b>${fmt(series[mi], 0)}</b> hot spots<br>${state.raw ? 'raw, ' + (mo.snpp[mi] != null ? 'S-NPP' : 'MODIS') : SRC_NAME[dom]}${!state.raw && mo.modelled[mi] > 0 ? `<br>90% band ${fmt(mo.lo[mi], 0)}–${fmt(mo.hi[mi], 0)}` : ''}`; }));
    const lay = base(); lay.margin.l = 44; lay.hovermode = 'closest'; lay.yaxis = { autorange: 'reversed', tickfont: { color: css('--muted') }, dtick: 2, gridcolor: 'rgba(0,0,0,0)' }; lay.xaxis.side = 'top'; lay.margin.t = 24; lay.margin.b = 8;
    Plotly.react('chart-calendar', [{ type: 'heatmap', x: MONTHS, y: YEARS, z, text, hoverinfo: 'text', xgap: 2, ygap: 2, colorscale: [[0, ramp(0)], [0.5, ramp(0.5)], [1, ramp(1)]], showscale: true, colorbar: { thickness: 8, len: 0.9, outlinewidth: 0, tickfont: { color: css('--muted'), size: 11 } }, zmin: 0 }], lay, CFG);
  }
  function chartSeason(mo) {
    const full = YEARS.filter((y) => !(y === LAST_YEAR && meta.last_day));
    const med = MONTHS.map((_, m) => median(full.map((y) => mo.harm[monthIdx(y, m)])));
    const sel = MONTHS.map((_, m) => (monthIdx(state.year, m) < NM ? mo.harm[monthIdx(state.year, m)] : null));
    const lay = base(); lay.hovermode = 'x unified'; lay.yaxis.title = { text: 'hot spots / month', font: { size: 12 } }; lay.bargap = 0.35;
    Plotly.react('chart-season', [
      { type: 'bar', x: MONTHS, y: med, name: `Median month ${full[0]}–${full[full.length - 1]}`, marker: { color: css('--band'), line: { width: 0 } } },
      { type: 'scatter', mode: 'lines+markers', x: MONTHS, y: sel, name: String(state.year), line: { color: css('--harm'), width: 2 }, marker: { size: 7, color: css('--harm') } },
    ], lay, CFG);
  }
  async function chartDaily() {
    const card = $('daily-card');
    const rowName = state.provIdx != null ? meta.provinces[state.provIdx] : state.cells.length === NC ? '__national__' : null;
    if (rowName == null) { card.style.display = 'none'; return; }
    card.style.display = '';
    const D = await load('daily_hs_harm'); const ri = meta.daily_rows.indexOf(rowName); const nd = meta.n_days;
    const start = new Date(meta.days_start + 'T00:00:00Z');
    const z = YEARS.map(() => new Array(366).fill(null));
    for (let di = 0; di < nd; di++) {
      const d = new Date(start.getTime() + di * 86400000); const y = d.getUTCFullYear(); const doy = Math.floor((d - Date.UTC(y, 0, 1)) / 86400000);
      const v = D.a[ri * nd + di]; z[y - Y0][doy] = v < 0 ? null : v;
    }
    const x = Array.from({ length: 366 }, (_, i) => i + 1);
    const text = YEARS.map((y, yi) => x.map((doy) => { const d = new Date(Date.UTC(y, 0, doy)); return `${d.toISOString().slice(0, 10)}<br><b>${fmt(z[yi][doy - 1], 0)}</b> hot spots${y < 2012 ? '<br>indicative (MODIS × monthly factor)' : ''}`; }));
    const ticks = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
    const lay = base(); lay.margin.l = 44; lay.hovermode = 'closest'; lay.yaxis = { autorange: 'reversed', tickfont: { color: css('--muted') }, dtick: 2, gridcolor: 'rgba(0,0,0,0)' };
    lay.xaxis = { tickvals: ticks, ticktext: MONTHS, side: 'top', tickfont: { color: css('--muted') }, gridcolor: 'rgba(0,0,0,0)' }; lay.margin.t = 24; lay.margin.b = 8;
    Plotly.react('chart-daily', [{ type: 'heatmap', x, y: YEARS, z, text, hoverinfo: 'text', xgap: 0, ygap: 1, colorscale: [[0, ramp(0)], [0.5, ramp(0.5)], [1, ramp(1)]], zmin: 0, zmax: Math.max(1, quantile(z.flat().filter((v) => v > 0), 0.99)), colorbar: { thickness: 8, len: 0.9, outlinewidth: 0, tickfont: { color: css('--muted'), size: 11 } } }], lay, CFG);
    $('daily-hint').textContent = 'Days before 2012 are MODIS days scaled by that month\'s province factor: they keep the monthly total but the day-to-day pattern is MODIS. Blank = sensor not flying.';
  }
  function quantile(a, q) { if (!a.length) return 0; const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(q * s.length))]; }

  function renderTable(mo, an) {
    const t = $('table'); t.textContent = '';
    const head = document.createElement('tr');
    ['Year', 'Harmonized', '90% low', '90% high', 'MODIS raw', 'S-NPP raw', 'NOAA-20 raw', 'NOAA-21 raw', 'Modelled share'].forEach((h) => { const th = document.createElement('th'); th.textContent = h; head.append(th); });
    t.append(head);
    YEARS.forEach((y, i) => {
      const tr = document.createElement('tr');
      [y === LAST_YEAR && meta.last_day ? `${y} (partial)` : y, fmt(an.harm[i]), fmt(an.lo[i]), fmt(an.hi[i]), fmt(an.modis[i]), fmt(an.snpp[i]), fmt(an.noaa20[i]), fmt(an.noaa21[i]), an.harm[i] ? Math.round(100 * (an.modelled[i] || 0) / an.harm[i]) + '%' : '–'].forEach((v) => { const td = document.createElement('td'); td.textContent = v; tr.append(td); });
      t.append(tr);
    });
    $('csv-btn').onclick = () => {
      const lines = ['month,harmonized_hotspots,band_low,band_high,modis_raw,snpp_raw,noaa20_raw,noaa21_raw,source_mix'];
      for (let mi = 0; mi < NM; mi++) lines.push([meta.months[mi], mo.harm[mi].toFixed(1), mo.lo[mi].toFixed(1), mo.hi[mi].toFixed(1), mo.modis[mi] ?? '', mo.snpp[mi] ?? '', mo.noaa20[mi] ?? '', mo.noaa21[mi] ?? '', mo.src[mi].map((n, k) => n ? `${SRC_NAME[k]}:${n}` : '').filter(Boolean).join('|')].join(','));
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' })); a.download = `burning_calendar_${state.name.replace(/[^a-z0-9]+/gi, '_')}.csv`; a.click();
    };
  }

  function renderTiles(mo, an) {
    const yi = YEARS.indexOf(state.year);
    let cur, lo, hi, normal, hist, ytdNote = '';
    if (state.month < 0 && state.year === LAST_YEAR && meta.last_day) {
      // partial year: compare the same Jan..last-month window in every year, not a full year
      const lastM = (NM - 1) % 12;
      const win = (y) => { let t = null; for (let m = 0; m <= lastM; m++) { const mi = monthIdx(y, m); if (mi < NM && mo.harm[mi] != null) t = (t || 0) + mo.harm[mi]; } return t; };
      hist = YEARS.map(win); cur = win(state.year); lo = an.lo[yi]; hi = an.hi[yi];
      ytdNote = ` · Jan–${MONTHS[lastM]} window`;
    } else if (state.month < 0) { cur = an.harm[yi]; lo = an.lo[yi]; hi = an.hi[yi]; hist = an.harm; }
    else { const mi = monthIdx(state.year, state.month); const ok = mi < NM; cur = ok ? mo.harm[mi] : null; lo = ok ? mo.lo[mi] : null; hi = ok ? mo.hi[mi] : null; hist = YEARS.map((y) => monthIdx(y, state.month) < NM ? mo.harm[monthIdx(y, state.month)] : null); }
    normal = median(hist.filter((v, i) => !(YEARS[i] === LAST_YEAR && meta.last_day)));
    $('hero-label').textContent = `Hot spots, ${periodLabel()}`;
    $('hero-value').textContent = fmt(cur);
    $('hero-sub').textContent = lo !== hi ? `90% band ${fmt(lo)}–${fmt(hi)} (pre-2012 is modelled)` : 'observed by VIIRS';
    const rank = cur == null ? null : hist.filter((v) => v != null && v > cur).length + 1;
    // critical period: shortest run of calendar months (circular) holding >= 2/3 of a median year's fire
    const fullYears = YEARS.filter((y) => !(y === LAST_YEAR && meta.last_day));
    const med = MONTHS.map((_, m) => median(fullYears.map((y) => mo.harm[monthIdx(y, m)])) || 0);
    const totMed = med.reduce((a, b) => a + b, 0);
    let best = null;
    if (totMed > 0) for (let len = 1; len <= 12 && !best; len++) for (let s0 = 0; s0 < 12; s0++) { let acc = 0; for (let k = 0; k < len; k++) acc += med[(s0 + k) % 12]; if (acc / totMed >= 2 / 3) { best = { s0, len, share: acc / totMed }; break; } }
    $('crit-value').textContent = best ? (best.len === 12 ? 'all year' : best.len === 1 ? MONTHS[best.s0] : `${MONTHS[best.s0]}–${MONTHS[(best.s0 + best.len - 1) % 12]}`) : '–';
    $('crit-sub').textContent = best ? `${best.len} month${best.len > 1 ? 's' : ''} hold ${Math.round(100 * best.share)}% of a normal year's fire` : 'not enough fire to define';
    const pct = normal > 0 && cur != null ? Math.round(100 * (cur / normal - 1)) : null;
    $('anom-value').textContent = pct == null || cur == null ? '–' : (pct >= 0 ? '+' : '') + pct + '%';
    $('anom-sub').textContent = cur == null ? 'no data yet for this month' : `rank ${rank} of ${YEARS.length} ${state.month < 0 ? 'years' : MONTHS[state.month] + 's'} · normal ${fmt(normal)}${ytdNote}`;
    const months = monthsOf(state.year, state.month);
    const mix = [0, 0, 0, 0, 0, 0]; months.forEach((mi) => mo.src[mi].forEach((n, k) => (mix[k] += n)));
    const tot = mix.slice(1).reduce((a, b) => a + b, 0) || 1;
    const bar = $('src-bar'); bar.textContent = '';
    [1, 2, 5, 3, 4].forEach((k) => { if (!mix[k]) return; const s = document.createElement('span'); s.style.width = (100 * mix[k] / tot) + '%'; s.style.background = SRC_COL[k]; s.title = SRC_NAME[k]; bar.append(s); });
    $('src-sub').textContent = [1, 2, 5, 3, 4].filter((k) => mix[k]).map((k) => `${Math.round(100 * mix[k] / tot)}% ${SRC_NAME[k]}`).join(' · ');
  }

  function renderPanel() {
    const mo = monthly(state.cells), an = annual(mo);
    const area = state.cells.reduce((a, ci) => a + meta.cells[ci].a, 0);
    $('aoi-name').textContent = state.name;
    $('aoi-meta').textContent = `${state.cells.length} cells · ~${fmt(area)} km² · ${meta.months[0]} to ${meta.months[NM - 1]}`;
    renderTiles(mo, an); chartAnnual(an); chartCalendar(mo); chartSeason(mo); renderTable(mo, an); chartDaily();
  }

  // ---------- switch & method tabs -------------------------------------------------------------
  function renderSwitch() {
    const an = annual(monthly(allCells));
    const lay = base(); lay.yaxis.title = { text: 'hot spots / year, Argentina', font: { size: 12 } };
    lay.shapes = [{ type: 'line', x0: 2012, x1: 2012, y0: 0, y1: 1, yref: 'paper', line: { color: css('--axis'), width: 1 } }];
    Plotly.react('chart-switch', [
      { x: [...YEARS, ...YEARS.slice().reverse()], y: [...an.hi, ...an.lo.slice().reverse()], fill: 'toself', fillcolor: css('--band'), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
      { x: YEARS, y: an.joined, name: 'Naive joined record (MODIS then S-NPP)', mode: 'lines+markers', line: { color: css('--joined'), width: 2 }, marker: { size: 6 } },
      { x: YEARS, y: an.modis, name: 'MODIS alone', mode: 'lines', line: { color: css('--modis'), width: 2 } },
      { x: YEARS, y: an.harm, name: 'Harmonized (VIIRS scale)', mode: 'lines', line: { color: css('--harm'), width: 2.5 } },
    ], lay, CFG);
    const s = meta.validation.seam_2012_national;
    const pct = (r) => (r >= 1 ? '+' : '') + Math.round(100 * (r - 1)) + '%';
    $('seam-raw').textContent = pct(s.raw_joined_post_over_pre); $('seam-harm').textContent = pct(s.harmonized_post_over_pre); $('seam-modis').textContent = pct(s.modis_only_post_over_pre);
    const ks = Object.values(meta.validation.k_national_by_month); $('k-avg').textContent = (ks.reduce((a, b) => a + b, 0) / ks.length).toFixed(1) + '×';
  }
  function renderMethod() {
    const v = meta.validation; const root = $('validation'); root.textContent = '';
    const mk = (title, rows, head) => { const h = document.createElement('h3'); h.textContent = title; const t = document.createElement('table'); t.className = 'vtable'; const tr = document.createElement('tr'); head.forEach((x) => { const th = document.createElement('th'); th.textContent = x; tr.append(th); }); t.append(tr); rows.forEach((r) => { const tr = document.createElement('tr'); r.forEach((x) => { const td = document.createElement('td'); td.textContent = x; tr.append(td); }); t.append(tr); }); root.append(h, t); };
    mk('Backtest: factors fitted on 2016–2025 predict S-NPP in 2012–2015 (cell × month)', v.backtest_2012_2015.cell_month.map((m) => [m.method, m.total_bias_pct + '%', m.wape_pct + '%', m.rmse]), ['Method', 'Total bias', 'Weighted abs. error', 'RMSE']);
    mk('Backtest: national totals per year', Object.entries(v.backtest_2012_2015.national_annual).map(([y, r]) => [y, fmt(r.y_hs), fmt(r.pred_raw), fmt(r.pred_ratio), fmt(r.pred_lgbm)]), ['Year', 'S-NPP observed', 'MODIS raw', 'MODIS × k', 'LightGBM']);
    mk('Per-cell error over the 4 backtest years (cells with ≥20 hot spots)', [['Ratio × k', Math.round(100 * v.backtest_2012_2015.cell_4yr_fire_weighted_abs_err_pred_ratio) + '%', Math.round(100 * v.backtest_2012_2015.cell_4yr_median_abs_err_pred_ratio) + '%'], ['LightGBM', Math.round(100 * v.backtest_2012_2015.cell_4yr_fire_weighted_abs_err_pred_lgbm) + '%', Math.round(100 * v.backtest_2012_2015.cell_4yr_median_abs_err_pred_lgbm) + '%']], ['Method', 'Fire-weighted abs. error', 'Median abs. error']);
    mk('Seam test at 2012 (2013–15 mean over 2009–11 mean, national)', [['Naive joined record', v.seam_2012_national.raw_joined_post_over_pre + '×'], ['Harmonized', v.seam_2012_national.harmonized_post_over_pre + '×'], ['MODIS alone (control)', v.seam_2012_national.modis_only_post_over_pre + '×'], ['LightGBM variant', v.seam_2012_national.harmonized_lgbm_post_over_pre + '×']], ['Record', 'Ratio']);
    mk('National factor k = S-NPP / MODIS by calendar month (hot spots; FRP)', MONTHS.map((m, i) => [m, v.k_national_by_month[i + 1], v.k_frp_national_by_month[i + 1]]), ['Month', 'k hot spots', 'k FRP']);
    mk('NOAA-20 / S-NPP by year (hot spots; FRP)', Object.keys(v.noaa20_over_snpp_by_year.hotspots).map((y) => [y, v.noaa20_over_snpp_by_year.hotspots[y], v.noaa20_over_snpp_by_year.frp[y]]), ['Year', 'hot spots', 'FRP']);
    if (v.noaa21_over_snpp_by_year) mk('NOAA-21 / S-NPP by year (hot spots; FRP)', Object.keys(v.noaa21_over_snpp_by_year.hotspots).map((y) => [y, v.noaa21_over_snpp_by_year.hotspots[y], v.noaa21_over_snpp_by_year.frp[y]]), ['Year', 'hot spots', 'FRP']);
    mk('Terra-only bridge: (Terra+Aqua)/Terra cell-days by month, 2003–2011', MONTHS.map((m, i) => [m, v.terra_only_bridge_national_by_month[i + 1]]), ['Month', 'factor']);
  }

  // ---------- controls -----------------------------------------------------------------------
  const sel = $('aoi-select');
  const optAll = document.createElement('option'); optAll.value = 'all'; optAll.textContent = 'Argentina (whole country)'; sel.append(optAll);
  meta.provinces.forEach((p, i) => { const o = document.createElement('option'); o.value = String(i); o.textContent = p; sel.append(o); });
  const optC = document.createElement('option'); optC.value = '__custom__'; optC.textContent = 'Custom selection'; optC.disabled = true; sel.append(optC);
  sel.onchange = () => {
    if (sel.value === 'all') { selectCells(allCells, 'Argentina', null); map.setView([-38.5, -64], 4); return; }
    const i = +sel.value; const cells = provCells[i]; state.provIdx = i; selectCells(cells, meta.provinces[i], i);
    const lats = cells.map((c) => meta.cells[c].lat), lons = cells.map((c) => meta.cells[c].lon);
    if (cells.length) map.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], { padding: [20, 20] });
  };
  $('year').oninput = (e) => { state.year = +e.target.value; $('year-out').value = state.year; paintMap(); renderPanel(); };
  $('month').onchange = (e) => { state.month = +e.target.value; paintMap(); renderPanel(); };
  $('layer').onchange = (e) => { state.layer = e.target.value; paintMap(); };
  $('show-raw').onchange = (e) => { state.raw = e.target.checked; renderPanel(); };
  document.querySelectorAll('.tab').forEach((b) => b.onclick = () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tabpane').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + b.dataset.tab));
    $('filters').style.visibility = b.dataset.tab === 'explore' ? 'visible' : 'hidden';
    if (b.dataset.tab === 'switch') renderSwitch(); if (b.dataset.tab === 'method') renderMethod();
    if (b.dataset.tab === 'explore') { map.invalidateSize(); renderPanel(); }
  });
  $('generated').textContent = 'Data built ' + meta.generated + '.';

  // URL state (?aoi=Corrientes&year=2020&month=8&layer=modis&tab=switch) so views can be shared
  const q = new URLSearchParams(location.search);
  if (q.get('year')) { state.year = Math.min(LAST_YEAR, Math.max(Y0, +q.get('year'))); $('year').value = state.year; $('year-out').value = state.year; }
  if (q.get('month')) { state.month = +q.get('month'); $('month').value = state.month; }
  if (q.get('layer') && [...$('layer').options].some((o) => o.value === q.get('layer'))) { state.layer = q.get('layer'); $('layer').value = state.layer; }
  if (q.get('raw') === '1') { state.raw = true; $('show-raw').checked = true; }
  paintMap(); renderPanel();
  if (q.get('aoi')) { const i = meta.provinces.findIndex((p) => p.toLowerCase() === q.get('aoi').toLowerCase()); if (i >= 0) { sel.value = String(i); sel.onchange(); } }
  if (q.get('tab')) { const b = document.querySelector(`.tab[data-tab="${q.get('tab')}"]`); if (b) b.click(); }
})();

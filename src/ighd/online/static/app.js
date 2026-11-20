/* The page: fetch the API, hold one state object, render it.
 *
 * Python parses the input, decomposes, applies the modifications and validates. This file
 * renders what comes back and handles clicks. There is no hypergraph algorithm here: bags,
 * covers, widths, kept nodes and changed edges are all read from the API payload.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const SVGNS = 'http://www.w3.org/2000/svg';
let STATE = null;
let KIND = 'AddVar';
let FORM = {};
let SELECTED = null;          // {type: 'vertex'|'edge'|'node', name}

/* ------------------------------------------------------------------ */
/* API                                                                 */
/* ------------------------------------------------------------------ */
async function api(path, body) {
  $('busy').hidden = false;
  document.querySelectorAll('button.primary').forEach(b => b.classList.add('busy'));
  try {
    let res;
    try {
      res = await fetch(path, body === undefined ? {} :
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    } catch (_) { throw new Error('Could not reach the server. Is it still running?'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { if (data.state) render(data.state); throw new Error(data.error || `The server answered ${res.status}.`); }
    return data;
  } finally {
    $('busy').hidden = true;
    document.querySelectorAll('button.primary').forEach(b => b.classList.remove('busy'));
  }
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */
const set = (xs) => '{' + [...xs].join(',') + '}';
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const k of kids) e.append(k);
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
function showError(id, msg) { const e = $(id); e.textContent = msg || ''; e.hidden = !msg; }
function fresh(prefix, taken) {
  if (!taken.has(prefix)) return prefix;
  for (let i = 1; ; i++) if (!taken.has(prefix + i)) return prefix + i;
}
const edgesOf = () => STATE?.hypergraph?.edges || {};
const verticesOf = () => STATE?.hypergraph?.vertices || [];
const incident = (v) => Object.entries(edgesOf()).filter(([, vs]) => vs.includes(v)).map(([e]) => e);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ------------------------------------------------------------------ */
/* pan & zoom (Fit / 1:1), no library                                  */
/* ------------------------------------------------------------------ */
class Zoom {
  constructor(svgEl, scene, { fitPad = 24 } = {}) {
    this.svg = svgEl; this.scene = scene; this.t = { k: 1, x: 0, y: 0 }; this.fitPad = fitPad;
    this.moved = false;
    svgEl.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = svgEl.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const k = Math.min(4, Math.max(0.05, this.t.k * Math.exp(-e.deltaY * 0.0015)));
      this.t.x = px - (px - this.t.x) * (k / this.t.k); this.t.y = py - (py - this.t.y) * (k / this.t.k); this.t.k = k;
      this.apply();
    }, { passive: false });
    let drag = null;
    svgEl.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY, tx: this.t.x, ty: this.t.y }; this.moved = false;
    });
    window.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!this.moved && Math.hypot(dx, dy) < 4) return;
      if (!this.moved) { this.moved = true; svgEl.setPointerCapture?.(e.pointerId); svgEl.classList.add('dragging'); }
      this.t.x = drag.tx + dx; this.t.y = drag.ty + dy; this.apply();
    });
    window.addEventListener('pointerup', () => { drag = null; svgEl.classList.remove('dragging'); });
  }
  apply() { this.scene.setAttribute('transform', `translate(${this.t.x},${this.t.y}) scale(${this.t.k})`); }
  size() { const r = this.svg.getBoundingClientRect(); return [Math.max(r.width, 1), Math.max(r.height, 1)]; }
  fit(box) {
    const [W, H] = this.size(), p = this.fitPad;
    const k = Math.min(3, (W - 2 * p) / Math.max(box.w, 1), (H - 2 * p) / Math.max(box.h, 1));
    this.t = { k, x: (W - box.w * k) / 2 - box.x * k, y: (H - box.h * k) / 2 - box.y * k };
    this.apply(); return k;
  }
  oneToOne(box, anchorTop = false) {
    const [W, H] = this.size();
    this.t = { k: 1, x: (W - box.w) / 2 - box.x, y: anchorTop ? 20 - box.y : (H - box.h) / 2 - box.y };
    this.apply();
  }
}

/* ------------------------------------------------------------------ */
/* input block                                                         */
/* ------------------------------------------------------------------ */
async function loadExamples() {
  const ex = await (await fetch('/api/examples')).json();
  for (const x of ex) {
    const c = el('button', { class: 'chip', type: 'button', 'aria-pressed': 'false', text: x.name });
    c.onclick = () => {
      $('graph-text').value = x.text;
      document.querySelectorAll('#examples .chip').forEach(b => b.setAttribute('aria-pressed', String(b === c)));
    };
    $('examples').append(c);
  }
  fetch('/api/hyperbench').then(r => r.json()).then(list => {
    if (!list.length) { $('bench').hidden = true; return; }
    $('bench').options[0].text = `HyperBench instance (${list.length} with ≤ 16 vertices)…`;
    for (const b of list) $('bench').append(el('option', { value: b.name, text: `${b.name}  (${b.edges} edges, ${b.vertices} vertices)` }));
    $('bench').disabled = false;
  });
}
$('bench').onchange = async () => {
  if (!$('bench').value) return;
  try { $('graph-text').value = (await api('/api/hyperbench', { name: $('bench').value })).text; }
  catch (e) { showError('graph-error', e.message); }
};
$('file').onchange = async (ev) => { const f = ev.target.files[0]; if (f) $('graph-text').value = await f.text(); ev.target.value = ''; };
$('generate').onclick = async () => {
  showError('graph-error', '');
  if (STATE?.started && STATE.history.length > 1 &&
      !confirm('Start again from this hypergraph? The current decomposition and its step log are replaced.')) return;
  try {
    POS.clear(); COLOR.clear(); SELECTED = null; VIEW.opened = false;
    render(await api('/api/start', { text: $('graph-text').value }));
  } catch (e) { showError('graph-error', e.message); }
};
$('undo').onclick = async () => {
  try { render(await api('/api/undo', {})); } catch (e) { showError('update-error', e.message); }
};

/* settings */
for (const id of ['strategy', 'tighten', 'oracle', 'timeout']) {
  $(id).onchange = async () => {
    const body = { strategy: $('strategy').value, tighten: $('tighten').checked,
                   oracle: $('oracle').checked, timeout: $('timeout').value };
    try { render(await api('/api/settings', body)); } catch (e) { alert(e.message); }
  };
}

/* ------------------------------------------------------------------ */
/* modification forms                                                  */
/* ------------------------------------------------------------------ */
const KINDS = {
  AddVar:    { label: 'Add vertex',     desc: 'Add a new vertex to one or more existing edges (AddVar).' },
  DelVar:    { label: 'Delete vertex',  desc: 'Remove a vertex from every edge it is in; an edge left empty is deleted (DelVar).' },
  AddConstr: { label: 'Add edge',       desc: 'Add a new edge over existing and/or new vertices (AddConstr).' },
  DelConstr: { label: 'Delete edge',    desc: 'Remove an edge; vertices left in no edge disappear (DelConstr).' },
  AddEq:     { label: 'Merge vertices', desc: 'Merge several vertices into one; it may keep one of the names or get a new one (AddEq).' },
  DelEq:     { label: 'Split vertex',   desc: 'Split a vertex into parts; every edge of the vertex goes to at least one part (DelEq).' },
};
function chips(items, selected, onToggle, label = (x) => x, extra = () => '') {
  const box = el('div', { class: 'chips' });
  for (const it of items) {
    const c = el('button', { class: 'chip', type: 'button', 'aria-pressed': String(selected.has(it)) }, label(it));
    const ex = extra(it); if (ex) c.append(el('small', { text: ex }));
    c.onclick = () => { onToggle(it); buildForm(); };
    box.append(c);
  }
  return box;
}
function field(text, ...kids) { const d = el('div'); d.append(el('label', { class: 'field', text }), ...kids); return d; }
function input(value, onInput, placeholder = '') {
  const i = el('input', { type: 'text', value: value ?? '', placeholder, spellcheck: 'false' });
  i.oninput = () => { onInput(i.value.trim()); updatePreview(); };
  return i;
}
function select(options, value, onChange) {
  const s = el('select');
  for (const [v, t] of options) { const o = el('option', { value: v, text: t }); if (v === value) o.selected = true; s.append(o); }
  s.onchange = () => { onChange(s.value); buildForm(); };
  return s;
}
function defaults() {
  const E = new Set(Object.keys(edgesOf())), V = new Set(verticesOf()), v0 = verticesOf()[0] || '';
  return {
    AddVar: { vertex: fresh('x', V), edges: new Set() },
    DelVar: { vertex: v0 },
    AddConstr: { name: fresh('e' + (E.size + 1), E), vertices: new Set(), extra: '' },
    DelConstr: { name: Object.keys(edgesOf())[0] || '' },
    AddEq: { merge: new Set(), into: '', intoNew: fresh('m', V) },
    DelEq: { vertex: verticesOf().find(v => incident(v).length) || v0, parts: null },
  };
}
function buildKinds() {
  const box = $('kinds'); box.replaceChildren();
  for (const [k, v] of Object.entries(KINDS)) {
    const b = el('button', { class: 'chip', type: 'button', role: 'tab', 'aria-pressed': String(k === KIND), text: v.label });
    b.onclick = () => { KIND = k; showError('update-error', ''); buildKinds(); };
    box.append(b);
  }
  $('kind-desc').textContent = KINDS[KIND].desc;
  buildForm();
}
function buildForm() {
  const f = FORM[KIND], form = $('form');
  form.replaceChildren();
  const E = edgesOf(), V = verticesOf();
  const edgeLabel = (e) => `${e} ${set(E[e])}`;
  const grid = el('div', { class: 'form-grid' });
  if (KIND === 'AddVar') {
    grid.append(field('new vertex name', input(f.vertex, (v) => f.vertex = v)));
    const full = field('add it to these edges',
      chips(Object.keys(E), f.edges, (e) => f.edges.has(e) ? f.edges.delete(e) : f.edges.add(e), edgeLabel));
    full.className = 'full'; grid.append(full);
  } else if (KIND === 'DelVar') {
    grid.append(field('vertex to delete',
      select(V.map(v => [v, `${v}  (in ${incident(v).length} edge${incident(v).length === 1 ? '' : 's'})`]), f.vertex, (v) => f.vertex = v)));
  } else if (KIND === 'AddConstr') {
    grid.append(field('new edge name', input(f.name, (v) => f.name = v)));
    grid.append(field('new vertices (optional)', input(f.extra, (v) => f.extra = v, 'e.g. y z')));
    const full = field('its vertices', chips(V, f.vertices, (v) => f.vertices.has(v) ? f.vertices.delete(v) : f.vertices.add(v)));
    full.className = 'full'; grid.append(full);
  } else if (KIND === 'DelConstr') {
    grid.append(field('edge to delete', select(Object.keys(E).map(e => [e, edgeLabel(e)]), f.name, (v) => f.name = v)));
  } else if (KIND === 'AddEq') {
    const full = field('vertices to merge',
      chips(V, f.merge, (v) => { f.merge.has(v) ? f.merge.delete(v) : f.merge.add(v); if (!f.merge.has(f.into)) f.into = ''; },
        (v) => v, (v) => `${incident(v).length}`));
    full.className = 'full'; grid.append(full);
    const into = f.into || ([...f.merge].sort()[0] ?? '__new__');
    const opts = [...f.merge].sort().map(v => [v, `keep the name ${v}`]).concat([['__new__', 'a new name…']]);
    grid.append(field('merged vertex', select(opts, into, (v) => f.into = v)));
    if (into === '__new__') grid.append(field('new name', input(f.intoNew, (v) => f.intoNew = v)));
  } else if (KIND === 'DelEq') {
    grid.append(field('vertex to split',
      select(V.filter(v => incident(v).length).map(v => [v, `${v}  (in ${incident(v).length} edges)`]), f.vertex,
        (v) => { f.vertex = v; f.parts = null; })));
    const inc = incident(f.vertex);
    if (!f.parts || f.parts.vertex !== f.vertex) {
      const half = Math.ceil(inc.length / 2);
      f.parts = { vertex: f.vertex, names: [f.vertex, fresh(f.vertex + '2', new Set(V))],
                  assign: Object.fromEntries(inc.map((e, i) => [e, new Set([i < half ? 0 : 1])])) };
    }
    const P = f.parts, tbl = el('table', { class: 'parts-table' });
    const head = el('tr', {}, el('th', { text: 'edge' }));
    P.names.forEach((n, j) => {
      const i = el('input', { type: 'text', value: n, 'aria-label': `name of part ${j + 1}` });
      i.oninput = () => { P.names[j] = i.value.trim(); updatePreview(); };
      head.append(el('th', {}, i));
    });
    tbl.append(head);
    for (const e of inc) {
      const tr = el('tr', {}, el('td', { text: edgeLabel(e) }));
      P.names.forEach((_, j) => {
        const cb = el('input', { type: 'checkbox', 'aria-label': `${e} goes to part ${j + 1}` }); cb.checked = P.assign[e]?.has(j);
        cb.onchange = () => { cb.checked ? P.assign[e].add(j) : P.assign[e].delete(j); updatePreview(); };
        tr.append(el('td', {}, cb));
      });
      tbl.append(tr);
    }
    const full = field('which edges each part keeps (rename the parts in the header)', tbl,
      el('div', { class: 'actions' },
        el('button', { class: 'tool', type: 'button', text: '+ part',
          onclick: () => { P.names.push(fresh(f.vertex + (P.names.length + 1), new Set([...V, ...P.names]))); buildForm(); } }),
        el('button', { class: 'tool', type: 'button', text: '− part',
          onclick: () => { if (P.names.length > 2) { P.names.pop(); for (const s of Object.values(P.assign)) s.delete(P.names.length); buildForm(); } } })));
    full.className = 'full'; grid.append(full);
  }
  form.append(grid);
  updatePreview();
}
function request() {
  const f = FORM[KIND];
  switch (KIND) {
    case 'AddVar': return { kind: KIND, vertex: f.vertex, edges: [...f.edges] };
    case 'DelVar': return { kind: KIND, vertex: f.vertex };
    case 'AddConstr': {
      const extra = (f.extra || '').split(/[\s,;]+/).filter(Boolean);
      return { kind: KIND, name: f.name, vertices: [...new Set([...f.vertices, ...extra])] };
    }
    case 'DelConstr': return { kind: KIND, name: f.name };
    case 'AddEq': {
      const into = f.into || ([...f.merge].sort()[0] ?? '__new__');
      return { kind: KIND, merge: [...f.merge], into: into === '__new__' ? f.intoNew : into };
    }
    case 'DelEq': {
      const parts = {};
      f.parts.names.forEach((n, j) => { parts[n] = Object.entries(f.parts.assign).filter(([, s]) => s.has(j)).map(([e]) => e); });
      return { kind: KIND, vertex: f.vertex, parts };
    }
  }
}
function updatePreview() {
  const r = request(); let t = '';
  if (r.kind === 'AddVar') t = `ADD VERTEX ${r.vertex || '?'} TO ${r.edges.length ? set(r.edges.sort()) : '(pick edges)'}`;
  if (r.kind === 'DelVar') t = `DELETE VERTEX ${r.vertex || '?'}  (from ${set(incident(r.vertex))})`;
  if (r.kind === 'AddConstr') t = `ADD EDGE ${r.name || '?'} = ${r.vertices.length ? set(r.vertices.sort()) : '(pick vertices)'}`;
  if (r.kind === 'DelConstr') t = `DELETE EDGE ${r.name} = ${set(edgesOf()[r.name] || [])}`;
  if (r.kind === 'AddEq') t = `MERGE ${r.merge.length ? set(r.merge.sort()) : '(pick vertices)'} INTO ${r.into || '?'}`;
  if (r.kind === 'DelEq') t = `SPLIT ${r.vertex}: ` + Object.entries(r.parts).map(([p, es]) => `${p || '?'} ← ${set(es.sort())}`).join('   ');
  $('preview').innerHTML = `<span class="lbl">next</span>${esc(t)}`;
}
$('apply').onclick = async () => {
  showError('update-error', '');
  try { render(await api('/api/modify', request())); }
  catch (e) { showError('update-error', e.message); }
};

/* ------------------------------------------------------------------ */
/* hypergraph drawing (Euler style)                                    */
/* ------------------------------------------------------------------ */
/* Every edge is a closed shape around exactly its vertices: one vertex a circle, two a
 * capsule, more a rounded outline of their convex hull. Smaller edges get tighter
 * outlines, so an edge contained in another is drawn inside it. Positions and colours
 * belong to the vertex and the edge for the whole session, so a modification shows up as
 * a change in a picture you recognise, not as a new picture. */
const HG_W = 640, HG_H = 460, VR = 13;
const POS = new Map();
const COLOR = new Map(), NCOLORS = 8;
const VIEW = { opened: false, treeOpened: false };

function layout(vertices, edges) {
  const W = HG_W, H = HG_H, M = 48, n = vertices.length, E = Object.values(edges);
  const nbr = Object.fromEntries(vertices.map(v => [v, new Set()]));
  for (const vs of E) for (const a of vs) for (const b of vs) if (a !== b) nbr[a].add(b);
  const p = {};
  vertices.forEach((v, i) => {
    if (POS.has(v)) { p[v] = [...POS.get(v)]; return; }
    const known = [...nbr[v]].filter(u => POS.has(u));
    if (known.length) {
      const c = known.reduce((a, u) => [a[0] + POS.get(u)[0], a[1] + POS.get(u)[1]], [0, 0]);
      p[v] = [c[0] / known.length + 15 * Math.cos(i), c[1] / known.length + 15 * Math.sin(i)];
    } else {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(n, 1);
      p[v] = [W / 2 + 170 * Math.cos(a), H / 2 + 150 * Math.sin(a)];
    }
  });
  const k = Math.sqrt((W - 2 * M) * (H - 2 * M) / Math.max(n, 1)) * 0.8;
  let temp = POS.size ? 12 : 70;
  for (let it = 0; it < 320; it++) {
    const d = Object.fromEntries(vertices.map(v => [v, [0, 0]]));
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = vertices[i], b = vertices[j];
      const dx = p[a][0] - p[b][0], dy = p[a][1] - p[b][1], dist = Math.hypot(dx, dy) || 0.01;
      let f = (k * k) / dist;
      if (nbr[a].has(b)) f -= (dist * dist) / k;
      d[a][0] += dx / dist * f; d[a][1] += dy / dist * f; d[b][0] -= dx / dist * f; d[b][1] -= dy / dist * f;
    }
    for (const vs of E) {
      if (vs.length < 2) continue;
      const cx = vs.reduce((a, v) => a + p[v][0], 0) / vs.length, cy = vs.reduce((a, v) => a + p[v][1], 0) / vs.length;
      const rad = Math.max(...vs.map(v => Math.hypot(p[v][0] - cx, p[v][1] - cy))) + 30;
      for (const v of vs) { d[v][0] += (cx - p[v][0]) * 0.08; d[v][1] += (cy - p[v][1]) * 0.08; }
      for (const v of vertices) {
        if (vs.includes(v)) continue;
        const dx = p[v][0] - cx, dy = p[v][1] - cy, dist = Math.hypot(dx, dy) || 0.01;
        if (dist < rad) { const push = (rad - dist) * 0.9; d[v][0] += dx / dist * push; d[v][1] += dy / dist * push; }
      }
    }
    for (const v of vertices) {
      d[v][0] += (W / 2 - p[v][0]) * 0.02; d[v][1] += (H / 2 - p[v][1]) * 0.02;
      const len = Math.hypot(d[v][0], d[v][1]) || 1, step = Math.min(len, temp);
      p[v][0] = Math.min(W - M, Math.max(M, p[v][0] + d[v][0] / len * step));
      p[v][1] = Math.min(H - M, Math.max(M, p[v][1] + d[v][1] / len * step));
    }
    temp = Math.max(temp * 0.97, 1.5);
  }
  for (const v of [...POS.keys()]) if (!vertices.includes(v)) POS.delete(v);
  for (const v of vertices) POS.set(v, p[v]);
  return p;
}
function hull(pts) {
  const uniq = [...new Map(pts.map(q => [q.join(','), q])).values()];
  if (uniq.length < 3) return uniq;
  const s = [...uniq].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of s) { while (lo.length >= 2 && cross(lo.at(-2), lo.at(-1), q) <= 0) lo.pop(); lo.push(q); }
  for (const q of s.reverse()) { while (up.length >= 2 && cross(up.at(-2), up.at(-1), q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function blobPath(h, r) {
  if (h.length === 1) {
    const [x, y] = h[0];
    return `M ${x - r} ${y} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0 Z`;
  }
  if (h.length === 2) {
    const [[x1, y1], [x2, y2]] = h, L = Math.hypot(x2 - x1, y2 - y1) || 1;
    const nx = -(y2 - y1) / L * r, ny = (x2 - x1) / L * r;
    return `M ${x1 + nx} ${y1 + ny} L ${x2 + nx} ${y2 + ny} A ${r} ${r} 0 0 0 ${x2 - nx} ${y2 - ny} ` +
           `L ${x1 - nx} ${y1 - ny} A ${r} ${r} 0 0 0 ${x1 + nx} ${y1 + ny} Z`;
  }
  const c = h.reduce((a, q) => [a[0] + q[0] / h.length, a[1] + q[1] / h.length], [0, 0]);
  const normals = h.map((q, i) => {
    const q2 = h[(i + 1) % h.length], L = Math.hypot(q2[0] - q[0], q2[1] - q[1]) || 1;
    let nx = (q2[1] - q[1]) / L, ny = -(q2[0] - q[0]) / L;
    if (nx * ((q[0] + q2[0]) / 2 - c[0]) + ny * ((q[1] + q2[1]) / 2 - c[1]) < 0) { nx = -nx; ny = -ny; }
    return [nx, ny];
  });
  let d = '';
  h.forEach((q, i) => {
    const q2 = h[(i + 1) % h.length], [nx, ny] = normals[i], [mx, my] = normals[(i + 1) % h.length];
    const a = [q[0] + nx * r, q[1] + ny * r], b = [q2[0] + nx * r, q2[1] + ny * r], e = [q2[0] + mx * r, q2[1] + my * r];
    d += (i === 0 ? `M ${a[0]} ${a[1]} ` : '') + `L ${b[0]} ${b[1]} A ${r} ${r} 0 0 ${nx * my - ny * mx > 0 ? 1 : 0} ${e[0]} ${e[1]} `;
  });
  return d + 'Z';
}
function assignColors(names) {
  for (const e of [...COLOR.keys()]) if (!names.includes(e)) COLOR.delete(e);
  const used = new Set(COLOR.values());
  for (const e of names) {
    if (COLOR.has(e)) continue;
    let slot = 0; while (used.has(slot) && slot < NCOLORS) slot++;
    COLOR.set(e, slot); if (slot < NCOLORS) used.add(slot);
  }
  return Object.fromEntries(names.map(e => [e, COLOR.get(e) < NCOLORS ? `var(--h${COLOR.get(e) + 1})` : 'var(--h-other)']));
}

const HG = { svg: $('hg-svg'), scene: null, zoom: null, box: { x: -30, y: -30, w: HG_W + 60, h: HG_H + 60 } };
HG.scene = svg('g', { class: 'scene' }); HG.svg.append(HG.scene);
HG.zoom = new Zoom(HG.svg, HG.scene);
HG.svg.addEventListener('click', (e) => { if (e.target === HG.svg && !HG.zoom.moved) setSelection(null); });
$('hg-fit').onclick = () => HG.zoom.fit(HG.box);
$('hg-reset').onclick = () => HG.zoom.oneToOne(HG.box);

function drawHypergraph() {
  const hg = STATE.hypergraph;
  HG.scene.replaceChildren();
  if (!hg) return;
  const changed = new Set(STATE.last?.changed_edges || []);
  const p = layout(hg.vertices, hg.edges);
  const names = Object.keys(hg.edges), color = assignColors(names);
  const order = [...names].sort((a, b) => hg.edges[a].length - hg.edges[b].length || a.localeCompare(b));
  const pad = {}, placed = [];
  for (const e of order) {                       // inner edges tight, overlapping ones on distinct rings
    const vs = new Set(hg.edges[e]);
    const used = new Set(placed.filter(f => hg.edges[f].some(v => vs.has(v))).map(f => pad[f]));
    let r = 20; while (used.has(r) && r < 20 + 7 * 6) r += 7;
    pad[e] = r; placed.push(e);
  }
  const layerE = svg('g'), layerL = svg('g'), layerV = svg('g');
  const many = names.length > 40;
  for (const e of [...order].reverse()) {
    const vs = hg.edges[e], h = hull(vs.map(v => p[v])), ch = changed.has(e);
    const g = svg('g', { class: 'hedge' + (ch ? ' changed' : ''), 'data-edge': e, style: `--c:${color[e]}` });
    const title = svg('title'); title.textContent = `${e} = ${set(vs)}${ch ? '  (changed by the last step)' : ''}`;
    g.append(title, svg('path', { d: blobPath(h, pad[e]), class: 'blob' }));
    g.addEventListener('click', (ev) => { if (!HG.zoom.moved) { ev.stopPropagation(); setSelection({ type: 'edge', name: e }); } });
    layerE.append(g);
    if (!many) {
      let best = h[0], bd = -1;
      for (const q of h) { const dd = Math.hypot(q[0] - HG_W / 2, q[1] - HG_H / 2); if (dd > bd) { bd = dd; best = q; } }
      let ux = best[0] - HG_W / 2, uy = best[1] - HG_H / 2; const L = Math.hypot(ux, uy) || 1; ux /= L; uy /= L;
      if (h.length === 1 || L < 5) { ux = 0; uy = -1; }
      const lw = (e.length + (ch ? 2 : 0)) * 7.5;
      let lx = best[0] + ux * (pad[e] + 9), ly = best[1] + uy * (pad[e] + 9) + 4;
      let anchor = ux > 0.35 ? 'start' : ux < -0.35 ? 'end' : 'middle';
      if (anchor === 'start' && lx + lw > HG_W + 26) { lx = HG_W + 26; anchor = 'end'; }
      if (anchor === 'end' && lx - lw < -26) { lx = -26; anchor = 'start'; }
      ly = Math.min(HG_H + 22, Math.max(-14, ly));
      const t = svg('text', { x: lx, y: ly, 'text-anchor': anchor, class: 'elabel', 'data-edge': e, style: `--c:${color[e]}` });
      t.textContent = ch ? `${e} ●` : e;
      layerL.append(t);
    }
  }
  for (const v of hg.vertices) {
    const [x, y] = p[v];
    const g = svg('g', { class: 'vertex', 'data-vertex': v });
    const title = svg('title'); title.textContent = `${v}: in ${incident(v).join(', ') || 'no edge'}`;
    g.append(title, svg('circle', { cx: x, cy: y, r: VR }));
    const t = svg('text', { x, y: y + 4 }); t.textContent = v; g.append(t);
    g.addEventListener('click', (ev) => { if (!HG.zoom.moved) { ev.stopPropagation(); setSelection({ type: 'vertex', name: v }); } });
    layerV.append(g);
  }
  HG.scene.append(layerE, layerL, layerV);
  if (!VIEW.opened) { HG.zoom.fit(HG.box); VIEW.opened = true; }

  // caption: counts, changed edges, colour-coded edge list
  const last = STATE.last, cap = $('hg-caption');
  const parts = [`<strong>${hg.vertices.length}</strong> vertices, <strong>${names.length}</strong> edges.`];
  if (last && last.status !== 'built' && last.status !== 'undo') {
    if (last.changed_edges.length) parts.push(`<span class="k-chg">changed by the last step:</span> ${esc(last.changed_edges.join(', '))} (dashed).`);
    if (last.removed_edges.length) parts.push(`deleted: ${esc(last.removed_edges.join(', '))}.`);
  }
  cap.innerHTML = parts.join(' ') + ' Click a vertex or an edge to select it.';
  const list = el('div', { class: 'edge-list' });
  for (const e of names) {
    const c = el('span', { class: 'echip' + (changed.has(e) ? ' changed' : ''), style: `--c:${color[e]}`, title: `${e} = ${set(hg.edges[e])}` },
      `${e} ${set(hg.edges[e])}`);
    c.onclick = () => setSelection({ type: 'edge', name: e });
    list.append(c);
  }
  for (const e of last?.removed_edges || []) list.append(el('span', { class: 'echip removed', text: e, title: 'deleted by the last step' }));
  cap.append(list);
}

/* ------------------------------------------------------------------ */
/* decomposition drawing                                               */
/* ------------------------------------------------------------------ */
const TR = { svg: $('tree-svg'), scene: null, zoom: null, box: null };
TR.scene = svg('g', { class: 'scene' }); TR.svg.append(TR.scene);
TR.zoom = new Zoom(TR.svg, TR.scene);
TR.svg.addEventListener('click', (e) => { if (e.target === TR.svg && !TR.zoom.moved) setSelection(null); });
$('tree-fit').onclick = () => TR.box && TR.zoom.fit(TR.box);
$('tree-reset').onclick = () => TR.box && TR.zoom.oneToOne(TR.box, true);

function drawTree() {
  const t = STATE.ghd;
  TR.scene.replaceChildren();
  const cap = $('tree-caption');
  if (!t) { cap.textContent = STATE.started ? 'No decomposition: the last search hit the time limit. Press Decompose again or raise the limit in Settings.' : ''; TR.box = null; return; }
  const byId = Object.fromEntries(t.nodes.map(n => [n.id, n]));
  const last = STATE.last;
  const showKept = last?.status === 'updated';
  const kept = new Set(showKept ? last.reused_node_ids : []);
  const lines = (n) => [`B ${set(n.bag)}`, `λ ${set(n.cover)}`];
  const CH = 6.4, LH = 14, PX = 9, PY = 7;
  const size = (n) => [Math.max(...lines(n).map(l => l.length)) * CH + 2 * PX, 2 * LH + 2 * PY + 2];
  const depth = {}, leaves = [];
  (function walk(u, d) { depth[u] = d; const n = byId[u]; if (!n.children.length) leaves.push(u); n.children.forEach(c => walk(c, d + 1)); })(t.root, 0);
  const colW = Math.max(...t.nodes.map(n => size(n)[0])) + 22, rowH = 2 * LH + 2 * PY + 40;
  const x = {};
  (function place(u) { const n = byId[u]; if (!n.children.length) x[u] = leaves.indexOf(u);
    else { n.children.forEach(place); x[u] = n.children.reduce((a, c) => a + x[c], 0) / n.children.length; } })(t.root);
  const pos = (u) => [(x[u] + 0.5) * colW, depth[u] * rowH + rowH / 2];
  const links = svg('g'), nodes = svg('g');
  for (const n of t.nodes) for (const c of n.children) {
    const [x1, y1] = pos(n.id), [x2, y2] = pos(c), my = (y1 + y2) / 2;
    links.append(svg('path', { d: `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`, class: 'tree-edge' }));
  }
  for (const n of t.nodes) {
    const [cx, cy] = pos(n.id), [w, h] = size(n);
    const cls = ['bag', showKept ? (kept.has(n.id) ? 'kept' : 'new') : '', n.id === t.root ? 'is-root' : ''].filter(Boolean).join(' ');
    const g = svg('g', { class: cls, 'data-node': n.id });
    const title = svg('title');
    title.textContent = `node ${n.id}${n.id === t.root ? ' (root)' : ''}${showKept ? (kept.has(n.id) ? ', kept' : ', new') : ''}\nbag B = ${set(n.bag)}\ncover λ = ${set(n.cover)}`;
    g.append(title, svg('rect', { x: cx - w / 2, y: cy - h / 2, width: w, height: h, rx: 4 }));
    lines(n).forEach((l, i) => { const tx = svg('text', { x: cx - w / 2 + PX, y: cy - h / 2 + PY + 11 + i * LH, class: i === 0 ? 'b' : '' }); tx.textContent = l; g.append(tx); });
    const tag = n.id === t.root ? 'ROOT' : showKept ? (kept.has(n.id) ? 'KEPT' : 'NEW') : '';
    if (tag) { const tg = svg('text', { x: cx + w / 2 - 4, y: cy - h / 2 - 4, class: 'tag', 'text-anchor': 'end' }); tg.textContent = showKept && n.id === t.root ? `ROOT · ${kept.has(n.id) ? 'KEPT' : 'NEW'}` : tag; g.append(tg); }
    g.addEventListener('click', (ev) => { if (!TR.zoom.moved) { ev.stopPropagation(); setSelection({ type: 'node', name: n.id }); } });
    nodes.append(g);
  }
  TR.scene.append(links, nodes);
  TR.box = { x: 0, y: 0, w: leaves.length * colW, h: (Math.max(...Object.values(depth)) + 1) * rowH };
  if (!VIEW.treeOpened || STATE.last?.status !== 'undo') {
    const k = TR.zoom.fit(TR.box);
    if (k < 0.55) TR.zoom.oneToOne(TR.box, true);
    VIEW.treeOpened = true;
  }
  const w = Math.max(...t.nodes.map(n => n.cover.length));
  let c = `<strong>${t.nodes.length}</strong> node${t.nodes.length === 1 ? '' : 's'}, width <strong>${w}</strong> (largest cover λ).`;
  if (showKept) c += ` <span class="k-kept">green</span> = kept from the previous decomposition (${kept.size}), <span class="k-new">purple</span> = built anew (${t.nodes.length - kept.size}).`;
  else if (last?.status === 'proven_no') c += ' Rebuilt by exact search, since the old width became impossible.';
  else if (last?.status === 'built') c += ' Built by exact search.';
  cap.innerHTML = c + ' B = bag, λ = cover.';
}

/* ------------------------------------------------------------------ */
/* selection: across both drawings, and into the form                  */
/* ------------------------------------------------------------------ */
function setSelection(sel) {
  SELECTED = sel;
  applySelection();
  if (sel) fillForm(sel);
}
function applySelection() {
  const sel = SELECTED, t = STATE?.ghd, hg = STATE?.hypergraph;
  HG.scene.classList.toggle('focus', !!sel); TR.scene.classList.toggle('focus', !!sel);
  let V = new Set(), E = new Set(), N = new Set(), text = '';
  if (sel && hg) {
    if (sel.type === 'vertex') {
      V = new Set([sel.name]); E = new Set(incident(sel.name));
      N = new Set((t?.nodes || []).filter(n => n.bag.includes(sel.name)).map(n => n.id));
      text = `vertex ${sel.name}: in edges ${set([...E])}; in the bags of ${N.size} GHD node${N.size === 1 ? '' : 's'} (connected, as required)`;
    } else if (sel.type === 'edge') {
      const vs = hg.edges[sel.name] || [];
      V = new Set(vs); E = new Set([sel.name]);
      const covering = (t?.nodes || []).filter(n => vs.every(v => n.bag.includes(v)));
      N = new Set(covering.map(n => n.id));
      text = `edge ${sel.name} = ${set(vs)}: contained in the bag of node${covering.length === 1 ? '' : 's'} ${covering.map(n => n.id).join(', ') || '—'}` +
             `${(t?.nodes || []).some(n => n.cover.includes(sel.name)) ? '; used in a cover λ' : ''}`;
    } else if (sel.type === 'node') {
      const n = t.nodes.find(n => n.id === sel.name);
      V = new Set(n.bag); E = new Set(n.cover); N = new Set([n.id]);
      text = `node ${n.id}: bag B = ${set(n.bag)} is inside the union of its cover λ = ${set(n.cover)} (|λ| = ${n.cover.length})`;
    }
  }
  HG.scene.querySelectorAll('.hedge, .elabel').forEach(g => g.classList.toggle('on', E.has(g.dataset.edge)));
  HG.scene.querySelectorAll('.vertex').forEach(g => g.classList.toggle('on', V.has(g.dataset.vertex)));
  TR.scene.querySelectorAll('.bag').forEach(g => g.classList.toggle('on', N.has(Number(g.dataset.node))));
  $('selection-bar').hidden = !sel;
  $('selection-text').textContent = text;
}
$('clear-selection').onclick = () => setSelection(null);

function fillForm(sel) {
  if (!STATE?.started || sel.type === 'node') return;
  const f = FORM[KIND], name = sel.name;
  const toggle = (S) => S.has(name) ? S.delete(name) : S.add(name);
  if (sel.type === 'edge') {
    if (KIND === 'AddVar') toggle(f.edges);
    else if (KIND === 'DelConstr') f.name = name;
    else return;
  } else {
    if (KIND === 'DelVar') f.vertex = name;
    else if (KIND === 'AddConstr') toggle(f.vertices);
    else if (KIND === 'AddEq') { toggle(f.merge); if (!f.merge.has(f.into)) f.into = ''; }
    else if (KIND === 'DelEq') { f.vertex = name; f.parts = null; }
    else return;
  }
  buildForm();
}

/* ------------------------------------------------------------------ */
/* render                                                              */
/* ------------------------------------------------------------------ */
function deltaClass(before, after) { return after > before ? 'up' : after < before ? 'down' : 'same'; }
function render(state) {
  STATE = state;
  const started = state.started, hg = state.hypergraph;
  $('stats').hidden = !started; $('panels').hidden = !started; $('update-block').hidden = !started;
  $('empty-state').hidden = started;
  $('undo').disabled = !state.can_undo;
  $('strategy').value = state.settings.strategy; $('tighten').checked = state.settings.tighten;
  $('oracle').checked = state.settings.oracle; $('timeout').value = state.settings.timeout ?? '';
  const lim = state.limits;
  if (lim?.public) {
    $('limit-note').textContent = `Public demo: every answer is exact, so inputs are limited to ${lim.max_edges} edges and ` +
      `${lim.max_vertices} vertices, and each search stops after at most ${lim.max_timeout_s} s (default ${lim.default_timeout_s} s). ` +
      'Your hypergraph is private to this browser session.';
    $('timeout').max = lim.max_timeout_s;
  }
  const last = state.last;
  if (started) {
    $('stat-vertices').textContent = hg.vertices.length;
    $('stat-edges').textContent = Object.keys(hg.edges).length;
    $('stat-nodes').textContent = state.ghd ? state.ghd.nodes.length : '—';
    const w = $('stat-width');
    w.textContent = state.k == null ? '?' : (state.exact ? state.k : `≤ ${state.k}`);
    if (last && last.k_before != null && last.width_after != null && last.exact && last.status !== 'undo') {
      const c = deltaClass(last.k_before, last.width_after);
      w.append(el('span', { class: `delta ${c}`, text: c === 'up' ? `▲ from ${last.k_before}` : c === 'down' ? `▼ from ${last.k_before}` : 'unchanged' }));
    }
    $('stat-width-label').textContent = state.k == null ? 'ghw: unknown (time limit)' : state.exact ? 'ghw · proven' : 'ghw · upper bound';
    const v = $('stat-valid');
    v.textContent = state.valid == null ? '—' : state.valid ? 'VALID ✓' : 'INVALID ✗';
    v.className = 'stat-value badge ' + (state.valid ? 'ok' : 'bad');
  }
  $('generate-note').textContent = started ? 'Decompose again to start over from the text above.' : '';
  drawHypergraph(); drawTree();
  if (SELECTED) {   // keep a selection only if it still exists
    const ok = SELECTED.type === 'vertex' ? hg?.vertices.includes(SELECTED.name)
             : SELECTED.type === 'edge' ? !!hg?.edges[SELECTED.name]
             : !!state.ghd?.nodes.some(n => n.id === SELECTED.name);
    if (!ok) SELECTED = null;
  }
  applySelection();
  renderResult(last);
  renderLog(state.history);
  if (started) { FORM = defaults(); buildKinds(); }
}
function renderResult(r) {
  const box = $('result');
  if (!r || r.status === 'built') { box.hidden = true; return; }
  box.hidden = false;
  const ms = (r.seconds * 1000).toFixed(r.seconds < 0.1 ? 1 : 0) + ' ms';
  let title = r.description, lines = [], cls = 'same';
  if (r.status === 'updated') {
    const dropped = (r.notes || []).some(n => n.startsWith('ghw dropped'));
    lines.push(dropped
      ? `The incremental update kept ${r.reused_nodes} of ${r.old_nodes} old nodes at width ${r.k_before}; an exact search then found a smaller width, so a new GHD of width ${r.width_after} was built (${ms}).`
      : `Updated incrementally (${r.strategy}) in ${ms}: kept ${r.reused_node_ids.length} of ${r.old_nodes} old nodes, ${r.decomposer_calls} decomposer call${r.decomposer_calls === 1 ? '' : 's'}.`);
  } else if (r.status === 'proven_no') {
    lines.push(`No GHD of width ${r.k_before} exists any more (proved by exhaustive search); a new one of width ${r.width_after} was computed (${ms}).`);
  } else if (r.status === 'not_found') {
    lines.push(`Time limit reached after ${ms}: nothing found and nothing proven.`);
  } else if (r.status === 'undo') { title = 'Undone'; lines.push('The previous hypergraph and decomposition are restored.'); }
  if (r.k_before != null && r.width_after != null && r.exact && r.status !== 'undo') {
    cls = deltaClass(r.k_before, r.width_after);
    lines.push(cls === 'up' ? `ghw rose ${r.k_before} → ${r.width_after}.` : cls === 'down' ? `ghw dropped ${r.k_before} → ${r.width_after}.` : `ghw unchanged (${r.width_after}).`);
  }
  if (r.ghw_note) lines.push(r.ghw_note);
  if (r.oracle_ghw != null) lines.push(`exact oracle: ghw = ${r.oracle_ghw}${r.oracle_ghw === r.width_after ? ' (agrees)' : ''}`);
  box.className = `result ${cls}`;
  box.innerHTML = `<div class="title">${esc(title)}</div>` + lines.map(l => `<div class="line">${esc(l)}</div>`).join('') +
    ((r.notes || []).length ? `<details><summary>algorithm details (${r.notes.length})</summary>${r.notes.map(n => `<div>• ${esc(n)}</div>`).join('')}</details>` : '');
}
function renderLog(history) {
  const ol = $('log'); ol.replaceChildren();
  if (!history.length) { ol.append(el('li', { class: 'empty', text: 'nothing applied yet' })); return; }
  history.forEach((h, i) => {
    let change = '', cls = 'same';
    if (h.status === 'built') change = `ghw ${h.width_after}`;
    else if (h.status === 'undo') change = 'undo';
    else if (h.k_before != null && h.width_after != null) {
      cls = deltaClass(h.k_before, h.width_after);
      change = cls === 'same' ? `ghw ${h.width_after}` : `ghw ${h.k_before}→${h.width_after}`;
      if (!h.exact) change += ' (≤)';
    } else change = h.status;
    const info = h.status === 'updated' ? `${(h.seconds * 1000).toFixed(1)} ms · kept ${h.reused_node_ids.length}/${h.old_nodes}`
               : h.status === 'undo' ? '' : `${(h.seconds * 1000).toFixed(1)} ms`;
    ol.append(el('li', {}, el('span', { class: 'n', text: i + 1 }), el('span', { class: 'op', text: h.description, title: h.description }),
      el('span', { class: `change ${cls}`, text: change }), el('span', { text: info })));
  });
  ol.scrollTop = ol.scrollHeight;
}

loadExamples();
api('/api/state').then(render).catch(e => showError('graph-error', e.message));

(() => {
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const REQUIRED = ['date', 'pharmacy', 'initials', 'drug_name'];
const CHECK_SECTIONS = ['problem', 'action', 'recommend', 'result', 'outcome'];
const sectionTitle = id => SCHEMA.sections.find(s => s.id === id).title;

/* ---------- state ---------- */
const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const remembered = () => { try { return JSON.parse(localStorage.getItem('ci-defaults') || '{}'); } catch { return {}; } };
const remember = f => { try { localStorage.setItem('ci-defaults', JSON.stringify({ pharmacy: f.pharmacy || '', pharmacist: f.pharmacist || '', team_leader: f.team_leader || '' })); } catch {} };
const blank = () => ({ fields: { date: today(), signed_date: today(), ...remembered() }, checks: {} });

let state = blank();
let editingId = null;
let records = [];
const pads = {};

/* ---------- form rendering ---------- */
function fieldHTML(f) {
  const id = 'f_' + f.k;
  const ph = f.ph ? ` placeholder="${esc(f.ph)}"` : '';
  let ctl;
  if (f.type === 'textarea') ctl = `<textarea id="${id}" data-field="${f.k}" rows="${f.rows || 3}"${ph}></textarea>`;
  else if (f.type === 'select') ctl = `<select id="${id}" data-field="${f.k}"><option value="">Select</option>${f.options.map(o => `<option>${esc(o)}</option>`).join('')}</select>`;
  else ctl = `<input id="${id}" data-field="${f.k}" type="${f.type || 'text'}"${f.step ? ` step="${f.step}"` : ''}${f.min ? ` min="${f.min}"` : ''}${f.type === 'number' ? ' inputmode="decimal"' : ''}${ph} autocomplete="off">`;
  return `<div class="field${f.wide ? ' wide' : ''}" data-wrap="${f.k}"><label for="${id}">${esc(f.label)}${f.req ? '<span class="req" aria-hidden="true"> *</span>' : ''}</label>${ctl}</div>`;
}

function optHTML(key, label, ph) {
  return `<div class="opt" data-opt="${key}">
    <label class="opt-row"><input type="checkbox" data-check="${key}"><span class="box" aria-hidden="true"></span><span>${esc(label)}</span></label>
    <div class="opt-note"><div><input type="text" data-note="${key}" placeholder="${esc(ph || 'Details (optional)')}" aria-label="Details for ${esc(label)}" autocomplete="off"></div></div>
  </div>`;
}

function checksHTML(sec) {
  const c = CHECKS[sec];
  return `<div class="groups${c.cols ? ' cols' : ''}">` + c.groups.map(g => `
    <div class="group">
      ${g.title ? `<h3>${esc(g.title)}<b class="n" data-gcount></b></h3>` : ''}
      ${g.items.map(([id, label, ph]) => optHTML(c.prefix + id, label, ph)).join('')}
    </div>`).join('') + '</div>';
}

function signoffHTML() {
  const person = (nameKey, label, sigKey) => `
    <div class="signer">
      ${fieldHTML({ k: nameKey, label })}
      <div class="sig">
        <div class="sig-bar"><span>Signature</span><button type="button" class="link" data-sigclear="${sigKey}">Clear</button></div>
        <canvas data-sig="${sigKey}" width="640" height="200" aria-label="${esc(label)} signature"></canvas>
        <span class="sig-hint">Sign here</span>
      </div>
    </div>`;
  return `<div class="signers">${person('pharmacist', 'Intervention conducted by', 'sig_pharmacist')}${person('team_leader', 'Team leader or chief pharmacist', 'sig_leader')}</div>
          <div class="grid narrow top-gap">${fieldHTML({ k: 'signed_date', label: 'Date signed', type: 'date' })}</div>`;
}

function sectionBody(id) {
  switch (id) {
    case 'patient':   return `<div class="grid">${FIELDS.patient.map(fieldHTML).join('')}</div>`;
    case 'drug':      return `<div class="grid two">${FIELDS.drug.map(fieldHTML).join('')}</div>`;
    case 'action':    return checksHTML('action') + `<div class="grid top-gap">${fieldHTML(FIELDS.specifics)}</div>`;
    case 'outcome':   return `<div class="grid narrow">${fieldHTML(FIELDS.hours)}</div>` + checksHTML('outcome');
    case 'signoff':   return signoffHTML();
    default:          return checksHTML(id);
  }
}

function buildForm() {
  $('#form-sections').innerHTML = SCHEMA.sections.map(s => `
    <section class="panel" id="sec-${s.id}" data-sec="${s.id}">
      <header class="panel-head">
        <div><h2>${esc(s.title)}</h2>${s.hint ? `<p>${esc(s.hint)}</p>` : ''}</div>
        <span class="pill" data-count="${s.id}" hidden></span>
      </header>
      ${sectionBody(s.id)}
    </section>`).join('');

  $('#secnav').innerHTML = SCHEMA.sections.map(s =>
    `<a href="#/new" data-nav="${s.id}"><span>${esc(s.short)}</span><b class="n" data-ncount="${s.id}"></b></a>`).join('');

  $$('canvas[data-sig]').forEach(initPad);
}

function updateCounts() {
  $$('.group').forEach(g => {
    const n = $$('input[data-check]:checked', g).length, b = $('[data-gcount]', g);
    if (b) b.textContent = n ? n : '';
  });
  CHECK_SECTIONS.forEach(id => {
    const n = $$('input[data-check]:checked', $('#sec-' + id)).length;
    const pill = $(`[data-count="${id}"]`), nav = $(`[data-ncount="${id}"]`);
    pill.hidden = !n; pill.textContent = n + ' selected';
    nav.textContent = n ? n : '';
  });
}

function fillForm() {
  $$('[data-field]').forEach(el => { el.value = state.fields[el.dataset.field] ?? ''; el.closest('.field').classList.remove('invalid'); });
  $$('input[data-check]').forEach(el => {
    const c = state.checks[el.dataset.check];
    el.checked = !!c;
    el.closest('.opt').classList.toggle('on', !!c);
    $(`[data-note="${el.dataset.check}"]`).value = c ? c.note || '' : '';
  });
  Object.keys(pads).forEach(k => pads[k].load(state.fields[k]));
  updateCounts();
}

function setEditUI() {
  $('#edit-banner').hidden = editingId == null;
  $('#edit-text').textContent = editingId != null ? `Editing record #${editingId}` : '';
  $('#btn-save').textContent = editingId != null ? 'Save changes' : 'Save intervention';
}

/* ---------- signature pads ---------- */
function initPad(canvas) {
  const key = canvas.dataset.sig, ctx = canvas.getContext('2d'), box = canvas.closest('.sig');
  ctx.lineWidth = 3.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.strokeStyle = ctx.fillStyle = '#17231F';
  let drawing = false, last = null;
  const pos = e => { const r = canvas.getBoundingClientRect(); return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height }; };
  canvas.addEventListener('pointerdown', e => {
    drawing = true; canvas.setPointerCapture(e.pointerId); last = pos(e);
    ctx.beginPath(); ctx.arc(last.x, last.y, 1.8, 0, Math.PI * 2); ctx.fill(); e.preventDefault();
  });
  canvas.addEventListener('pointermove', e => {
    if (!drawing) return;
    const p = pos(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p;
  });
  const end = () => { if (!drawing) return; drawing = false; state.fields[key] = canvas.toDataURL('image/png'); box.classList.add('signed'); };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  pads[key] = {
    clear() { ctx.clearRect(0, 0, canvas.width, canvas.height); delete state.fields[key]; box.classList.remove('signed'); },
    load(url) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      box.classList.toggle('signed', !!url);
      if (url) { const img = new Image(); img.onload = () => ctx.drawImage(img, 0, 0); img.src = url; }
    },
  };
}

/* ---------- form events ---------- */
function bindForm() {
  const root = $('#form-sections');
  root.addEventListener('input', e => {
    const t = e.target;
    if (t.dataset.field) { state.fields[t.dataset.field] = t.value; t.closest('.field').classList.remove('invalid'); }
    else if (t.dataset.note && state.checks[t.dataset.note]) state.checks[t.dataset.note].note = t.value;
  });
  root.addEventListener('change', e => {
    const t = e.target;
    if (!t.dataset.check) return;
    const k = t.dataset.check;
    if (t.checked) state.checks[k] = { on: true, note: $(`[data-note="${k}"]`).value };
    else delete state.checks[k];
    t.closest('.opt').classList.toggle('on', t.checked);
    updateCounts();
  });
  root.addEventListener('click', e => {
    const b = e.target.closest('[data-sigclear]');
    if (b) pads[b.dataset.sigclear].clear();
  });

  $('#secnav').addEventListener('click', e => {
    const a = e.target.closest('[data-nav]');
    if (!a) return;
    e.preventDefault();
    $('#sec-' + a.dataset.nav).scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const spy = new IntersectionObserver(entries => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      $$('#secnav a').forEach(a => a.classList.toggle('on', a.dataset.nav === en.target.dataset.sec));
      const on = $('#secnav a.on'); if (on && window.innerWidth <= 820) on.scrollIntoView({ inline: 'center', block: 'nearest' });
    });
  }, { rootMargin: '-25% 0px -65% 0px' });
  $$('.panel').forEach(p => spy.observe(p));

  $('#btn-save').addEventListener('click', save);
  $('#btn-clear').addEventListener('click', () => {
    if (confirm('Clear everything you entered on this form?')) { state = blank(); fillForm(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  });
  $('#edit-cancel').addEventListener('click', () => {
    editingId = null; state = blank(); fillForm(); setEditUI(); location.hash = '#/records';
  });
}

async function save() {
  const missing = REQUIRED.filter(k => !String(state.fields[k] || '').trim());
  if (missing.length) {
    missing.forEach(k => $(`[data-wrap="${k}"]`).classList.add('invalid'));
    $(`[data-wrap="${missing[0]}"]`).scrollIntoView({ behavior: 'smooth', block: 'center' });
    toast('Fill in the highlighted fields to save.', 'error');
    return;
  }
  const btn = $('#btn-save'); btn.disabled = true;
  try {
    const res = await fetch(editingId != null ? `/api/interventions/${editingId}` : '/api/interventions', {
      method: editingId != null ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: state }),
    });
    if (!res.ok) throw new Error(await res.text());
    remember(state.fields);
    if (editingId != null) {
      editingId = null; state = blank(); fillForm(); setEditUI();
      location.hash = '#/records';
      toast('Changes saved.');
    } else {
      state = blank(); fillForm(); window.scrollTo({ top: 0, behavior: 'smooth' });
      toast('Intervention saved.', 'ok', { label: 'View records', fn: () => { location.hash = '#/records'; } });
    }
  } catch (err) {
    console.error(err);
    toast('Could not save. Check the server connection and try again.', 'error');
  } finally { btn.disabled = false; }
}

/* ---------- toast ---------- */
let toastTimer;
function toast(msg, kind = 'ok', action) {
  const t = $('#toast');
  t.className = 'show ' + kind;
  t.innerHTML = `<span>${esc(msg)}</span>` + (action ? `<button type="button">${esc(action.label)}</button>` : '');
  if (action) t.querySelector('button').onclick = () => { t.className = ''; action.fn(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, action ? 6000 : 3500);
}

/* ---------- records ---------- */
const fmtDate = s => { if (!s) return ''; const d = new Date(s + 'T00:00'); return isNaN(d) ? s : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); };

function selected(sec, checks) {
  const c = CHECKS[sec], out = [];
  c.groups.forEach(g => {
    const items = g.items.filter(([id]) => checks[c.prefix + id]).map(([id, label]) => ({ label, note: checks[c.prefix + id].note }));
    if (items.length) out.push({ title: g.title, items });
  });
  return out;
}

function resultStatus(checks) {
  const has = k => !!checks['res_' + k];
  if (has('acc_prescriber') || has('acc_team') || has('acc_patient')) return { cls: 'ok', label: 'Accepted' };
  if (has('not_accepted')) return { cls: 'bad', label: 'Not accepted' };
  if (has('unknown')) return { cls: 'mid', label: 'Unknown' };
  if (has('other')) return { cls: 'mid', label: 'Other' };
  return { cls: 'none', label: 'Not recorded' };
}

function filtered() {
  const q = $('#q').value.trim().toLowerCase(), ph = $('#f-pharmacy').value, from = $('#f-from').value, to = $('#f-to').value;
  return records.filter(r => {
    const f = r.data.fields;
    if (ph && f.pharmacy !== ph) return false;
    if (from && (f.date || '') < from) return false;
    if (to && (f.date || '') > to) return false;
    if (q) {
      const hay = [f.initials, f.mrn, f.drug_name, f.disease, f.pharmacist, f.ward, f.pharmacy].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderRecords() {
  const sel = $('#f-pharmacy'), cur = sel.value;
  const names = [...new Set(records.map(r => r.data.fields.pharmacy).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">All</option>' + names.map(n => `<option>${esc(n)}</option>`).join('');
  sel.value = names.includes(cur) ? cur : '';

  const list = filtered();
  const hours = list.reduce((a, r) => a + (parseFloat(r.data.fields.hours) || 0), 0);
  const withResult = list.filter(r => resultStatus(r.data.checks).cls !== 'none');
  const accepted = withResult.filter(r => resultStatus(r.data.checks).cls === 'ok').length;
  $('#stats').innerHTML = `
    <div><strong>${list.length}</strong><span>${list.length === 1 ? 'intervention' : 'interventions'}</span></div>
    <div><strong>${+hours.toFixed(2)}</strong><span>hours spent</span></div>
    <div><strong>${withResult.length ? Math.round(accepted / withResult.length * 100) + '%' : '\u2013'}</strong><span>accepted, of those with a result</span></div>`;

  if (!list.length) {
    $('#rec-list').innerHTML = records.length
      ? '<div class="empty"><p>No records match these filters.</p></div>'
      : '<div class="empty"><p>No interventions recorded yet.</p><a class="btn primary" href="#/new">Record the first one</a></div>';
    return;
  }
  $('#rec-list').innerHTML = list.map(r => {
    const f = r.data.fields, st = resultStatus(r.data.checks);
    const probs = selected('problem', r.data.checks).map(g => g.title);
    return `<button type="button" class="rec" data-id="${r.id}">
      <span class="rec-date">${esc(fmtDate(f.date))}</span>
      <span class="rec-pt"><strong>${esc(f.initials)}</strong><small>${esc(f.mrn || 'No MRN')}</small></span>
      <span class="rec-drug"><strong>${esc(f.drug_name)}</strong><small>${esc(f.disease || '')}</small></span>
      <span class="rec-tags">${probs.map(p => `<i class="tag">${esc(p)}</i>`).join('')}</span>
      <span class="status ${st.cls}">${st.label}</span>
    </button>`;
  }).join('');
}

async function loadRecords() {
  try {
    const res = await fetch('/api/interventions', { cache: 'no-store' });
    if (!res.ok) throw new Error(res.statusText);
    records = await res.json();
    renderRecords();
  } catch (err) {
    console.error(err);
    $('#rec-list').innerHTML = '<div class="empty"><p>Could not load records. Check the server connection and refresh.</p></div>';
  }
}

/* ---------- detail dialog ---------- */
function detailHTML(r) {
  const f = r.data.fields, c = r.data.checks;
  const kv = (label, v) => v ? `<div><dt>${esc(label)}</dt><dd>${esc(v)}</dd></div>` : '';
  const meta = [fmtDate(f.date), f.pharmacy, f.ward && 'Ward ' + f.ward].filter(Boolean).join(', ');
  const blocks = CHECK_SECTIONS.map(sec => {
    const groups = selected(sec, c);
    if (!groups.length) return '';
    return `<section class="d-sec"><h3>${esc(sectionTitle(sec))}</h3>${groups.map(g => `
      ${g.title ? `<h4>${esc(g.title)}</h4>` : ''}
      <ul>${g.items.map(i => `<li>${esc(i.label)}${i.note ? `<span class="d-note">${esc(i.note)}</span>` : ''}</li>`).join('')}</ul>`).join('')}
      ${sec === 'action' && f.specifics ? `<h4>Intervention specifics</h4><p class="d-text">${esc(f.specifics)}</p>` : ''}
      ${sec === 'outcome' && f.hours ? `<h4>Time spent</h4><p>${esc(f.hours)} hours</p>` : ''}
    </section>`;
  }).join('');
  const sigs = [['pharmacist', 'sig_pharmacist', 'Intervention conducted by'], ['team_leader', 'sig_leader', 'Team leader or chief pharmacist']]
    .filter(([n, s]) => f[n] || f[s])
    .map(([n, s, l]) => `<div class="d-sig"><span>${esc(l)}</span><strong>${esc(f[n] || '')}</strong>${f[s] ? `<img src="${esc(f[s])}" alt="Signature">` : ''}</div>`).join('');

  return `
    <div class="d-head">
      <div><h2 id="detail-title">${esc(f.drug_name)} <small>for ${esc(f.initials)}</small></h2><p>${esc(meta)}</p></div>
      <button type="button" class="icon-btn" data-close aria-label="Close">\u00d7</button>
    </div>
    <div class="d-body">
      <dl class="d-grid">${kv('MRN', f.mrn)}${kv('Age', f.age)}${kv('Gender', f.gender)}${kv('Weight', f.weight)}${kv('Height', f.height)}${kv('Condition', f.disease)}</dl>
      ${f.labs ? `<section class="d-sec"><h3>Lab readings and notes</h3><p class="d-text">${esc(f.labs)}</p></section>` : ''}
      ${blocks}
      ${sigs ? `<section class="d-sec"><h3>Sign-off${f.signed_date ? ', ' + esc(fmtDate(f.signed_date)) : ''}</h3><div class="d-sigs">${sigs}</div></section>` : ''}
      <p class="d-foot">Record #${r.id}. Created ${esc(new Date(r.created_at).toLocaleString())}${r.updated_at !== r.created_at ? `, edited ${esc(new Date(r.updated_at).toLocaleString())}` : ''}.</p>
    </div>
    <div class="d-actions">
      <button type="button" class="btn danger-ghost" data-del="${r.id}">Delete</button>
      <span class="spacer"></span>
      <button type="button" class="btn ghost" data-print>Print</button>
      <button type="button" class="btn primary" data-edit="${r.id}">Edit</button>
    </div>`;
}

function openDetail(id) {
  const r = records.find(x => x.id === id); if (!r) return;
  const dlg = $('#detail'); dlg.innerHTML = detailHTML(r);
  if (!dlg.open) dlg.showModal();
  dlg.scrollTop = 0;
}

function bindRecords() {
  ['q', 'f-pharmacy', 'f-from', 'f-to'].forEach(id => $('#' + id).addEventListener('input', renderRecords));
  $('#rec-list').addEventListener('click', e => {
    const b = e.target.closest('.rec'); if (b) openDetail(+b.dataset.id);
  });
  const dlg = $('#detail');
  dlg.addEventListener('click', async e => {
    if (e.target === dlg || e.target.closest('[data-close]')) return dlg.close();
    if (e.target.closest('[data-print]')) return window.print();
    const ed = e.target.closest('[data-edit]');
    if (ed) {
      const r = records.find(x => x.id === +ed.dataset.edit);
      state = JSON.parse(JSON.stringify(r.data)); state.checks ||= {}; editingId = r.id;
      dlg.close(); setEditUI(); fillForm(); location.hash = '#/new'; window.scrollTo(0, 0);
      return;
    }
    const del = e.target.closest('[data-del]');
    if (del && confirm('Delete this intervention record? This cannot be undone.')) {
      const res = await fetch('/api/interventions/' + del.dataset.del, { method: 'DELETE' });
      if (res.ok) { dlg.close(); toast('Record deleted.'); loadRecords(); } else toast('Could not delete the record.', 'error');
    }
  });
  $('#btn-export').addEventListener('click', () => exportCSV(filtered()));
}

/* ---------- CSV export ---------- */
function exportCSV(list) {
  const flat = (sec, r) => selected(sec, r.data.checks).flatMap(g => g.items.map(i => (g.title ? g.title + ': ' : '') + i.label + (i.note ? ` (${i.note})` : ''))).join('; ');
  const cols = [
    ['ID', r => r.id], ['Date', r => r.data.fields.date], ['Pharmacy', r => r.data.fields.pharmacy], ['Ward', r => r.data.fields.ward],
    ['Pharmacy MRN', r => r.data.fields.mrn], ['Patient initials', r => r.data.fields.initials], ['Age', r => r.data.fields.age],
    ['Gender', r => r.data.fields.gender], ['Weight', r => r.data.fields.weight], ['Height', r => r.data.fields.height],
    ['Lab readings and notes', r => r.data.fields.labs], ['Drug', r => r.data.fields.drug_name], ['Condition', r => r.data.fields.disease],
    ['Drug-related problem', r => flat('problem', r)], ['What was done', r => flat('action', r)],
    ['Intervention specifics', r => r.data.fields.specifics], ['Recommendations', r => flat('recommend', r)],
    ['Result', r => flat('result', r)], ['Hours', r => r.data.fields.hours], ['Expected outcome', r => flat('outcome', r)],
    ['Pharmacist', r => r.data.fields.pharmacist], ['Team leader', r => r.data.fields.team_leader], ['Date signed', r => r.data.fields.signed_date],
    ['Created', r => r.created_at],
  ];
  const q = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const csv = '\ufeff' + [cols.map(c => q(c[0])).join(','), ...list.map(r => cols.map(c => q(c[1](r))).join(','))].join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `clinical-interventions-${today()}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
}

/* ---------- routing ---------- */
function route() {
  const onRecords = location.hash.startsWith('#/records');
  $('#view-new').hidden = onRecords;
  $('#view-records').hidden = !onRecords;
  $$('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === (onRecords ? 'records' : 'new')));
  if (onRecords) loadRecords();
  window.scrollTo(0, 0);
}

buildForm(); bindForm(); bindRecords(); fillForm(); setEditUI();
window.addEventListener('hashchange', route);
route();
})();

(() => {
'use strict';
const { $, esc, toast, monthLabel } = window.CI;

/* ---------- admin session (kept in memory only; locks itself after 15 idle minutes) ---------- */
const IDLE_MS = 15 * 60 * 1000;
let pin = null, lastUse = 0;
const unlocked = () => !!pin && Date.now() - lastUse < IDLE_MS;
const touch = () => { lastUse = Date.now(); };

function refreshBtn() {
  const b = $('#btn-settings');
  b.classList.toggle('on', unlocked());
  b.title = unlocked() ? 'Settings (admin unlocked)' : 'Settings (admin PIN required)';
}
function lock() { pin = null; refreshBtn(); }
setInterval(() => { if (pin && !unlocked()) lock(); }, 30000);

async function adminFetch(url, opts = {}) {
  const res = await fetch(url, { ...opts, headers: { ...(opts.headers || {}), 'X-Admin-Pin': pin || '' } });
  if (res.status === 403 || res.status === 429) lock(); else touch();
  return res;
}
async function errorText(res) {
  try { return (await res.json()).detail || res.statusText; } catch { return res.statusText; }
}

/* ---------- PIN prompt ---------- */
function ensure() {
  if (unlocked()) { touch(); return Promise.resolve(true); }
  return askPin();
}

function askPin() {
  return new Promise(async resolve => {
    const dlg = $('#pin-dialog');
    let status = { configured: true };
    try { status = await (await fetch('/api/admin/status')).json(); } catch { /* assume configured */ }
    dlg.innerHTML = `
      <form class="pin-form" autocomplete="off">
        <h2 id="pin-title">Admin PIN</h2>
        <p>${status.configured ? 'Deleting records and the admin settings need the admin PIN.'
          : 'No admin PIN is set. Add <code>ADMIN_PIN</code> to the container environment and restart it.'}</p>
        ${status.configured ? '<input type="password" name="pin" aria-label="Admin PIN" autocomplete="off" required>' : ''}
        <p class="pin-err" role="alert"></p>
        <div class="pin-actions">
          <button type="button" class="btn ghost" data-cancel>${status.configured ? 'Cancel' : 'Close'}</button>
          ${status.configured ? '<button type="submit" class="btn primary">Unlock</button>' : ''}
        </div>
      </form>`;
    let done = false;
    const finish = v => { if (done) return; done = true; if (dlg.open) dlg.close(); resolve(v); };
    dlg.onclose = () => finish(false);
    $('[data-cancel]', dlg).onclick = () => finish(false);
    const form = $('form', dlg), input = $('input', dlg);
    form.onsubmit = async e => {
      e.preventDefault();
      const err = $('.pin-err', dlg), val = input.value;
      const res = await fetch('/api/admin/verify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: val }),
      });
      if (res.ok) { pin = val; touch(); refreshBtn(); finish(true); }
      else { err.textContent = await errorText(res); input.select(); }
    };
    dlg.showModal();
    if (input) setTimeout(() => input.focus(), 0);
  });
}

/* ---------- settings panel ---------- */
async function renderPanel(dlg) {
  const [status, rep] = await Promise.all([
    fetch('/api/admin/status').then(r => r.json()),
    fetch('/api/report?month=all', { cache: 'no-store' }).then(r => r.json()),
  ]);
  const months = rep.options.months, names = rep.options.pharmacies;
  dlg.innerHTML = `
    <div class="d-head">
      <div><h2 id="adm-title">Settings</h2><p>Admin tools. Editing a record never needs the PIN; deleting does.</p></div>
      <button type="button" class="icon-btn" data-close aria-label="Close">\u00d7</button>
    </div>
    <div class="d-body">
      ${status.default_pin ? '<div class="banner">The admin PIN is still the default. Change <code>ADMIN_PIN</code> in your docker yml and restart the container.</div>' : ''}
      <section class="adm-card">
        <h3>Back up and restore</h3>
        <p>Download every record as a file, or add records from a backup. Records already present are skipped.</p>
        <div class="adm-row">
          <button type="button" class="btn ghost" id="adm-backup">Download backup</button>
          <label class="btn ghost">Restore from backup<input type="file" id="adm-file" accept="application/json,.json" hidden></label>
        </div>
      </section>
      <section class="adm-card">
        <h3>Rename a pharmacy</h3>
        <p>Fixes typos and merges spelling variants across all records.</p>
        <div class="grid two">
          <div class="field"><label for="adm-from">Current name</label>
            <select id="adm-from">${names.map(p => `<option>${esc(p.name)}</option>`).join('') || '<option value="">No pharmacies yet</option>'}</select></div>
          <div class="field"><label for="adm-to">New name</label><input id="adm-to" type="text" autocomplete="off"></div>
        </div>
        <div class="adm-row"><button type="button" class="btn ghost" id="adm-rename">Rename</button></div>
      </section>
      <section class="adm-card danger">
        <h3>Delete records in bulk</h3>
        <p>Permanently removes every record that matches the month and pharmacy below.</p>
        <div class="grid two">
          <div class="field"><label for="adm-month">Month</label>
            <select id="adm-month"><option value="all">All months</option>${months.map(m => `<option value="${m.value}">${esc(monthLabel(m.value))} (${m.count})</option>`).join('')}</select></div>
          <div class="field"><label for="adm-ph">Pharmacy</label>
            <select id="adm-ph"><option value="">All pharmacies</option>${names.map(p => `<option>${esc(p.name)}</option>`).join('')}</select></div>
        </div>
        <div class="adm-row"><button type="button" class="btn ghost" id="adm-find">Find matching records</button></div>
        <div id="adm-confirm" hidden>
          <p id="adm-found"></p>
          <div class="field"><label for="adm-type">Type DELETE to confirm</label><input id="adm-type" type="text" autocomplete="off"></div>
          <div class="adm-row"><button type="button" class="btn danger" id="adm-delete" disabled>Delete these records</button></div>
        </div>
      </section>
    </div>
    <div class="d-actions">
      <button type="button" class="btn ghost" id="adm-lock">Lock admin</button>
      <span class="spacer"></span>
      <button type="button" class="btn primary" data-close>Done</button>
    </div>`;
}

const sel = () => ({ month: $('#adm-month').value, pharmacy: $('#adm-ph').value });
const post = (url, body) => adminFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

async function refreshAfterChange() {
  window.CI.loadPharmacies();
  window.CI.reloadRecords();
  await renderPanel($('#admin-dialog'));
}

function bindPanel() {
  const dlg = $('#admin-dialog');
  dlg.addEventListener('click', async e => {
    if (e.target === dlg || e.target.closest('[data-close]')) return dlg.close();
    const id = (e.target.closest('button') || {}).id;
    if (!id) return;
    if (id === 'adm-lock') { lock(); dlg.close(); toast('Admin locked.'); return; }

    if (id === 'adm-backup') {
      const res = await adminFetch('/api/admin/backup');
      if (!res.ok) return toast(await errorText(res), 'error');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(await res.blob());
      a.download = `clinical-interventions-backup-${window.CI.today()}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    if (id === 'adm-rename') {
      const old = $('#adm-from').value, neu = $('#adm-to').value.trim();
      if (!old || !neu) return toast('Choose a pharmacy and enter the new name.', 'error');
      if (!confirm(`Rename "${old}" to "${neu}" on every record?`)) return;
      const res = await post('/api/admin/rename-pharmacy', { old, new: neu });
      if (!res.ok) return toast(await errorText(res), 'error');
      toast(`Renamed on ${(await res.json()).changed} records.`);
      return refreshAfterChange();
    }
    if (id === 'adm-find') {
      const res = await post('/api/admin/delete-matching', { ...sel(), dry_run: true });
      if (!res.ok) return toast(await errorText(res), 'error');
      const n = (await res.json()).count;
      $('#adm-found').textContent = n ? `${n} ${n === 1 ? 'record matches' : 'records match'}. This cannot be undone.` : 'No records match.';
      $('#adm-confirm').hidden = !n;
      $('#adm-type').value = ''; $('#adm-delete').disabled = true;
      return;
    }
    if (id === 'adm-delete') {
      const res = await post('/api/admin/delete-matching', { ...sel(), dry_run: false });
      if (!res.ok) return toast(await errorText(res), 'error');
      toast(`Deleted ${(await res.json()).count} records.`);
      return refreshAfterChange();
    }
  });
  dlg.addEventListener('input', e => {
    if (e.target.id === 'adm-type') $('#adm-delete').disabled = e.target.value.trim() !== 'DELETE';
  });
  dlg.addEventListener('change', async e => {
    if (e.target.id === 'adm-month' || e.target.id === 'adm-ph') { $('#adm-confirm').hidden = true; return; }
    if (e.target.id !== 'adm-file') return;
    const file = e.target.files[0]; e.target.value = '';
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const records = Array.isArray(parsed) ? parsed : parsed.records;
      if (!Array.isArray(records)) throw new Error('not a backup');
      if (!confirm(`Restore from this backup (${records.length} records)? Records already here are skipped.`)) return;
      const res = await post('/api/admin/restore', { records });
      if (!res.ok) return toast(await errorText(res), 'error');
      const r = await res.json();
      toast(`Restored ${r.added} records, skipped ${r.skipped}.`);
      refreshAfterChange();
    } catch { toast('That file is not a valid backup.', 'error'); }
  });
}

async function openSettings() {
  if (!(await ensure())) return;
  const dlg = $('#admin-dialog');
  try { await renderPanel(dlg); } catch { return toast('Could not load settings.', 'error'); }
  if (!dlg.open) dlg.showModal();
}

bindPanel();
$('#btn-settings').addEventListener('click', openSettings);
refreshBtn();
window.CIAdmin = { ensure, fetch: adminFetch, lock, unlocked };
})();

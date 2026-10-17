(() => {
'use strict';
const { $, esc, monthLabel } = window.CI;

const st = { month: 'latest', pharmacy: '' };
let submitted = '';
try { submitted = localStorage.getItem('ci-submitted-by') || ''; } catch { /* optional */ }
let last = null;

const todayMDY = () => {
  const d = new Date();
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}`;
};
const rowHTML = r => `<tr class="${r.kind}"><td>${esc(r.label)}</td><td class="num">${r.value ?? ''}</td></tr>`;

function updateLink() {
  const q = new URLSearchParams({ month: st.month, pharmacy: st.pharmacy, submitted_by: submitted });
  $('#rep-xlsx').href = '/api/report/xlsx?' + q;
}

function render(data) {
  last = data;
  const mSel = $('#rep-month'), pSel = $('#rep-pharmacy');
  mSel.innerHTML = '<option value="all">All months</option>' +
    data.options.months.map(m => `<option value="${m.value}">${esc(monthLabel(m.value))} (${m.count})</option>`).join('');
  mSel.value = st.month;
  pSel.innerHTML = '<option value="">All pharmacies</option>' +
    data.options.pharmacies.map(p => `<option value="${esc(p.name)}">${esc(p.name)} (${p.count})</option>`).join('');
  pSel.value = [...pSel.options].some(o => o.value === st.pharmacy) ? st.pharmacy : '';

  const meta = [
    ['Name of pharmacy', st.pharmacy || 'All pharmacies'],
    ['Department', 'In and Out Patient'],
    ['Submitted by', submitted || '\u00a0'],
    ['Date', todayMDY()],
    ['Month', monthLabel(st.month)],
  ];
  $('#report-sheet').innerHTML = `
    <article class="sheet">
      <header class="sheet-head">
        <h2>NATIONAL HEALTH FUND PHARMACY SERVICES DELIVERY</h2>
        <h3>CLINICAL INTERVENTION REPORTING FORM</h3>
      </header>
      <dl class="sheet-meta">${meta.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      ${data.count === 0 ? '<p class="rep-empty no-print">No interventions match this month and pharmacy, so every figure is 0.</p>' : ''}
      <div class="sheet-tables">
        <section>
          <h4>Table 1: Drug Related Problems and Intervention</h4>
          <table class="rep"><thead><tr><th>Drug Related Problems (DRP)</th><th class="num">Total</th></tr></thead>
            <tbody>${data.tables.t1.map(rowHTML).join('')}</tbody></table>
        </section>
        <section>
          <h4>Table 2: Recommendations and Expected Outcomes</h4>
          <table class="rep"><tbody>${data.tables.t2.map(rowHTML).join('')}</tbody></table>
        </section>
      </div>
      <p class="sheet-count">Based on ${data.count} ${data.count === 1 ? 'intervention' : 'interventions'}. Each intervention is counted once for every box ticked.</p>
      <div class="sheet-sign">
        <div><span></span>Signature</div>
        <div><span></span>Name, pharmacy manager / chief pharmacist</div>
        <div><span></span>Date</div>
      </div>
    </article>`;
  updateLink();
}

async function load() {
  try {
    const q = new URLSearchParams({ month: st.month, pharmacy: st.pharmacy });
    const res = await fetch('/api/report?' + q, { cache: 'no-store' });
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    st.month = data.month;
    render(data);
  } catch (err) {
    console.error(err);
    $('#report-sheet').innerHTML = '<div class="empty"><p>Could not load the report. Check the server connection and refresh.</p></div>';
  }
}

$('#rep-month').addEventListener('change', e => { st.month = e.target.value; load(); });
$('#rep-pharmacy').addEventListener('change', e => { st.pharmacy = e.target.value; load(); });
$('#rep-submitted').value = submitted;
$('#rep-submitted').addEventListener('input', e => {
  submitted = e.target.value;
  try { localStorage.setItem('ci-submitted-by', submitted); } catch { /* optional */ }
  if (last) render(last);
  const el = $('#rep-submitted'); el.focus();
});
$('#rep-print').addEventListener('click', () => window.print());

window.CI.onShow = view => { if (view === 'report') load(); };
if (location.hash.startsWith('#/report')) load();
})();

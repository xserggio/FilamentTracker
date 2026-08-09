/* Filament Tracker — interface */

const S = {
  filaments: [], prints: [], projects: [], groups: [], stats: {}, settings: {}, dbPath: '',
  dryDays: {}, materials: [], spoolTare: {}, backups: {},
  brands: [], spoolTypes: ['plastic', 'cardboard', 'metal', 'other'],
  lang: 'en', view: 'dashboard',
  inv: { search: '', material: '', sort: 'name', lowOnly: false, stockOnly: false, archived: false },
  his: { search: '', filament: '', from: '', to: '', failedOnly: false, group: '',
         sort: 'date', dir: 'desc' },
  // prints picked by hand, by id. Kept apart from the filters on purpose: you
  // search for one thing, tick two, search for another, tick two more.
  picked: new Set(), lastPick: null,
  editingPrint: null, editingFilament: null, rollTarget: null, sparesTarget: null,
  failTarget: null, detailTarget: null, confirmFn: null, grouping: [],
  infoPrint: null, infoProject: null,
  mismatchTarget: null,
  slice: null, sliceTimer: null, snoozed: new Set(), sliceFolder: null,
  ams: [], amsTarget: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ---------- translation ----------
   t('inv.spare', {n: 2}) resolves {key} substitutions and picks the plural form
   of strings written as "singular|plural" based on n. */
function t(key, vars) {
  const dict = I18N[S.lang] || I18N.en;
  let s = dict[key];
  if (s === undefined) s = (I18N.en[key] !== undefined ? I18N.en[key] : key);
  if (s.includes('|')) {
    const forms = s.split('|');
    s = (vars && Number(vars.n) === 1) ? forms[0] : forms[1];
  }
  if (vars) {
    s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m));
  }
  return s;
}

const locale = () => (LANGS[S.lang] || LANGS.en).locale;

/* The stylesheet declares the palette twice and picks by data-theme, so
   switching is one attribute and no reload. "auto" follows Windows, which the
   browser reports through prefers-color-scheme. */
const systemDark = () => !window.matchMedia
  || window.matchMedia('(prefers-color-scheme: dark)').matches;

function applyTheme(theme) {
  const want = theme || S.settings.theme || 'dark';
  const dark = want === 'auto' ? systemDark() : want !== 'light';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

function applyI18n() {
  document.documentElement.lang = S.lang;
  $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}

/* ---------- helpers ---------- */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function g(n) {
  n = Number(n) || 0;
  return n.toLocaleString(locale(), { maximumFractionDigits: n >= 100 ? 0 : 1 });
}
function kg(n) {
  n = Number(n) || 0;
  if (n < 1000) return g(n) + ' g';
  return (n / 1000).toLocaleString(locale(), { maximumFractionDigits: 2 }) + ' kg';
}
function fdate(iso) {
  if (!iso) return '—';
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  if (isNaN(d)) return String(iso);
  return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: '2-digit' });
}
function fmonth(ym) {
  const d = new Date(ym + '-01T00:00:00');
  if (isNaN(d)) return ym;
  return d.toLocaleDateString(locale(), { month: 'short', year: '2-digit' });
}
// Catalogue temperatures are Celsius; the setting only changes how they read.
function temp(c) {
  if (c == null) return '—';
  return (S.settings.temp_unit === 'F')
    ? Math.round(c * 9 / 5 + 32) + ' °F'
    : Math.round(c) + ' °C';
}

/* Money is only ever shown in the currency it was entered in; nothing is
   converted. Intl knows the symbol, where it goes and how many decimals each
   currency uses, so 1234.5 reads as 1.234,50 € in Spanish and ¥1,235 in
   Japanese without a symbol table to maintain. */
function money(n) {
  const cur = S.settings.currency || 'EUR';
  try {
    return Number(n || 0).toLocaleString(locale(), { style: 'currency', currency: cur });
  } catch (e) {
    return Number(n || 0).toFixed(2) + ' ' + cur;
  }
}

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthStart = () => todayISO().slice(0, 8) + '01';

function statusColor(f) {
  if (f.empty || f.low) return 'var(--danger)';
  if (f.pct < 35) return 'var(--warn)';
  return 'var(--ok)';
}

function toast(msg, kind = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = `<span class="dot"></span><span>${esc(msg)}</span>`;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 220); }, 2800);
}

/* ---------- bridge to Python ----------
   Actions that merely confirm (save, delete…) return data = null, so failure needs
   a value of its own — otherwise a successful save would look like an error. */
const FAIL = Symbol('call-failed');
const failed = (r) => r === FAIL;

async function call(method, arg) {
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api[method]) { toast('API: ' + method, 'error'); return FAIL; }
  try {
    const res = arg === undefined ? await api[method]() : await api[method](arg);
    if (!res || res.ok === false) {
      toast((res && res.error) || 'Error', 'error');
      return FAIL;
    }
    return res.data;
  } catch (e) {
    toast(String((e && e.message) || e), 'error');
    return FAIL;
  }
}

function absorb(d) {
  S.filaments = d.filaments; S.prints = d.prints; S.projects = d.projects;
  S.groups = d.groups || [];
  S.stats = d.stats; S.settings = d.settings; S.dryDays = d.dry_days || {};
  S.materials = d.materials || []; S.dbPath = d.db_path;
  S.spoolTare = d.spool_tare || {}; S.backups = d.backups || {};
  if (d.brands) S.brands = d.brands;
  if (d.spool_types) S.spoolTypes = d.spool_types;
  if (d.settings && d.settings.lang && I18N[d.settings.lang]) S.lang = d.settings.lang;
}

async function reload() {
  const d = await call('refresh', {});
  if (failed(d) || !d) return;
  absorb(d);
  renderAll();
}

/* ---------- navigation ---------- */
const VIEWS = ['dashboard', 'inventory', 'history', 'stats', 'settings'];

function setView(v) {
  S.view = v;
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === v));
  $$('.view').forEach((s) => { s.hidden = s.id !== 'view-' + v; });
  $('#viewTitle').textContent = t('nav.' + v);
  $('#viewSub').textContent = t('view.' + v + '.sub');

  const act = $('#topActions');
  act.innerHTML = '';
  if (v === 'inventory' || v === 'history') {
    const label = v === 'inventory' ? t('action.newFilament') : t('nav.newPrint');
    // The slicer button only earns its place next to New print when there is
    // actually a folder with plates in it -- otherwise it is a dead end for
    // anyone not running Bambu Studio.
    const slices = v === 'history' && S.sliceFolder && S.sliceFolder.plates;
    act.innerHTML = `${slices ? `<button class="btn ghost" id="taSlices">
      <svg viewBox="0 0 24 24" class="ic"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
      ${esc(t('action.fromSlice'))}</button>` : ''}
      <button class="btn primary" id="taAction">
      <svg viewBox="0 0 24 24" class="ic"><path d="M12 5v14M5 12h14"/></svg> ${esc(label)}</button>`;
    $('#taAction').onclick = () => (v === 'inventory' ? openFilament(null) : openPrint(null));
    if (slices) $('#taSlices').onclick = openSliceList;
  }
  renderAll();
}

/* ---------- main render ---------- */
function renderAll() {
  // the dot means "there is something on the panel", so it counts what is on
  // the panel: silencing an alert takes it off the badge too
  const muted = readMutes();
  const pending = buildAlerts().filter((a) => !muted[a.key]).length;
  const badge = $('#navAlerts');
  badge.hidden = pending === 0;
  badge.textContent = pending;

  if (S.view === 'dashboard') renderDashboard();
  if (S.view === 'inventory') renderInventory();
  if (S.view === 'history') renderHistory();
  if (S.view === 'ams') renderAms();
  if (S.view === 'stats') renderStats();
  if (S.view === 'settings') renderSettings();
  fillSelects();
}

function fillSelects() {
  const mats = [...new Set(S.filaments.map((f) => f.material))].sort();
  const im = $('#invMaterial');
  im.innerHTML = `<option value="">${esc(t('inv.allMaterials'))}</option>` +
    mats.map((m) => `<option>${esc(m)}</option>`).join('');
  im.value = S.inv.material;

  const hf = $('#hisFilament');
  hf.innerHTML = `<option value="">${esc(t('his.allFilaments'))}</option>` +
    S.filaments.map((f) => `<option value="${f.id}">${esc(f.name)}</option>`).join('');
  hf.value = S.his.filament;

  $('#groupList').innerHTML = S.groups
    .map((x) => `<option value="${esc(x.name)}">`).join('');
  const gsel = $('#hisGroup');
  const keep = S.his.group;
  gsel.innerHTML = `<option value="">${esc(t('his.allGroups'))}</option>`
    + `<option value="none">${esc(t('his.noGroup'))}</option>`
    + S.groups.map((x) => `<option value="${x.id}">${esc(x.name)} · ${g(x.grams)} g</option>`).join('');
  gsel.value = keep;

  $('#projectList').innerHTML = S.projects.map((p) => `<option value="${esc(p)}">`).join('');
  // the material list offers everything the app knows how to dry, not just what is in use
  const allMats = [...new Set([...S.materials, ...mats])].sort();
  $('#materialList').innerHTML = allMats.map((m) => `<option value="${esc(m)}">`).join('');
}


/* ---------- brand and spool-type dropdowns ----------
   Brand stopped being free text so it can hook into the tare table: picking it
   (together with the spool type) tells the app how much the empty spool weighs.
   "Other brand…" opens a text field so nothing is locked out. */
const OTHER = '__other__';

function brandOptions(current) {
  const list = [...new Set([...S.brands, ...(current ? [current] : [])])]
    .filter(Boolean).sort((a, b) => a.localeCompare(b, locale()));
  const known = list.some((b) => b === current);
  return `<option value="">${esc(t('brand.none'))}</option>` +
    list.map((b) => `<option value="${esc(b)}"${b === current ? ' selected' : ''}>${esc(b)}</option>`).join('') +
    `<option value="${OTHER}"${current && !known ? ' selected' : ''}>${esc(t('brand.other'))}</option>`;
}

function typeOptions(current) {
  const cur = current || 'plastic';
  return S.spoolTypes.map((k) =>
    `<option value="${k}"${k === cur ? ' selected' : ''}>${esc(t('type.' + k))}</option>`).join('');
}

/* Wires a brand <select> to its companion text <input> and reports changes. */
function wireBrand(selId, otherId, onChange) {
  const sel = $(selId);
  const other = $(otherId);
  const sync = () => {
    other.hidden = sel.value !== OTHER;
    if (!other.hidden) other.focus();
    if (onChange) onChange();
  };
  sel.onchange = sync;
  other.oninput = () => { if (onChange) onChange(); };
  other.hidden = sel.value !== OTHER;
}

const readBrand = (selId, otherId) =>
  ($(selId).value === OTHER ? $(otherId).value.trim() : $(selId).value);

function setBrand(selId, otherId, value) {
  const sel = $(selId);
  sel.innerHTML = brandOptions(value);
  const other = $(otherId);
  const isOther = sel.value === OTHER;
  other.value = isOther ? (value || '') : '';
  other.hidden = !isOther;
}

// tare for a given brand and type, with the generic figure as fallback
function tareFor(brand, kind) {
  const norm = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const key = Object.keys(S.spoolTare).find((k) => norm(k) === norm(brand));
  const e = (key && S.spoolTare[key]) || {};
  return e[kind || 'plastic'] ?? e.plastic ?? e.cardboard
    ?? ({ plastic: 220, cardboard: 160, metal: 320, other: 220 }[kind] || 220);
}

/* ---------- KPIs ---------- */
const ICONS = {
  spool: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.4"/>',
  boxes: '<path d="M12 3.4 3.2 7.8 12 12.2l8.8-4.4z"/><path d="M3.2 12.4 12 16.8l8.8-4.4"/><path d="M3.2 16.8 12 21.2l8.8-4.4"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2.2"/><path d="M3.5 10h17M8 3.2v3.4M16 3.2v3.4"/>',
  alert: '<path d="M12 4.6 2.9 19.4h18.2z"/><path d="M12 10v4"/><circle cx="12" cy="16.8" r=".9" fill="currentColor" stroke="none"/>',
  scale: '<path d="M12 4.6v14.8M7 19.4h10"/><path d="M4 9.6h16l-3.4 5.2H7.4z"/>',
  printer: '<path d="M7 9V4h10v5"/><rect x="3.5" y="9" width="17" height="7" rx="2"/><path d="M7 14h10v6H7z"/>',
  gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="m12 17 4.2-5"/>',
  trash: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 12.5h9L17.5 7"/><path d="M10 11v5M14 11v5"/>',
  drop: '<path d="M12 3.5c3.6 4 6 7 6 9.8a6 6 0 0 1-12 0c0-2.8 2.4-5.8 6-9.8z"/>',
  coin: '<ellipse cx="12" cy="7" rx="7.5" ry="3.4"/><path d="M4.5 7v10c0 1.9 3.4 3.4 7.5 3.4s7.5-1.5 7.5-3.4V7"/><path d="M4.5 12c0 1.9 3.4 3.4 7.5 3.4s7.5-1.5 7.5-3.4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  palette: '<circle cx="12" cy="12" r="8.2"/><circle cx="9.2" cy="9.6" r="1.1" fill="currentColor" stroke="none"/><circle cx="14.8" cy="9.6" r="1.1" fill="currentColor" stroke="none"/><circle cx="12" cy="15.2" r="1.1" fill="currentColor" stroke="none"/>',
  link: '<path d="M10.5 13.5a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 0 0-5.7-5.7l-1.4 1.4"/><path d="M13.5 10.5a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 1 0 5.7 5.7l1.4-1.4"/>',
  bang: '<path d="M12 3.6 2.6 19.8h18.8z"/><path d="M12 9.6v4.4"/><circle cx="12" cy="17" r="1" fill="currentColor" stroke="none"/>',
  pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
};
const svg = (n) => `<svg viewBox="0 0 24 24">${ICONS[n] || ''}</svg>`;

function renderKpis(el, defs) {
  el.innerHTML = defs.map((d, i) => `
    <div class="kpi t-${d.tone || 'neutral'}${d.action ? ' clickable' : ''}"
         ${d.action ? `data-k="${i}"` : ''}${d.hint ? ` title="${esc(d.hint)}"` : ''}>
      <div class="kpi-head">
        <span class="label">${esc(d.label)}</span>
        <span class="kpi-ic">${svg(d.icon)}</span>
      </div>
      <div class="value">${esc(d.value)}</div>
      <div class="foot">${esc(d.foot)}${d.action ? '<span class="go">&rarr;</span>' : ''}</div>
    </div>`).join('');
  $$('[data-k]', el).forEach((n) => { n.onclick = defs[+n.dataset.k].action; });
}

/* Built in one place so the badge counts exactly what the list shows, rather
   than its own approximation of it. That drift is what put a red dot on
   Inventory while the alerts -- and the only way to silence them -- were on the
   dashboard. */
function buildAlerts() {
  const active = S.filaments.filter((f) => !f.archived);
  const lows = active.filter((f) => f.low || f.empty);
  const alerts = [];
    // A roll whose ledger has gone negative is not empty -- there is plastic on
    // the spool and the books are wrong. Saying "empty" there is the app telling
    // you something you can see is false, which is the fastest way to lose the
    // reader's trust in everything else it says.
    lows.forEach((f) => alerts.push({
      // Running low and having run out are different news, and the second one
      // matters more -- so they are different keys. Silencing "getting low"
      // must not also silence "it is gone", and when a low spool empties the
      // old mute stops matching anything and is swept away.
      key: f.mismatch ? `mismatch:${f.id}` : (f.empty ? `empty:${f.id}` : `low:${f.id}`),
      color: f.mismatch ? 'var(--warn)' : (f.empty ? 'var(--danger)' : 'var(--warn)'),
      title: f.name, id: f.id,
      sub: f.mismatch ? t('alert.mismatch', { n: g(f.over) })
        : f.empty
          ? (f.stock > 0 ? t('alert.emptyStock', { n: f.stock }) : t('alert.emptyNoStock'))
          : (f.stock > 0 ? t('alert.lowStock', { n: f.stock }) : t('alert.lowNoStock')),
      val: f.mismatch ? `+${g(f.over)} g` : g(f.remaining) + ' g',
      weigh: f.mismatch,
    }));
    active.filter((f) => f.needs_dry).forEach((f) => alerts.push({
      key: `dry:${f.id}`,
      color: 'var(--info-text)', title: f.name, id: f.id,
      sub: t('alert.dry', {
        n: f.days_since_dry, limit: f.dry_limit, mat: f.material,
        since: f.dried_at ? t('alert.dry.sinceDried') : t('alert.dry.sinceOpen'),
      }),
      val: f.days_since_dry + ' d',
    }));
    active.filter((f) => !f.low && !f.empty && f.stock === 0 && f.pct < 45).forEach((f) => alerts.push({
      key: `nospare:${f.id}`,
      color: 'var(--muted)', title: f.name, sub: t('alert.noSpare'),
      val: g(f.remaining) + ' g', id: f.id,
    }));
  return alerts;
}

/* Silenced alerts live in the settings rather than a table: it is a handful of
   keys that come and go, and it means the list travels with the database. */
function readMutes() {
  try { return JSON.parse(S.settings.alert_mutes || '{}'); } catch (e) { return {}; }
}
function saveMutes(m) {
  S.settings.alert_mutes = JSON.stringify(m);
  call('save_settings', { alert_mutes: S.settings.alert_mutes });
}
function muteAlert(key) {
  const m = readMutes();
  m[key] = todayISO();
  saveMutes(m);
  // renderAll, not just the panel: the badge is drawn there and silencing one
  // has to take it off the count as well
  renderAll();
  toast(t('toast.alertMuted'));
}
function unmuteAll() {
  saveMutes({});
  renderAll();
  toast(t('toast.alertsBack'));
}

/* ---------- jumps with filters already applied ---------- */
function gotoInventory({ lowOnly = false, stockOnly = false, sort = 'name', material = '' } = {}) {
  S.inv = { search: '', material, sort, lowOnly, stockOnly, archived: false };
  $('#invSearch').value = ''; $('#invMaterial').value = material;
  $('#invSort').value = sort; $('#invLowOnly').checked = lowOnly;
  $('#invStockOnly').checked = stockOnly; $('#invArchived').checked = false;
  setView('inventory');
}

function gotoHistory({ from = '', to = '', failedOnly = false, search = '', group = '' } = {}) {
  // the sort is not a filter: arriving from a tile changes what is shown, not
  // the order it was asked for
  S.his = { ...S.his, search, filament: '', from, to, failedOnly, group };
  $('#hisSearch').value = search; $('#hisFilament').value = '';
  $('#hisFrom').value = from; $('#hisTo').value = to;
  $('#hisFailed').checked = failedOnly;
  $('#hisGroup').value = group;
  setView('history');
}

/* ---------- DASHBOARD ---------- */
function renderDashboard() {
  const st = S.stats;
  const active = S.filaments.filter((f) => !f.archived);
  const lows = active.filter((f) => f.low || f.empty);

  renderKpis($('#kpis'), [
    { label: t('kpi.available'), value: kg(st.available_g), icon: 'spool',
      foot: t('kpi.availableFoot', { v: kg(st.open_g) }), hint: t('kpi.hint.inventory'),
      action: () => gotoInventory() },
    { label: t('kpi.spares'), value: String(st.stock_spools ?? 0), icon: 'boxes',
      foot: t('kpi.sparesFoot', { n: active.length }), hint: t('kpi.hint.spares'),
      action: () => gotoInventory({ stockOnly: true, sort: 'stock' }) },
    { label: t('kpi.month'), value: kg(st.month_grams), icon: 'calendar', tone: 'ok',
      foot: t('kpi.monthFoot', { n: st.month_prints || 0 }), hint: t('kpi.hint.month'),
      action: () => gotoHistory({ from: monthStart(), to: todayISO() }) },
    { label: t('kpi.low'), value: String(lows.length), icon: 'alert',
      tone: lows.length ? 'bad' : 'ok',
      foot: lows.length ? t('kpi.lowFoot') : t('kpi.lowFootOk'), hint: t('kpi.hint.low'),
      action: () => gotoInventory({ lowOnly: true, sort: 'pct' }) },
  ]);

  let alerts = buildAlerts();

  // An alert you have read and cannot act on today is noise for as long as it
  // takes you to buy more filament, and noise you cannot switch off teaches you
  // to ignore the panel. Silencing one keeps it out of the way until its
  // situation clears -- fit a new roll, dry the spool, weigh it -- and then it
  // is allowed to be news again. Nothing is silenced forever, because nothing
  // stays true forever.
  const muted = readMutes();
  const live = new Set(alerts.map((a) => a.key));
  const stale = Object.keys(muted).filter((k) => !live.has(k));
  if (stale.length) {
    stale.forEach((k) => delete muted[k]);
    saveMutes(muted);
  }
  const shown = alerts.filter((a) => !muted[a.key]);
  const hidden = alerts.length - shown.length;

  $('#alertCount').textContent = shown.length;
  $('#alertMuted').hidden = !hidden;
  $('#alertMuted').textContent = t('alert.muted', { n: hidden });
  alerts = shown;
  $('#alerts').innerHTML = alerts.length ? alerts.map((a, i) => `
    <div class="alert" data-fil="${a.id}" data-alert="${i}">
      <span class="dot" style="background:${a.color}"></span>
      <span class="txt"><b>${esc(a.title)}</b><small>${esc(a.sub)}</small></span>
      <span class="val">${esc(a.val)}</span>
      ${a.weigh ? `<button class="icon-btn sm" data-weigh="${a.id}"
        title="${esc(t('roll.mode.adjust'))}">${svg('scale')}</button>` : ''}
      <button class="icon-btn sm" data-mute="${i}"
              title="${esc(t('alert.mute'))}">${svg('close')}</button>
    </div>`).join('')
    : `<div class="empty"><b>${esc(t('dash.noAlerts'))}</b>${esc(t('dash.noAlertsSub'))}</div>`;
  $$('#alerts [data-weigh]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      const f = S.filaments.find((x) => x.id == b.dataset.weigh);
      if (f) openMismatch(f);
    };
  });
  $$('#alerts [data-mute]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); muteAlert(alerts[+b.dataset.mute].key); };
  });
  $$('#alerts .alert').forEach((el) => {
    el.onclick = () => {
      const f = S.filaments.find((x) => x.id == el.dataset.fil);
      setView('inventory');
      if (f) openDetail(f);
    };
  });

  $('#miniMonths').innerHTML = columns((S.stats.by_month || []).slice(-6));

  const recent = S.prints.slice(0, 7);
  $('#recentPrints').innerHTML = recent.length ? `<table class="table">${recent.map((p) => `
    <tr>
      <td class="date" style="width:110px">${fdate(p.date)}</td>
      <td class="proj">${esc(p.project)}${failTag(p)}</td>
      <td><div class="fchips">${p.items.map(chip).join('')}</div></td>
      <td class="total right" style="width:90px">${g(p.total)} g</td>
    </tr>`).join('')}</table>`
    : `<div class="empty"><b>${esc(t('dash.noPrints'))}</b>${esc(t('dash.noPrintsSub'))}</div>`;
}

const failTag = (p) => (p.failed ? `<span class="tag failed">${esc(t('his.failed'))}</span>` : '');

function chip(it) {
  return `<span class="fchip"><i style="background:${esc(it.hex)}"></i>
    <span>${esc(it.name)}</span><b>${g(it.grams)} g</b></span>`;
}

/* ---------- INVENTORY ---------- */
// PLA lasts months, PETG and nylon do not: the warning comes from the material limit.
function dryBadge(f) {
  if (f.days_since_dry == null) return '';
  const vars = { d: fdate(f.dried_at), n: f.days_since_dry, limit: f.dry_limit, mat: f.material };
  const title = f.dried_at ? t('inv.dry.titleDried', vars) : t('inv.dry.titleNever', vars);
  if (f.needs_dry) {
    return `<span class="dry warn" title="${esc(title)}">${svg('drop')}${esc(t('inv.dry.badge'))}</span>`;
  }
  return f.dried_at
    ? `<span class="dry ok" title="${esc(title)}">${svg('drop')}${f.days_since_dry} d</span>` : '';
}

const spareBrands = (f) => [...new Set((f.spares || []).map((s) => s.brand).filter(Boolean))];

// The spares tag only shows when it adds something, and names the brand when it
// differs from the fitted roll's.
function stockTag(f) {
  // the books disagreeing with the shelf outranks anything else the chip says
  if (f.mismatch) {
    return `<span class="tag warn-tag">${esc(t('inv.mismatchTag'))}</span>`;
  }
  // nothing is fitted, so the stock is the whole story and says so plainly
  if (f.sealed) {
    return `<span class="tag sealed">${esc(t('inv.sealed'))}</span>`;
  }
  if (f.stock > 0) {
    const b = spareBrands(f);
    let extra = '';
    if (b.length === 1 && b[0] !== f.roll_brand) extra = ` · ${b[0]}`;
    else if (b.length > 1) extra = ` · ${t('inv.brands', { n: b.length })}`;
    const title = (f.spares || [])
      .map((s) => `${s.brand || t('roll.noBrand')} · ${g(s.weight)} g`).join('\n');
    return `<span class="tag stock" title="${esc(title)}">${
      esc(t('inv.spare', { n: f.stock }) + extra)}</span>`;
  }
  if (f.low || f.empty || f.pct < 45) return `<span class="tag nostock">${esc(t('inv.noSpare'))}</span>`;
  return '';
}

function renderInventory() {
  const q = S.inv.search.toLowerCase();
  const list = S.filaments.filter((f) => {
    if (!S.inv.archived && f.archived) return false;
    if (S.inv.material && f.material !== S.inv.material) return false;
    if (S.inv.lowOnly && !(f.low || f.empty)) return false;
    if (S.inv.stockOnly && f.stock <= 0) return false;
    if (q && !`${f.name} ${f.material} ${f.color} ${f.roll_brand}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const sorters = {
    name: (a, b) => a.name.localeCompare(b.name, locale()),
    pct: (a, b) => a.pct - b.pct,
    remaining: (a, b) => b.remaining - a.remaining,
    used: (a, b) => b.total_used - a.total_used,
    stock: (a, b) => b.stock - a.stock || a.pct - b.pct,
  };
  list.sort(sorters[S.inv.sort]);

  $('#filamentCards').innerHTML = list.length ? list.map((f) => {
    const col = statusColor(f);
    return `<div class="fcard ${f.low || f.empty ? 'is-low' : ''} ${f.archived ? 'is-archived' : ''}"
                 data-detail="${f.id}">
      <div class="fcard-top">
        <span class="swatch" style="background:${esc(f.hex)}"></span>
        <span class="fcard-title" role="button" tabindex="0">
          <b title="${esc(f.name)}">${esc(f.name)}</b>
          <span class="fcard-meta">
            <span class="tag">${esc(f.material)}</span>
            ${f.roll_brand ? `<span class="tag brand">${esc(f.roll_brand)}</span>` : ''}
            ${stockTag(f)}
            ${dryBadge(f)}
          </span>
        </span>
        <button class="icon-btn" data-edit="${f.id}" title="${esc(t('inv.edit'))}">${svg('pencil')}</button>
      </div>

      ${f.sealed ? `
      <div class="sealed-line">
        <span class="g">${g(f.spare_g)}<small> g</small></span>
        <span class="lbl">${esc(t('inv.sealedStock', { n: f.stock }))}</span>
      </div>` : `
      <div class="gauge">
        <div class="gauge-nums">
          <span class="g">${g(f.remaining)}<small> / ${g(f.roll_weight)} g</small></span>
          <span class="p" style="color:${col}">${f.pct.toFixed(0)}%</span>
        </div>
        <div class="bar"><i style="width:${Math.min(100, f.pct)}%;background:${col}"></i></div>
        ${f.mismatch ? `<div class="mismatch">${esc(t('inv.mismatch', { n: g(f.over) }))}</div>` : ''}
      </div>`}

      <div class="fcard-foot">
        <div class="frow">
        <span class="used" title="${esc(f.sealed ? t('fil.sealedHint') : t('inv.openedTitle', {
          d: fdate(f.roll_opened), used: kg(f.total_used) }))}">${
          f.sealed ? esc(t('inv.sealed'))
            : (f.days_open != null ? `${f.days_open} d` : fdate(f.roll_opened))}</span>
        <div class="stepper">
          <button data-stock="${f.id}" data-delta="-1" title="${esc(t('inv.spareRemove'))}">−</button>
          <button class="count ${spareBrands(f).length > 1 ? 'mixed' : ''}"
                  data-spares="${f.id}" title="${esc(t('inv.spareOpen'))}">${f.stock}</button>
          <button data-stock="${f.id}" data-delta="1" title="${esc(t('inv.spareAdd'))}">+</button>
        </div>
        ${f.sealed ? '' : `
        <button class="icon-btn sm" data-adjust="${f.id}"
                title="${esc(t('roll.mode.adjust'))}">${svg('scale')}</button>
        <button class="icon-btn sm" data-dry="${f.id}"
                title="${esc(t('roll.mode.dry'))}">${svg('drop')}</button>`}
        </div>
        <button class="btn sm" data-roll="${f.id}">${
          esc(t(f.sealed ? 'inv.openRoll' : 'inv.newRoll'))}</button>
      </div>
    </div>`;
  }).join('')
    : `<div class="card"><div class="empty"><b>${esc(t('inv.noResults'))}</b>${esc(t('inv.noResultsSub'))}</div></div>`;

  const find = (id) => S.filaments.find((f) => f.id == id);
  $$('#filamentCards [data-edit]').forEach((b) => { b.onclick = () => openFilament(find(b.dataset.edit)); });
  // The whole card opens the sheet, not just the name: everything on it is
  // about that filament, and hunting for the one word that was clickable was
  // needless. The controls in the footer keep their own jobs.
  $$('#filamentCards [data-detail]').forEach((card) => {
    const open = () => openDetail(find(card.dataset.detail));
    card.onclick = (e) => {
      if (e.target.closest('button, .stepper, input, select, a, textarea')) return;
      open();
    };
    const title = card.querySelector('.fcard-title');
    if (title) title.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    };
  });
  $$('#filamentCards [data-roll]').forEach((b) => { b.onclick = () => openRoll(find(b.dataset.roll)); });
  $$('#filamentCards [data-adjust]').forEach((b) => {
    b.onclick = () => openRoll(find(b.dataset.adjust), 'adjust');
  });
  $$('#filamentCards [data-dry]').forEach((b) => {
    b.onclick = () => openRoll(find(b.dataset.dry), 'dry');
  });
  $$('#filamentCards [data-spares]').forEach((b) => { b.onclick = () => openSpares(find(b.dataset.spares)); });
  $$('#filamentCards [data-stock]').forEach((b) => {
    b.onclick = async () => {
      const f = find(b.dataset.stock);
      await call('set_stock', { id: f.id, stock: Math.max(0, f.stock + Number(b.dataset.delta)) });
      await reload();
      if (!$('#sparesModal').hidden) renderSpares();
    };
  });
}


/* ---------- MODAL: filament detail sheet ---------- */

/* Printing settings, with where they came from spelled out: a figure published
   by the manufacturer and a generic guess for the material should not look the
   same on screen. */
function specsBlock(sp, fil) {
  if (!sp || (sp.extruder == null && sp.density == null)) return '';
  const src = sp.source === 'generic' || sp.source === 'none'
    ? t(sp.source === 'none' ? 'detail.specsNone' : 'detail.specsGeneric', { mat: fil.material })
    : t('detail.specsFrom', { brand: sp.brand || fil.roll_brand || '', product: sp.product || '' });
  return `
    <h3 class="sub-head">${esc(t('detail.printing'))}<small>${esc(src)}</small></h3>
    <div class="det-specs">
      ${sp.extruder != null ? `<span class="spec"><i>${esc(t('detail.nozzle'))}</i><b>${esc(temp(sp.extruder))}</b></span>` : ''}
      ${sp.bed != null ? `<span class="spec"><i>${esc(t('detail.bed'))}</i><b>${esc(temp(sp.bed))}</b></span>` : ''}
      ${sp.density != null ? `<span class="spec"><i>${esc(t('detail.density'))}</i><b>${
        sp.density.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} g/cm³</b></span>` : ''}
    </div>`;
}
async function openDetail(f) {
  if (!f) return;
  S.detailTarget = f.id;
  $('#detailTitle').textContent = f.name;
  $('#detailBody').innerHTML = '';
  show('#detailModal');

  const d = await call('filament_detail', f.id);
  if (failed(d) || !d) { hide('#detailModal'); return; }
  const fil = d.filament;
  const col = statusColor(fil);
  const totalG = d.prints.reduce((a, p) => a + p.grams, 0);

  $('#detailBody').innerHTML = `
    <div class="det-head">
      <span class="swatch big" style="background:${esc(fil.hex)}"></span>
      <div class="det-sum">
        <div class="fcard-meta">
          <span class="tag">${esc(fil.material)}</span>
          ${fil.roll_brand ? `<span class="tag brand">${esc(fil.roll_brand)}</span>` : ''}
          ${stockTag(fil)}${dryBadge(fil)}
        </div>
        <div class="gauge-nums">
          <span class="g">${g(fil.remaining)}<small> / ${g(fil.roll_weight)} g</small></span>
          <span class="p" style="color:${col}">${fil.pct.toFixed(0)}%</span>
        </div>
        <div class="bar"><i style="width:${Math.min(100, fil.pct)}%;background:${col}"></i></div>
      </div>
    </div>

    ${specsBlock(d.specs, fil)}
    ${fil.price ? `<div class="det-price">
      <span class="spec"><i>${esc(t('detail.price'))}</i><b>${esc(money(fil.price))}</b></span>
      <span class="spec"><i>${esc(t('detail.perKg'))}</i><b>${esc(money(fil.price_per_g * 1000))}</b></span>
    </div>` : ''}

    <h3 class="sub-head">${esc(t('detail.rolls'))}</h3>
    ${d.rolls.length ? `<div class="det-rolls">${d.rolls.map((r) => `
      <div class="det-roll ${r.current ? 'is-current' : ''}">
        <span class="dr-date">${fdate(r.opened_at)}</span>
        <span class="dr-brand">${esc(r.brand || t('roll.noBrand'))}${
          r.current ? ` <em>${esc(t('detail.current'))}</em>` : ''}</span>
        <span class="dr-used">${esc(t('detail.consumed', { g: g(r.used) + ' g' }))}
          <small> / ${g(r.weight)} g</small></span>
        <span class="dr-days">${r.days != null ? esc(t('detail.lasted', { n: r.days })) : ''}</span>
        ${r.adjusted_at ? `<span class="dr-fix">${esc(t('detail.weighed', {
          date: fdate(r.adjusted_at), n: (r.adjust > 0 ? '+' : '') + g(r.adjust),
          held: g(r.weight + r.adjust),
        }))}</span>` : ''}
      </div>`).join('')}</div>`
      : `<div class="spares-empty">${esc(t('detail.noRolls'))}</div>`}

    <h3 class="sub-head">${esc(t('detail.prints'))}
      <small>${esc(t('detail.total', { n: d.prints.length, g: kg(totalG) }))}</small></h3>
    ${d.prints.length ? `<div class="det-prints"><table class="table">${d.prints.map((p) => `
      <tr data-pinfo="${p.id}">
        <td class="date" style="width:104px">${fdate(p.date)}</td>
        <td class="proj">${esc(p.project)}${p.failed ? failTag(p) : ''}</td>
        <td class="total right" style="width:78px">${g(p.grams)} g</td>
      </tr>`).join('')}</table></div>`
      : `<div class="spares-empty">${esc(t('detail.noPrints'))}</div>`}`;

  // the prints a filament went into are the obvious next question about it,
  // and reading one should not mean closing this and finding it in the history
  wirePrintRows($('#detailBody'));
}

/* Any table of prints, anywhere, opens the print's sheet on click. */
function wirePrintRows(root) {
  $$('tr[data-pinfo]', root).forEach((tr) => {
    tr.onclick = (e) => {
      if (e.target.closest('button, input, a, [data-gid]')) return;
      openPrintInfo(S.prints.find((p) => p.id == tr.dataset.pinfo));
    };
  });
}

/* ---------- MODAL: spares ---------- */
function openSpares(f) {
  S.sparesTarget = f.id;
  $('#sparesTitle').textContent = t('spares.title', { name: f.name });
  $('#sparesInfo').innerHTML = t('spares.info', {
    brand: f.roll_brand ? ` <b>${esc(f.roll_brand)}</b>` : t('spares.infoNoBrand'),
    rem: `<b>${g(f.remaining)} g</b>`,
  });
  renderSpares();
  show('#sparesModal');
}

function renderSpares() {
  const f = S.filaments.find((x) => x.id === S.sparesTarget);
  if (!f) return;
  $('#sparesList').innerHTML = (f.spares || []).length ? f.spares.map((s) => `
    <div class="spare-row" data-sid="${s.id}">
      <select class="sp-brand">${brandOptions(s.brand)}</select>
      <select class="sp-type">${typeOptions(s.spool_type)}</select>
      <input type="number" class="sp-weight" min="1" step="10" value="${s.weight}">
      <input type="number" class="sp-price" min="0" step="0.01" value="${s.price || ''}"
             placeholder="${esc(t('spares.price'))}">
      <button class="icon-btn" title="${esc(t('print.remove'))}">${svg('close')}</button>
    </div>`).join('')
    : `<div class="spares-empty">${esc(t('spares.empty'))}</div>`;

  $$('#sparesList .spare-row').forEach((row) => {
    const sid = Number(row.dataset.sid);
    const save = async () => {
      const sel = row.querySelector('.sp-brand');
      await call('update_spare', {
        spare_id: sid,
        brand: sel.value === OTHER ? (prompt(t('brand.otherPh')) || '') : sel.value,
        spool_type: row.querySelector('.sp-type').value,
        weight: Number(row.querySelector('.sp-weight').value) || 1000,
        price: Number(row.querySelector('.sp-price').value) || 0,
      });
      await reload();
    };
    row.querySelector('.sp-brand').onchange = save;
    row.querySelector('.sp-type').onchange = save;
    row.querySelector('.sp-price').onchange = save;
    row.querySelector('.sp-weight').onchange = save;
    row.querySelector('button').onclick = async () => {
      await call('delete_spare', sid);
      await reload();
      renderSpares();
    };
  });
}

/* ---------- HISTORY ---------- */

/* How each column compares, always ascending -- the direction is applied on
   top. The date falls back to the id so that two prints on the same day keep
   the order they were entered in rather than shuffling on every render. */
const HIS_SORTS = {
  date: (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id),
  // by the name on the row, not by the group above it: sorting a column by
  // something it does not show reads as broken, and the group has its own
  // filter for when you want its prints together
  project: (a, b) => a.project.localeCompare(
    b.project, locale(), { sensitivity: 'base', numeric: true }),
  // by how many colours it took, which is the only thing about a list of
  // filaments that can be put in order
  filaments: (a, b) => a.items.length - b.items.length,
  total: (a, b) => a.total - b.total,
  cost: (a, b) => (a.cost || 0) - (b.cost || 0),
};

/* Which way a column opens on the first click. Dates and amounts are asked
   about from the top -- the biggest, the most recent -- and names from A. */
const HIS_FIRST = { project: 'asc' };

function sortHistory(key) {
  const same = S.his.sort === key;
  S.his.dir = same ? (S.his.dir === 'asc' ? 'desc' : 'asc')
                   : (HIS_FIRST[key] || 'desc');
  S.his.sort = key;
  renderHistory();
}

function filteredPrints() {
  const q = S.his.search.toLowerCase();
  return S.prints.filter((p) => {
    // the group counts as part of the name: searching "casa UP" should find
    // its pieces whatever each one happens to be called
    if (q && !`${p.project} ${p.group_name || ''}`.toLowerCase().includes(q)) return false;
    if (S.his.group === 'none' && p.group_name) return false;
    if (S.his.group && S.his.group !== 'none' && String(p.group_id) !== S.his.group) return false;
    if (S.his.filament && !p.items.some((i) => i.filament_id == S.his.filament)) return false;
    if (S.his.from && p.date < S.his.from) return false;
    if (S.his.to && p.date > S.his.to) return false;
    if (S.his.failedOnly && !p.failed) return false;
    return true;
  }).sort((a, b) => {
    const by = (HIS_SORTS[S.his.sort] || HIS_SORTS.date)(a, b);
    return S.his.dir === 'asc' ? by : -by;
  });
}

const byPrintId = (id) => S.prints.find((p) => p.id === id);

function clearPicked() {
  S.picked.clear();
  S.lastPick = null;
  renderHistory();
}

function renderHistory() {
  const list = filteredPrints();
  // nothing filtered, nothing to unfilter: the button only exists when it does
  // something, which also stops it reading as "clear the table"
  const h = S.his;
  $('#hisClear').hidden = !(h.search || h.filament || h.from || h.to || h.failedOnly || h.group);
  // Two ways to say which prints, because neither covers the other. Filters
  // are how you say "the ten with casa UP in the name"; ticking is how you say
  // "those five", which no filter can express. Ticking wins when there is any,
  // and the button always says how many it is about to touch.
  const target = S.picked.size ? [...S.picked].map(byPrintId).filter(Boolean) : list;
  const btn = $('#hisGroupThese');
  btn.hidden = !target.length
    || (!S.picked.size && list.length === S.prints.length);
  btn.textContent = t('his.groupThese', { n: target.length });
  $('#hisPickNone').hidden = !S.picked.size;

  $$('#historyTable th[data-sort]').forEach((th) => {
    const on = th.dataset.sort === S.his.sort;
    if (on) th.dataset.dir = S.his.dir;
    else delete th.dataset.dir;
    th.setAttribute('aria-sort', on
      ? (S.his.dir === 'asc' ? 'ascending' : 'descending') : 'none');
  });

  // the cost column only earns its space once something has a price
  const showCost = !!S.stats.has_prices;
  $$('#historyTable .cost-col').forEach((el) => { el.hidden = !showCost; });
  $('#historyTable tbody').innerHTML = list.map((p) => `
    <tr class="${S.picked.has(p.id) ? 'picked' : ''}" data-pinfo="${p.id}">
      <td class="pick-col"><input type="checkbox" class="tick" data-pick="${p.id}"
          ${S.picked.has(p.id) ? 'checked' : ''} title="${esc(t('his.pick'))}"></td>
      <td class="date">${fdate(p.date)}</td>
      <td class="proj" title="${esc(p.notes)}">${esc(p.project)}${
        (p.group_name || p.failed) ? `<span class="proj-tags">${
          p.group_name ? `<span class="gchip" data-gid="${p.group_id}">${esc(p.group_name)}</span>` : ''
        }${failTag(p)}</span>` : ''
      }</td>
      <td><div class="fchips">${p.items.map(chip).join('')}</div></td>
      <td class="total right">${g(p.total)} g</td>
      <td class="cost right">${p.cost ? esc(money(p.cost)) : ''}</td>
      <td>
        <div class="row-actions">
          ${p.url ? `<button class="icon-btn" data-plink="${p.id}"
             title="${esc(t('his.openLink'))}">${svg('link')}</button>` : ''}
          <button class="icon-btn fail-btn ${p.failed ? 'on' : ''}" data-pfail="${p.id}"
                  title="${esc(t('his.markFailed'))}">${svg('bang')}</button>
          <button class="icon-btn" data-pedit="${p.id}" title="${esc(t('inv.edit'))}">${svg('pencil')}</button>
          <button class="icon-btn" data-pdel="${p.id}" title="${esc(t('btn.delete'))}">${svg('trash')}</button>
        </div>
      </td>
    </tr>`).join('');

  const em = $('#historyEmpty');
  em.hidden = list.length > 0;
  $('#historyTable').hidden = list.length === 0;
  em.innerHTML = S.prints.length
    ? `<b>${esc(t('his.noResults'))}</b>${esc(t('his.noResultsSub'))}`
    : `<b>${esc(t('his.empty'))}</b>${esc(t('his.emptySub'))}`;

  $$('#historyTable td.cost').forEach((el) => { el.hidden = !showCost; });

  const all = $('#hisPickAll');
  const on = list.filter((p) => S.picked.has(p.id)).length;
  all.checked = on > 0 && on === list.length;
  all.indeterminate = on > 0 && on < list.length;
  all.title = t('his.pickAll');
  all.onclick = () => {
    // the heading picks what is on screen, never what a filter is hiding
    list.forEach((p) => (all.checked ? S.picked.add(p.id) : S.picked.delete(p.id)));
    renderHistory();
  };

  $$('#historyTable [data-pick]').forEach((c) => {
    c.onclick = (e) => {
      e.stopPropagation();
      const id = Number(c.dataset.pick);
      // shift takes everything between this row and the last one ticked, which
      // is what every list of things has done for thirty years
      if (e.shiftKey && S.lastPick != null) {
        const ids = list.map((p) => p.id);
        const a = ids.indexOf(S.lastPick);
        const b = ids.indexOf(id);
        if (a > -1 && b > -1) {
          ids.slice(Math.min(a, b), Math.max(a, b) + 1)
            .forEach((x) => (c.checked ? S.picked.add(x) : S.picked.delete(x)));
        }
      } else if (c.checked) S.picked.add(id);
      else S.picked.delete(id);
      S.lastPick = id;
      renderHistory();
    };
  });

  $$('#historyTable [data-gid]').forEach((c) => {
    c.onclick = (e) => {
      e.stopPropagation();
      S.his.group = c.dataset.gid;
      $('#hisGroup').value = c.dataset.gid;
      renderHistory();
    };
  });

  // the checkbox, the group chip and the row's own buttons all stop the click
  // before it gets there; anything else on a row means "let me read this one"
  wirePrintRows($('#historyTable'));

  const find = (id) => S.prints.find((p) => p.id == id);
  $$('[data-pedit]').forEach((b) => { b.onclick = () => openPrint(find(b.dataset.pedit)); });
  $$('[data-pfail]').forEach((b) => { b.onclick = () => openFail(find(b.dataset.pfail)); });
  $$('[data-plink]').forEach((b) => { b.onclick = () => call('open_url', find(b.dataset.plink).url); });
  $$('[data-pdel]').forEach((b) => {
    b.onclick = () => {
      const p = find(b.dataset.pdel);
      confirmDialog(t('confirm.delPrint'),
        t('confirm.delPrintText', { project: p.project, date: fdate(p.date) }),
        async () => {
          await call('delete_print', p.id);
          await reload();
          toast(t('toast.printDeleted'));
        });
    };
  });
}

/* ---------- MODAL: outcome (flag as failed without reopening the full form) ---------- */
function openFail(p) {
  S.failTarget = p.id;
  $('#failIntro').textContent = t('fail.intro', {
    project: p.project, date: fdate(p.date), g: g(p.total),
  });
  $('#failToggle').checked = !!p.failed;
  $('#failNotes').value = p.notes || '';

  // A print that stops halfway does not use what was planned: this corrects what
  // actually came out, and those grams replace the recorded ones.
  $('#failItems').innerHTML = p.items.map((i) => `
    <div class="fail-row" data-fid="${i.filament_id}">
      <span class="fail-name"><i style="background:${esc(i.hex)}"></i>${esc(i.name)}</span>
      <input type="number" step="0.01" min="0" value="${i.grams}">
    </div>`).join('');
  $$('#failItems input').forEach((el) => { el.oninput = failTotal; });
  failTotal();

  show('#failModal');
  setTimeout(() => $('#failNotes').focus(), 60);
}

function failTotal() {
  const total = $$('#failItems .fail-row')
    .reduce((a, r) => a + (parseFloat(r.querySelector('input').value) || 0), 0);
  $('#failTotal').textContent = g(total) + ' g';
}

async function saveFail() {
  const p = S.prints.find((x) => x.id === S.failTarget);
  if (!p) return;
  const items = $$('#failItems .fail-row').map((r) => ({
    filament_id: r.dataset.fid,
    grams: parseFloat(r.querySelector('input').value) || 0,
  })).filter((i) => i.grams > 0);
  if (!items.length) return toast(t('toast.needItems'), 'error');

  const isFailed = $('#failToggle').checked;
  const res = await call('save_print', {
    id: p.id, date: p.date, project: p.project, url: p.url,
    notes: $('#failNotes').value.trim(), failed: isFailed ? 1 : 0, items,
  });
  if (failed(res)) return;
  hide('#failModal');
  await reload();
  toast(isFailed ? t('fail.saved') : t('fail.cleared'));
}

/* ---------- AMS ----------
   The printer cannot be asked what is loaded, so this is kept by hand. It earns
   that by answering the question you have while standing in front of the
   machine: which spool is in slot 3, and how much is left on it. */
const amsName = (s) => (s.external ? t('ams.external')
  : `${String.fromCharCode(64 + s.unit)}${s.slot}`);

async function renderAms() {
  $('#amsUnits').value = S.settings.ams_units ?? '1';
  const list = await call('ams');
  S.ams = failed(list) ? [] : (list || []);

  $('#amsSlots').innerHTML = S.ams.map((s, i) => {
    const f = s.filament;
    return `<div class="ams-slot${f ? '' : ' is-empty'}${s.external ? ' is-ext' : ''}"
                 data-ams="${i}" role="button" tabindex="0">
      <div class="ams-head">
        <span class="ams-id">${esc(amsName(s))}</span>
        ${f ? `<span class="tag">${esc(f.material)}</span>` : ''}
      </div>
      ${f ? `
      <div class="ams-body">
        <span class="swatch" style="background:${esc(f.hex)}"></span>
        <span class="ams-what">
          <b>${esc(f.name)}</b>
          <small>${f.sealed ? esc(t('inv.sealed')) : `${g(f.remaining)} g · ${f.pct.toFixed(0)} %`}</small>
        </span>
      </div>
      <div class="bar"><i style="width:${Math.min(100, f.pct)}%;background:${statusColor(f)}"></i></div>`
      : `<div class="ams-body"><span class="ams-free">${svg('plus')}${esc(t('ams.empty'))}</span></div>`}
    </div>`;
  }).join('');

  $$('#amsSlots [data-ams]').forEach((n) => {
    const open = () => openAmsPick(S.ams[+n.dataset.ams]);
    n.onclick = open;
    n.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  });
}

/* A spool can only be in one place, so the list says where each one already is
   and loading it somewhere else takes it out of there. */
function openAmsPick(slot) {
  S.amsTarget = slot;
  const here = slot.filament ? slot.filament.id : null;
  const whereIs = {};
  S.ams.forEach((x) => { if (x.filament) whereIs[x.filament.id] = amsName(x); });

  $('#amsTitle').textContent = t('ams.pick', { slot: amsName(slot) });
  $('#amsClear').hidden = !here;
  $('#amsPick').innerHTML = S.filaments
    .filter((f) => !f.archived)
    .map((f) => `
      <button class="ams-opt${f.id === here ? ' here' : ''}" data-fil="${f.id}">
        <span class="swatch" style="background:${esc(f.hex)}"></span>
        <b>${esc(f.name)}</b>
        <small>${f.sealed ? esc(t('inv.sealed')) : `${g(f.remaining)} g`}${
          whereIs[f.id] && f.id !== here ? ` · ${esc(t('ams.elsewhere', { slot: whereIs[f.id] }))}` : ''}</small>
      </button>`).join('');

  $$('#amsPick [data-fil]').forEach((b) => {
    b.onclick = () => setAmsSlot(b.dataset.fil);
  });
  show('#amsModal');
}

async function setAmsSlot(filamentId) {
  const s = S.amsTarget;
  const r = await call('set_ams_slot', {
    unit: s.unit, slot: s.slot, filament_id: filamentId || null });
  if (failed(r)) return;
  hide('#amsModal');
  await renderAms();
  toast(t(filamentId ? 'toast.amsSet' : 'toast.amsCleared'));
}

/* ---------- STATISTICS ---------- */
/* The months are stacked in the colours of the filaments that made them.
   Nothing invented and nothing decorative: it is the same palette sitting in
   the drawer, and it turns a plain bar chart into a picture of what was
   printed. A black filament on a dark ground would be a hole in the bar, so
   every band carries a hairline. */
/* `money` draws the same shape in currency: the field is still called grams
   because it is still the magnitude of the bar, and here that magnitude is
   what the month cost. */
function columns(data, opts = {}) {
  if (!data || !data.length) return `<div class="empty">${esc(t('stats.noData'))}</div>`;
  const show = opts.money ? money : (v) => `${g(v)} g`;
  const max = Math.max(...data.map((d) => d.grams), 1);
  return `<div class="columns">${data.map((d) => {
    const split = (d.split || []).length ? d.split : [{ hex: '', name: '', grams: d.grams }];
    return `<div class="col" title="${esc(show(d.grams))} · ${esc(t('stats.prints', { n: d.prints }))}">
      <span class="cv">${esc(show(d.grams))}</span>
      <span class="stack"><span class="fill" style="height:${Math.max(3, (d.grams / max) * 100)}%">
        ${split.map((p) => `<i style="height:${(p.grams / d.grams) * 100}%;background:${
          esc(p.hex || 'var(--muted-2)')}" title="${esc(p.name)} · ${esc(show(p.grams))}"></i>`).join('')}
      </span></span>
      <span class="cl">${fmonth(d.month)}</span>
    </div>`;
  }).join('')}</div>`;
}

/* A project leads to the history filtered to it -- by group when it is one,
   which is exact, instead of by a name that could also be a print's own. */
function projectRow(p) {
  return {
    label: p.project, value: p.grams, split: p.split,
    // what it weighed is on the bar; what it cost belongs next to how many
    // prints it took, and only once something has a price
    sub: t('stats.prints', { n: p.prints })
      + (S.stats.has_prices && p.cost ? ` · ${money(p.cost)}` : ''),
    // the sheet, not the history: the history is a button away on it, and a
    // list of rows is a poor answer to "what was this project"
    action: () => openProjectInfo(p),
  };
}

function openAllProjects() {
  const rows = (S.stats.top_projects || []).map(projectRow);
  $('#allProjectsCount').textContent = t('stats.allProjects', { n: rows.length });
  $('#allProjectsList').innerHTML = bars(rows);
  wireBars($('#allProjectsList'), rows);
  show('#projectsModal');
}

/* Every bar is made of the filaments that made it, so none of them needs an
   invented colour: a material or a project is drawn from the same palette that
   is sitting in the drawer. And every row leads somewhere, because the obvious
   next question about a figure is "which ones?". */
function bars(rows, opts = {}) {
  if (!rows.length) return `<div class="empty">${esc(t('stats.noData'))}</div>`;
  const max = Math.max(...rows.map((r) => r.value), 1);
  const total = rows.reduce((a, r) => a + r.value, 0) || 1;

  const html = `<div class="bars">${rows.map((r, i) => {
    const split = (r.split && r.split.length) ? r.split
      : [{ hex: r.hex || '', grams: r.value, name: r.label }];
    return `<div class="brow${r.action ? ' go' : ''}"${r.action ? ` data-b="${i}" role="button" tabindex="0"` : ''}>
      <span class="bl" title="${esc(r.label)}">
        ${r.hex ? `<i style="background:${esc(r.hex)}"></i>` : ''}
        <span class="bl-txt">${esc(r.label)}<small>${esc(r.sub || '')}</small></span>
      </span>
      <span class="btrack"><span class="bt" style="width:${(r.value / max) * 100}%">
        ${split.map((p) => `<i style="width:${(p.grams / r.value) * 100}%;background:${
          esc(p.hex || 'var(--muted-2)')}" title="${esc(p.name || '')}"></i>`).join('')}
      </span></span>
      <span class="bv">${opts.unit ? esc(opts.unit(r.value)) : `${g(r.value)} g`}${
        opts.share === false ? '' : `<small>${g((r.value / total) * 100)} %</small>`}</span>
    </div>`;
  }).join('')}</div>`;

  return html;
}

/* bars() only builds the markup; the rows are wired once they are in the DOM */
function wireBars(el, rows) {
  $$('[data-b]', el).forEach((n) => {
    const act = rows[+n.dataset.b].action;
    n.onclick = act;
    n.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } };
  });
}

function renderStats() {
  const st = S.stats;
  const days = st.first_date
    ? Math.max(1, Math.round((new Date(st.last_date) - new Date(st.first_date)) / 864e5) + 1) : 1;
  const pct = st.total_grams ? (st.failed_grams / st.total_grams) * 100 : 0;

  renderKpis($('#statKpis'), [
    { label: t('kpi.printed'), value: kg(st.total_grams), icon: 'scale',
      foot: t('kpi.printedFoot', { d: fdate(st.first_date) }), hint: t('kpi.hint.history'),
      action: () => gotoHistory() },
    { label: t('kpi.prints'), value: String(st.total_prints || 0), icon: 'printer', tone: 'ok',
      foot: t('kpi.printsFoot', { n: g(st.total_prints / days * 7) }), hint: t('kpi.hint.history'),
      action: () => gotoHistory() },
    { label: t('kpi.wasted'), value: kg(st.failed_grams || 0), icon: 'trash',
      tone: st.failed_grams ? 'warn' : 'ok',
      foot: `${t('kpi.wastedFoot', { n: st.failed_prints || 0 })} · ${t('kpi.wastedPct', { p: g(pct) })}`,
      hint: t('kpi.hint.wasted'),
      action: () => gotoHistory({ failedOnly: true }) },
    ...(st.has_prices ? [{
      label: t('kpi.spent'), value: money(st.total_cost), icon: 'coin',
      foot: t('kpi.spentFoot', { v: money(st.month_cost) }), hint: t('kpi.hint.spent'),
      action: () => gotoHistory(),
    }] : []),
    ...(st.has_prices && st.stock_value ? [{
      label: t('kpi.stock'), value: money(st.stock_value), icon: 'boxes',
      foot: t('kpi.stockFoot', { kg: kg(st.available_g || 0) }),
      hint: t('kpi.hint.inventory'), action: () => gotoInventory(),
    }] : []),
    { label: t('kpi.filaments'), value: String(st.n_filaments || 0), icon: 'palette',
      tone: st.n_low ? 'warn' : 'ok', foot: t('kpi.filamentsFoot', { n: st.n_low || 0 }),
      hint: st.n_low ? t('kpi.hint.low') : t('kpi.hint.inventory'),
      action: () => gotoInventory(st.n_low ? { lowOnly: true, sort: 'pct' } : {}) },
  ]);

  $('#chartMonths').innerHTML = columns(st.by_month || []);
  // the same months in money, and only where there is money to show
  $('#cardSpend').hidden = !st.has_prices;
  if (st.has_prices) $('#chartSpend').innerHTML = columns(st.by_spend || [], { money: true });

  // a filament leads to its own sheet, which is where its whole story is
  const fil = (st.by_filament || []).slice(0, 12).map((f) => ({
    label: f.name, value: f.grams, hex: f.hex,
    sub: t('stats.prints', { n: f.prints }),
    action: () => { const x = S.filaments.find((y) => y.name === f.name); if (x) openDetail(x); },
  }));
  $('#chartFilaments').innerHTML = bars(fil);
  wireBars($('#chartFilaments'), fil);

  // a material leads to the inventory showing only that material
  const mat = (st.by_material || []).map((m) => ({
    label: m.material, value: m.grams, split: m.split,
    sub: t('stats.prints', { n: m.prints }),
    action: () => gotoInventory({ material: m.material }),
  }));
  $('#chartMaterials').innerHTML = bars(mat);
  wireBars($('#chartMaterials'), mat);

  const all = (st.top_projects || []).map(projectRow);
  const proj = all.slice(0, 8);
  $('#chartProjects').innerHTML = bars(proj);
  wireBars($('#chartProjects'), proj);
  // the card is the top of the list; the rest is a click away rather than a
  // scrollbar inside a card
  $('#allProjects').hidden = all.length <= proj.length;

  // Which model keeps failing is the one question about wasted material that
  // can be acted on -- the total only tells you it happened.
  const fails = (st.worst_failures || []).map((f) => ({
    label: f.project, value: f.grams, split: f.split,
    sub: t('stats.failedN', { n: f.n }),
    action: () => gotoHistory({ failedOnly: true, search: f.project }),
  }));
  $('#chartFails').innerHTML = bars(fails);
  wireBars($('#chartFails'), fails);

  // Day names from the system rather than from the translations: it already
  // knows them in every language, and 2024-01-07 was a Sunday, which is where
  // SQLite's %w starts counting.
  const dayName = new Intl.DateTimeFormat(locale(), { weekday: 'long' });
  const week = (st.by_weekday || []).map((d, i) => ({
    label: dayName.format(new Date(2024, 0, 7 + i)),
    value: d.grams, split: d.split,
  }));
  $('#chartWeekday').innerHTML = bars(week);

  // What runs out soonest first, which is the order you care about it in.
  const life = (st.roll_life || []).map((r) => ({
    label: r.material, value: r.days, split: r.split,
    sub: t('stats.lifeSub', { n: r.rolls, rate: g(r.rate) }),
    action: () => gotoInventory({ material: r.material }),
  }));
  $('#cardLife').hidden = !life.length;
  $('#chartLife').innerHTML = bars(life, {
    // a share of days adds up to nothing worth printing
    share: false, unit: (v) => t('stats.days', { n: Math.round(v) }),
  });
  wireBars($('#chartLife'), life);
}

/* ---------- SETTINGS ---------- */
function renderSettings() {
  $('#setLang').innerHTML = Object.entries(LANGS)
    .map(([k, v]) => `<option value="${k}">${esc(v.name)}</option>`).join('');
  $('#setLang').value = S.lang;
  const cur = S.settings.currency || 'EUR';
  const names = (() => {
    try { return new Intl.DisplayNames([locale()], { type: 'currency' }); } catch (e) { return null; }
  })();
  $('#setCurrency').innerHTML = CURRENCIES.map((c) => {
    const label = names ? `${c} · ${names.of(c)}` : c;
    return `<option value="${c}"${c === cur ? ' selected' : ''}>${esc(label)}</option>`;
  }).join('');
  $('#setTheme').value = S.settings.theme || 'dark';
  $('#setTempUnit').value = S.settings.temp_unit || 'C';
  $('#setSlicerWatch').checked = S.settings.slicer_watch !== '0';
  $('#setSlicerDir').value = S.settings.slicer_dir || '';
  renderSlicerFolder();
  renderLearned();
  $('#setLow').value = S.settings.low_threshold_pct ?? 15;
  $('#setSpool').value = S.settings.default_spool_g ?? 1000;
  $('#dbPath').textContent = S.dbPath || '—';

  // materials actually in use first; the rest stays collapsed
  const used = [...new Set(S.filaments.map((f) => f.material))].sort();
  const others = Object.keys(S.dryDays).filter((m) => !used.includes(m)).sort();
  // A material with no entry of its own is not on 45 days: it inherits its
  // family, and the filament already carries the limit actually being applied.
  // Showing 45 here would contradict what the inventory is doing.
  const limitOf = (m) => S.dryDays[m]
    ?? (S.filaments.find((f) => f.material === m) || {}).dry_limit ?? 45;
  const row = (m) => `<label class="field"><span>${esc(m)}</span>
      <input type="number" min="1" max="3650" step="1" data-mat="${esc(m)}"
             value="${limitOf(m)}"></label>`;
  $('#dryGridUsed').innerHTML = used.map(row).join('');
  $('#dryGridOther').innerHTML = others.map(row).join('');

  // tares: brands in use first, the rest of the table behind them.
  // 'Bambu Lab' and 'bambulab' are the same brand, so they compare normalised.
  const norm = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const mine = [...new Map(S.filaments.flatMap(
    (f) => [f.roll_brand, ...(f.spares || []).map((sp) => sp.brand)])
    .filter(Boolean).map((b) => [norm(b), b])).values()];
  const seen = new Set(mine.map(norm));
  const known = Object.keys(S.spoolTare).filter((b) => !seen.has(norm(b))).sort();
  const tareRow = (b) => `
    <div class="field tare-row"><span>${esc(b)}</span>
      <div class="tare-pair">
        <label><i>${esc(t('set.tarePlastic'))}</i>
          <input type="number" min="1" max="2000" step="1"
                 data-tare="${esc(b)}" data-kind="plastic" value="${tareFor(b, 'plastic')}"></label>
        <label><i>${esc(t('set.tareCardboard'))}</i>
          <input type="number" min="1" max="2000" step="1"
                 data-tare="${esc(b)}" data-kind="cardboard" value="${tareFor(b, 'cardboard')}"></label>
      </div>
    </div>`;
  $('#tareGrid').innerHTML = [...mine, ...known].map(tareRow).join('');

  $('#backupDesc').textContent = t('set.backupsDesc', {
    n: S.backups.count || 0, d: S.backups.last || '—' });
}

/* ---------- what Bambu Studio just sliced ----------
   Slicing is the moment the grams are known, so that is when the print is
   offered. Nothing is ever recorded from here: the card opens the normal form
   filled in, and the user confirms or corrects it. */

async function checkSlices() {
  if (S.settings.slicer_watch === '0') return;
  const list = await call('slices', { limit: 1 });
  if (failed(list) || !list || !list.length) return;
  const sl = list[0];
  // a card already on screen for the same slice must not restart its animation
  if (S.slice && S.slice.path === sl.path) return;
  // and one put off must stay put off, or the next check brings it straight back
  if (S.snoozed.has(sl.path)) return;
  S.slice = sl;
  showSliceCard(sl);
}

function showSliceCard(sl) {
  $('#sliceWhen').textContent = sliceWhen(sl);
  $('#sliceProject').textContent = sl.project || t('slice.untitled');
  $('#sliceChips').innerHTML = sl.items.map((i) => `
    <span class="slice-chip">
      <span class="dot" style="background:${esc(i.hex || '#888')}"></span>
      ${g(i.grams)} g · ${esc(i.material || '?')}
    </span>`).join('');
  show('#sliceCard');
}

/* "Not now" puts this slice off for the rest of the session: it is still
   pending, so it is offered again next launch, but it does not come back in
   forty-five seconds. The × says it is dealt with for good and moves the
   watermark past it. */
function hideSliceCard(forget) {
  hide('#sliceCard');
  if (S.slice) {
    if (forget) call('dismiss_slice', { path: S.slice.path, stamp: S.slice.stamp });
    else S.snoozed.add(S.slice.path);
  }
  S.slice = null;
}

/* Everything still in the slicer cache, newest first. The card only ever
   offers the newest plate and only once; this is how you get back to one you
   put aside, or one sliced while the app was closed. */
async function openSliceList() {
  const box = $('#slicesList');
  box.innerHTML = '';
  show('#slicesModal');

  const list = await call('slices', { all: true, limit: 12 });
  if (failed(list) || !list || !list.length) {
    box.innerHTML = `<div class="empty"><b>${esc(t('slices.empty'))}</b>${esc(t('slices.emptyHint'))}</div>`;
    return;
  }
  box.innerHTML = list.map((sl, i) => `
    <button class="slice-row" data-slice="${i}">
      <span class="slice-when">${esc(sliceWhen(sl))}</span>
      <span class="slice-what">
        <b>${esc(sl.project || t('slice.untitled'))}</b>${
          sl.logged_at ? `<span class="tag">${esc(t('slices.logged'))}</span>` : ''}
        <span class="slice-chips">${sl.items.map((it) => `
          <span class="slice-chip">
            <span class="dot" style="background:${esc(it.hex || '#888')}"></span>
            ${g(it.grams)} g · ${esc(it.material || '?')}
          </span>`).join('')}</span>
      </span>
      <span class="slice-grams">${g(sl.total)} g</span>
    </button>`).join('');

  $$('[data-slice]', box).forEach((b) => {
    b.onclick = () => { hide('#slicesModal'); openPrintFromSlice(list[b.dataset.slice]); };
  });
}

/* "just now" while it is fresh, a date once it is not. */
function sliceWhen(sl) {
  const when = new Date(sl.sliced_at);
  const mins = Math.max(0, Math.round((Date.now() - when.getTime()) / 60000));
  if (mins < 1) return t('slice.justNow');
  if (mins < 60) return t('slice.minsAgo', { n: mins });
  return when.toLocaleString(locale(), { dateStyle: 'short', timeStyle: 'short' });
}

/* Groups are made by naming one, not by creating an empty one first and
   filling it later: the name is the only thing a group has. */
function groupThese(list) {
  if (!list.length) return;
  S.grouping = list;
  // if they are already all in the same group, the field starts on its name, so
  // this doubles as the way to rename one or to add a print to it
  const current = [...new Set(list.map((p) => p.group_name).filter(Boolean))];
  $('#gCount').textContent = t('group.ask', { n: list.length });
  $('#gName').value = current.length === 1 ? current[0] : '';
  show('#groupModal');
  $('#gName').focus();
  $('#gName').select();
}

async function saveGroup() {
  const list = S.grouping || [];
  const name = $('#gName').value.trim();
  const r = await call('set_group', { ids: list.map((p) => p.id), name });
  if (failed(r)) return;
  hide('#groupModal');
  // the picking was for this; keeping it would leave rows ticked for a job
  // already done
  S.picked.clear();
  S.lastPick = null;
  await reload();
  toast(name ? t('toast.grouped', { n: list.length, name })
             : t('toast.ungrouped', { n: list.length }));
}

/* Weighing corrects the number whatever the cause, so it is worth a question
   first. A spool that overshot by a few grams held a few grams more than the
   label said; one that overshot by seventy-five was probably swapped without
   being recorded, and weighing that one welds two spools into a single roll
   and leaves the correction standing for good. */
function openMismatch(f) {
  S.mismatchTarget = f;
  $('#mmWhat').textContent = t('mm.what', { name: f.name, n: g(f.over) });
  show('#mismatchModal');
}

/* A project is a name several prints share; a group is that name made
   deliberate. One sheet does for both, because from the outside they are the
   same question: what went into this, and what did it cost.

   It takes a row from the statistics rather than working the totals out again
   -- the grams, the cost and the colours are already agreed there, and two
   places computing the same figure is two places to disagree. */
function openProjectInfo(p) {
  if (!p) return;
  S.infoProject = p;
  const mine = S.prints.filter((x) => (p.group_id
    ? x.group_id == p.group_id
    : !x.group_id && x.project === p.project));
  const dates = mine.map((x) => x.date).sort();
  const spec = (label, value) =>
    `<span class="spec"><i>${esc(label)}</i><b>${esc(value)}</b></span>`;

  $('#projTitle').textContent = p.project;
  $('#projBody').innerHTML = `
    <div class="pinfo-tags">
      ${dates.length ? `<span class="muted">${esc(dates.length > 1
        ? t('proj.between', { from: fdate(dates[0]), to: fdate(dates[dates.length - 1]) })
        : fdate(dates[0]))}</span>` : ''}
      ${p.group_id ? `<span class="gchip">${esc(t('print.group'))}</span>` : ''}
    </div>
    <div class="pinfo-specs">
      ${spec(t('his.total'), `${g(p.grams)} g`)}
      ${S.stats.has_prices && p.cost ? spec(t('his.cost'), money(p.cost)) : ''}
      ${spec(t('kpi.prints'), String(p.prints))}
    </div>
    <h3 class="sub-head">${esc(t('print.items'))}</h3>
    <div class="fchips proj-colours">${(p.split || []).map(chip).join('')}</div>
    <h3 class="sub-head">${esc(t('detail.prints'))}</h3>
    ${mine.length ? `<div class="det-prints"><table class="table">${mine.map((x) => `
      <tr data-pinfo="${x.id}">
        <td class="date" style="width:104px">${fdate(x.date)}</td>
        <td class="proj">${esc(x.project)}${failTag(x)}</td>
        <td class="total right" style="width:78px">${g(x.total)} g</td>
      </tr>`).join('')}</table></div>`
      : `<div class="spares-empty">${esc(t('detail.noPrints'))}</div>`}`;
  wirePrintRows($('#projBody'));
  show('#projModal');
}

/* Reading a print is not editing one. The history row is a summary -- date,
   name, colours, total -- and the rest of what was recorded has until now been
   reachable only by opening the form, which is a strange place to be put when
   all you did was ask what something was. */
function openPrintInfo(p) {
  if (!p) return;
  S.infoPrint = p;
  $('#pinfoTitle').textContent = p.project;
  const spec = (label, value) =>
    `<span class="spec"><i>${esc(label)}</i><b>${esc(value)}</b></span>`;
  $('#pinfoBody').innerHTML = `
    <div class="pinfo-tags">
      <span class="muted">${esc(fdate(p.date))}</span>
      ${p.group_name ? `<button class="gchip pinfo-group" id="pinfoGroup">${
        esc(p.group_name)}</button>` : ''}
      ${failTag(p)}
    </div>
    <h3 class="sub-head">${esc(t('print.items'))}</h3>
    <div class="fchips">${p.items.map(chip).join('')}</div>
    <div class="pinfo-specs">
      ${spec(t('his.total'), `${g(p.total)} g`)}
      ${p.cost ? spec(t('his.cost'), money(p.cost)) : ''}
    </div>
    ${p.notes ? `<div class="pinfo-note">${esc(p.notes)}</div>` : ''}
    ${p.url ? `<a class="pinfo-link" href="#" id="pinfoLink">${svg('link')}${
      esc(t('his.openLink'))}</a>` : ''}`;
  const grp = $('#pinfoGroup');
  if (grp) {
    grp.onclick = () => openProjectInfo(
      (S.stats.top_projects || []).find((x) => x.group_id === p.group_id));
  }
  const link = $('#pinfoLink');
  if (link) link.onclick = (e) => { e.preventDefault(); call('open_url', p.url); };
  show('#pinfoModal');
}

/* ---------- MODAL: print ---------- */
function openPrint(p) {
  S.editingPrint = p ? p.id : null;
  $('#printModalTitle').textContent = p ? t('print.edit') : t('print.new');
  $('#pDate').value = p ? p.date : todayISO();
  $('#pProject').value = p ? p.project : '';
  $('#pGroup').value = p ? (p.group_name || '') : '';
  $('#pUrl').value = p ? (p.url || '') : '';
  $('#pNotes').value = p ? p.notes : '';
  $('#pFailed').checked = p ? !!p.failed : false;
  $('#pItems').innerHTML = '';
  if (p && p.items.length) p.items.forEach((i) => addItemRow(i.filament_id, i.grams));
  else addItemRow();
  show('#printModal');
  setTimeout(() => $('#pProject').focus(), 60);
}

/* The form as the slicer would fill it in: one row per filament, each with the
   spool the app believes it was and the option list behind it. */
function openPrintFromSlice(sl) {
  openPrint(null);
  $('#printModalTitle').textContent = t('print.fromSlice');
  $('#pProject').value = sl.project || '';
  $('#pItems').innerHTML = '';
  $('#pGroup').value = '';
  sl.items.forEach((i) => addItemRow(i.pick || '', i.grams, i));
  printTotal();
  hide('#sliceCard');
  setTimeout(() => {
    const unsure = $('#pItems .item-row.guess select');
    (unsure || $('#pProject')).focus();
  }, 60);
}

function addItemRow(fid = '', grams = '', slice = null) {
  const opts = S.filaments.filter((f) => !f.archived || f.id == fid)
    .map((f) => `<option value="${f.id}" ${f.id == fid ? 'selected' : ''}>${esc(f.name)} — ${g(f.remaining)} g</option>`)
    .join('');
  const row = document.createElement('div');
  row.className = 'item-row';
  // a suggestion the app is not sure about is marked as such rather than
  // dressed up as a decision
  if (slice && !slice.confident) row.classList.add('guess');
  if (slice) row.dataset.sig = slice.signature || '';
  row.innerHTML = `
    <select>${fid ? '' : `<option value="">${esc(t('print.pickFilament'))}</option>`}${opts}</select>
    <input type="number" step="0.01" min="0" placeholder="${esc(t('print.grams'))}" value="${grams === '' ? '' : grams}">
    <button class="icon-btn" title="${esc(t('print.remove'))}">${svg('close')}</button>
    ${slice ? `<small class="item-note">${sliceNote(slice)}</small>` : ''}`;
  row.querySelector('button').onclick = () => {
    row.remove();
    if (!$('#pItems').children.length) addItemRow();
    printTotal();
  };
  row.querySelector('input').oninput = printTotal;
  // changing the spool by hand is the correction the app learns from
  if (slice) row.querySelector('select').onchange = () => row.classList.remove('guess');
  $('#pItems').appendChild(row);
  printTotal();
}

/* Says where the suggestion came from, so an odd one is easy to spot. */
function sliceNote(i) {
  // the profile already names the material ("Bambu PLA Matte"), so saying both
  // would just read as "PLA · Generic PLA"
  const what = (i.profile ? i.profile.replace(/\s*@.*$/, '') : '') || i.material || '?';
  // when the AMS is why this spool was picked, say so: the colour on screen
  // will often disagree with it, and that is the one thing worth explaining
  if (i.from_slot) {
    const why = t('slice.fromSlot', { n: i.from_slot, what: esc(what) });
    return i.confident ? why : `<b>${esc(t('slice.check'))}</b> ${why}`;
  }
  return i.confident
    ? t('slice.sure', { what: esc(what) })
    : `<b>${esc(t('slice.check'))}</b> ${t('slice.unsure', { what: esc(what) })}`;
}

function printTotal() {
  const total = $$('#pItems .item-row')
    .reduce((a, r) => a + (parseFloat(r.querySelector('input').value) || 0), 0);
  $('#pTotal').textContent = g(total) + ' g';
}

async function savePrint() {
  const items = $$('#pItems .item-row').map((r) => ({
    filament_id: r.querySelector('select').value,
    grams: parseFloat(r.querySelector('input').value) || 0,
  })).filter((i) => i.filament_id && i.grams > 0);

  if (!$('#pProject').value.trim()) return toast(t('toast.needProject'), 'error');
  if (!items.length) return toast(t('toast.needItems'), 'error');

  const res = await call('save_print', {
    id: S.editingPrint, date: $('#pDate').value || todayISO(),
    project: $('#pProject').value.trim(), url: $('#pUrl').value.trim(),
    group: $('#pGroup').value.trim(),
    notes: $('#pNotes').value.trim(), failed: $('#pFailed').checked ? 1 : 0, items,
  });
  if (failed(res)) return;

  // The confirmations just given are what make the next identical slice a
  // certainty instead of a guess.
  const matches = $$('#pItems .item-row')
    .filter((r) => r.dataset.sig && r.querySelector('select').value)
    .map((r) => ({ signature: r.dataset.sig, filament_id: r.querySelector('select').value }));
  if (matches.length) await call('remember_matches', { matches });
  if (S.slice) {
    call('dismiss_slice', { path: S.slice.path, stamp: S.slice.stamp });
    if (S.slice.fingerprint) call('slice_logged', { fingerprint: S.slice.fingerprint });
    S.slice = null;
  }

  hide('#printModal');
  await reload();
  toast(S.editingPrint ? t('toast.printUpdated') : t('toast.printSaved'));
}

/* A sealed spool has no opening date, so the field goes rather than sitting
   there with today's date in it -- which is what made the app look like it was
   insisting the spool had been opened. */
function sealedToggled() {
  const on = $('#fSealed').checked;
  $('#fOpenedField').hidden = on;
  // Creating: there is no spool anywhere yet, so one has to be put in stock.
  // Editing: the fitted roll IS the spool and becomes the spare itself, so
  // adding one here would turn one spool into two.
  if (on && !S.editingFilament && Number($('#fStock').value) < 1) $('#fStock').value = 1;
}

/* ---------- MODAL: filament ---------- */
function openFilament(f) {
  S.editingFilament = f ? f.id : null;
  $('#filModalTitle').textContent = f ? t('fil.edit') : t('fil.new');
  $('#fMaterial').value = f ? f.material : 'PLA';
  $('#fColor').value = f ? f.color : '';
  $('#fName').value = f ? f.name : '';
  setBrand('#fBrand', '#fBrandOther', f ? (f.roll_brand || '') : '');
  $('#fType').innerHTML = typeOptions(f ? f.roll_type : 'plastic');
  $('#fStock').value = f ? f.stock : 0;
  $('#fPrice').value = f && f.price ? f.price : '';
  $('#fWeight').value = f ? f.roll_weight : (S.settings.default_spool_g || 1000);
  $('#fOpened').value = f ? (f.roll_opened || todayISO()) : todayISO();
  // Offered when creating, and when correcting a filament recorded as open
  // before it ever was -- which is only safe while nothing has been printed
  // from the roll, because after that the roll is the window those grams are
  // counted in.
  $('#fSealedRow').hidden = !!f && !f.can_seal;
  $('#fSealedRow').querySelector('.hint').textContent =
    t(f ? 'fil.sealedHintEdit' : 'fil.sealedHint');
  $('#fSealed').checked = false;
  sealedToggled();
  $('#fNotes').value = f ? f.notes : '';
  $('#fArchived').checked = f ? !!f.archived : false;
  setHex(f ? f.hex : '#8a8f96');
  loadCatalog(f ? f.hex : '');
  $('#fDelete').hidden = !f;
  show('#filModal');
  setTimeout(() => $(f ? '#fColor' : '#fMaterial').focus(), 60);
}

function setHex(v) { $('#fHex').value = v; $('#fHexTxt').value = v; }

/* The manufacturer's own colour list, loaded whenever brand or material changes.
   Picking one writes the exact hex the maker publishes, which is what later lets
   a colour coming from somewhere else be matched against the inventory. */
async function loadCatalog(selected) {
  const sel = $('#fCatalog');
  const brand = readBrand('#fBrand', '#fBrandOther');
  const material = $('#fMaterial').value.trim();
  sel.innerHTML = `<option value="">${esc(t('fil.catalogPick'))}</option>`;
  sel.disabled = true;
  if (!brand) return;
  const list = await call('catalog_colors', { brand, material });
  if (failed(list) || !list || !list.length) {
    sel.innerHTML = `<option value="">${esc(t('fil.catalogNone'))}</option>`;
    return;
  }
  sel.innerHTML = `<option value="">${esc(t('fil.catalogPick'))}</option>` +
    list.map((c) => `<option value="${esc(c.hex)}"${
      c.hex.toLowerCase() === String(selected || '').toLowerCase() ? ' selected' : ''
    } data-name="${esc(c.name)}">${esc(c.name)} · ${esc(c.hex)}</option>`).join('');
  sel.disabled = false;
}

async function saveFilament() {
  const data = {
    id: S.editingFilament,
    material: $('#fMaterial').value.trim() || 'PLA',
    color: $('#fColor').value.trim(),
    name: $('#fName').value.trim(),
    hex: $('#fHexTxt').value.trim(),
    brand: readBrand('#fBrand', '#fBrandOther'),
    spool_type: $('#fType').value,
    stock: Number($('#fStock').value) || 0,
    price: Number($('#fPrice').value) || 0,
    notes: $('#fNotes').value.trim(),
    archived: $('#fArchived').checked ? 1 : 0,
    roll_weight: Number($('#fWeight').value) || 1000,
    roll_opened: $('#fOpened').value || todayISO(),
    sealed: $('#fSealed').checked && !$('#fSealedRow').hidden ? 1 : 0,
  };
  if (data.sealed && !S.editingFilament) data.stock = Math.max(1, data.stock);
  if (!data.name && !data.color) return toast(t('toast.needColor'), 'error');
  const res = await call('save_filament', data);
  if (failed(res)) return;
  hide('#filModal');
  await reload();
  toast(S.editingFilament ? t('toast.filUpdated')
    : (data.sealed ? t('toast.filSealed') : t('toast.filSaved')));
}

/* ---------- MODAL: roll ---------- */
// mode: 'new' | 'adjust' | 'dry'. Each action has its own button on the card, so
// the dialog opens straight into whichever was asked for.
function openRoll(f, mode = 'new') {
  S.rollTarget = f;
  $('#rollModalTitle').textContent = t('roll.title', { name: f.name });
  $('#rollBody').innerHTML = `
    <div class="info-box">${f.sealed
      ? t('roll.infoSealed', { stock: `<b>${f.stock}</b>` })
      : t('roll.info', {
          brand: f.roll_brand ? t('roll.infoBrand', { brand: `<b>${esc(f.roll_brand)}</b>` }) : '',
          date: `<b>${fdate(f.roll_opened)}</b>`,
          rem: `<b>${g(f.remaining)} g</b>`, total: `${g(f.roll_weight)} g`,
          stock: `<b>${f.stock}</b>`,
        })}</div>
    <div class="field"><span>${esc(t('roll.what'))}</span>
      <select id="rMode">
        <option value="new">${esc(t('roll.mode.new'))}</option>
        <option value="adjust">${esc(t('roll.mode.adjust'))}</option>
        <option value="dry">${esc(t('roll.mode.dry'))}</option>
      </select>
    </div>
    <div id="rNew">
      <div class="form-grid">
        <label class="field"><span>${esc(t('roll.weight'))}</span>
          <input type="number" id="rWeight" min="1" step="10" value="${f.roll_weight}"></label>
        <label class="field"><span>${esc(t('roll.opened'))}</span>
          <input type="date" id="rOpened" value="${todayISO()}"></label>
      </div>
      <label class="field"><span>${esc(t('roll.price'))} <i>${esc(t('common.optional'))}</i></span>
        <input type="number" id="rPrice" min="0" step="0.01" value="${f.price || ''}"></label>
      <div class="form-grid">
        <label class="field"><span>${esc(t('fil.brand'))}</span>
          <select id="rBrand" class="brand-sel">${brandOptions(f.roll_brand || '')}</select>
          <input type="text" id="rBrandOther" placeholder="${esc(t('brand.otherPh'))}" hidden>
        </label>
        <label class="field"><span>${esc(t('fil.spoolType'))}</span>
          <select id="rType">${typeOptions(f.roll_type)}</select>
        </label>
      </div>
      <small class="field-note">${esc(t('roll.brandHelp'))}</small>
      <label class="field"><span>${esc(t('roll.useSpare'))}</span>
        <select id="rSpare">
          <option value="">${esc(t('roll.noSpare'))}</option>
          ${(f.spares || []).map((s, i) => `<option value="${s.id}"${
            // Opening the first spool of a sealed filament takes it out of the
            // stock: otherwise two spools in the drawer become an open roll plus
            // two spares, which is one spool more than you own.
            f.sealed && i === 0 ? ' selected' : ''}>${
            esc(s.brand || t('roll.noBrand'))} · ${g(s.weight)} g</option>`).join('')}
        </select>
        <small>${esc(f.stock ? t('roll.spareHelp') : t('roll.spareNone'))}</small>
      </label>
      <div class="info-box">${esc(t('roll.resetInfo'))}</div>
    </div>
    <div id="rDry" hidden>
      <label class="field"><span>${esc(t('roll.dryDate'))}</span>
        <input type="date" id="rDried" value="${todayISO()}">
        <small>${esc(f.dried_at
          ? t('roll.dryLast', { d: fdate(f.dried_at), n: f.days_since_dry })
          : t('roll.dryNever'))} ${esc(t('roll.dryLimit', { n: f.dry_limit, mat: f.material }))}</small>
      </label>
    </div>
    <div id="rAdjust" hidden>
      <div class="form-grid">
        <label class="field"><span>${esc(t('roll.scale'))}</span>
          <input type="number" id="rScale" min="0" step="0.1" placeholder="0">
          <small>${esc(t('roll.scaleHelp'))}</small></label>
        <label class="field"><span>${esc(t('roll.tare'))}</span>
          <input type="number" id="rTare" min="0" step="1" value="${f.tare || f.tare_hint}">
          <small>${esc(t('roll.tareHelp'))}</small></label>
      </div>
      <label class="field mt"><span>${esc(t('roll.remaining'))}</span>
        <input type="number" id="rRemaining" min="0" step="0.1" value="${f.remaining}">
        <small>${esc(t('roll.remainingHelp'))}</small></label>
    </div>`;
  const applyMode = (v) => {
    $('#rNew').hidden = v !== 'new';
    $('#rAdjust').hidden = v !== 'adjust';
    $('#rDry').hidden = v !== 'dry';
  };
  $('#rMode').onchange = (e) => applyMode(e.target.value);
  $('#rMode').value = mode;
  applyMode(mode);
  // scale minus tare feeds the remaining-grams field, which is what gets saved
  const fromScale = () => {
    const total = parseFloat($('#rScale').value);
    if (!(total > 0)) return;
    const tare = parseFloat($('#rTare').value) || 0;
    $('#rRemaining').value = Math.max(0, +(total - tare).toFixed(2));
  };
  $('#rScale').oninput = fromScale;
  $('#rTare').oninput = fromScale;

  // picking a spare fills in its brand and weight (still editable)
  $('#rSpare').onchange = (e) => {
    const sp = (f.spares || []).find((s) => String(s.id) === e.target.value);
    if (!sp) return;
    setBrand('#rBrand', '#rBrandOther', sp.brand || '');
    $('#rType').value = sp.spool_type || 'plastic';
    $('#rWeight').value = sp.weight;
    if (sp.price) $('#rPrice').value = sp.price;
  };
  // the tare in the scale panel follows the chosen brand and type
  const syncTare = () => {
    $('#rTare').value = tareFor(readBrand('#rBrand', '#rBrandOther'), $('#rType').value);
  };
  wireBrand('#rBrand', '#rBrandOther', syncTare);
  $('#rType').onchange = syncTare;
  show('#rollModal');
}

async function saveRoll() {
  const f = S.rollTarget;
  const mode = $('#rMode').value;
  let r;
  if (mode === 'new') {
    r = await call('new_roll', {
      id: f.id, weight: Number($('#rWeight').value) || f.roll_weight,
      opened: $('#rOpened').value || todayISO(),
      brand: readBrand('#rBrand', '#rBrandOther'), spool_type: $('#rType').value,
      price: Number($('#rPrice').value) || 0,
      spare_id: $('#rSpare').value || null,
    });
    if (failed(r)) return;
    toast(t('toast.rollNew'));
  } else if (mode === 'dry') {
    r = await call('mark_dried', { id: f.id, when: $('#rDried').value || todayISO() });
    if (failed(r)) return;
    toast(t('toast.dried'));
  } else {
    r = await call('adjust_roll', {
      id: f.id, remaining: Number($('#rRemaining').value) || 0,
      tare: parseFloat($('#rScale').value) > 0 ? Number($('#rTare').value) || 0 : 0,
    });
    if (failed(r)) return;
    toast(t('toast.adjusted'));
  }
  hide('#rollModal');
  await reload();
}

/* The folder is found on its own, but the guess can be wrong -- a portable
   install, a redirected TEMP -- and there was no way to see which one it landed
   on, let alone correct it. This shows the path in use and what is in it. */
async function renderSlicerFolder() {
  const st = await call('slicer_folder');
  const el = $('#slicerDirState');
  if (failed(st) || !st) { el.textContent = ''; return; }
  // the field stays empty while the folder is the one found automatically, so
  // "find it for me" is the visible default rather than a path frozen in place
  $('#setSlicerDir').placeholder = st.path;
  el.classList.toggle('bad', !st.exists || !st.plates);
  el.textContent = !st.exists ? t('set.folderMissing')
    : !st.plates ? t('set.folderEmpty')
      : t('set.folderOk', { n: st.plates });
}

async function saveSlicerDir(dir) {
  const r = await call('save_settings', { slicer_dir: dir });
  if (failed(r)) return;
  S.settings.slicer_dir = dir;
  $('#setSlicerDir').value = dir;
  await renderSlicerFolder();
  S.slice = null;
  S.snoozed.clear();         // the next check looks in the new folder
  S.sliceFolder = await call('slicer_folder');
  if (failed(S.sliceFolder)) S.sliceFolder = null;
  checkSlices();
  toast(t('toast.folderSaved'));
}

/* Every confirmation given on a slice, so a wrong one can be undone. */
async function renderLearned() {
  const list = await call('learned_matches');
  const box = $('#learnedList');
  if (failed(list) || !list || !list.length) {
    box.innerHTML = `<p class="muted">${esc(t('set.learnedEmpty'))}</p>`;
    return;
  }
  box.innerHTML = list.map((m) => `
    <div class="learned-row">
      <span class="dot" style="background:${esc(m.hex || '#888')}"></span>
      <b>${esc(m.name)}</b>
      <span class="learned-sig">${esc(m.signature)}</span>
      <button class="icon-btn" data-forget="${esc(m.signature)}"
              title="${esc(t('set.forget'))}">${svg('close')}</button>
    </div>`).join('');
  $$('[data-forget]', box).forEach((b) => {
    b.onclick = async () => {
      await call('forget_match', b.dataset.forget);
      renderLearned();
      toast(t('toast.forgot'));
    };
  });
}

/* ---------- confirmation and modals ---------- */
function confirmDialog(title, text, fn) {
  $('#cTitle').textContent = title;
  $('#cText').textContent = text;
  S.confirmFn = fn;
  show('#confirmModal');
}
/* Sheets open on top of sheets -- a filament leads to a print, a print to its
   project, a project back to a print -- and DOM order cannot say that A goes
   over B and B over A. Whichever was opened last is the one on top. */
let modalTop = 60;
function show(sel) {
  const el = $(sel);
  el.style.zIndex = ++modalTop;
  el.hidden = false;
}
function hide(sel) {
  $(sel).hidden = true;
  // back to the floor once none is left, so the number does not climb forever
  if (!$$('.overlay:not([hidden])').length) modalTop = 60;
}

/* ---------- events ---------- */
function wire() {
  $$('.nav-item').forEach((b) => { b.onclick = () => setView(b.dataset.view); });
  $$('[data-goto]').forEach((b) => { b.onclick = () => setView(b.dataset.goto); });
  $('#alertMuted').onclick = unmuteAll;

  $('#ctaNewPrint').onclick = () => openPrint(null);

  $('#btnPickSlicerDir').onclick = async () => {
    const dir = await call('pick_slicer_folder');
    if (failed(dir) || !dir) return;
    saveSlicerDir(dir);
  };
  $('#btnResetSlicerDir').onclick = () => saveSlicerDir('');
  $('#setSlicerDir').onchange = (e) => saveSlicerDir(e.target.value.trim());

  $('#helpRepo').onclick = (e) => {
    e.preventDefault();
    call('open_url', 'https://github.com/xserggio/FilamentTracker#manual');
  };

  $('#amsClear').onclick = () => setAmsSlot(null);
  $('#amsUnits').onchange = async (e) => {
    const r = await call('save_settings', { ams_units: e.target.value });
    if (failed(r)) return;
    S.settings.ams_units = e.target.value;
    renderAms();
  };

  $('#sliceAdd').onclick = () => openPrintFromSlice(S.slice);
  $('#sliceLater').onclick = () => hideSliceCard(false);
  $('#sliceDismiss').onclick = () => hideSliceCard(true);

  $('#invSearch').oninput = (e) => { S.inv.search = e.target.value; renderInventory(); };
  $('#invMaterial').onchange = (e) => { S.inv.material = e.target.value; renderInventory(); };
  $('#invSort').onchange = (e) => { S.inv.sort = e.target.value; renderInventory(); };
  $('#invLowOnly').onchange = (e) => { S.inv.lowOnly = e.target.checked; renderInventory(); };
  $('#invStockOnly').onchange = (e) => { S.inv.stockOnly = e.target.checked; renderInventory(); };
  $('#invArchived').onchange = (e) => { S.inv.archived = e.target.checked; renderInventory(); };

  $('#hisSearch').oninput = (e) => { S.his.search = e.target.value; renderHistory(); };
  $('#hisFilament').onchange = (e) => { S.his.filament = e.target.value; renderHistory(); };
  $('#hisFrom').onchange = (e) => { S.his.from = e.target.value; renderHistory(); };
  $('#hisTo').onchange = (e) => { S.his.to = e.target.value; renderHistory(); };
  $('#hisFailed').onchange = (e) => { S.his.failedOnly = e.target.checked; renderHistory(); };
  $('#hisGroup').onchange = (e) => { S.his.group = e.target.value; renderHistory(); };

  // The column headings stick underneath the filters, and the filters change
  // height when they wrap. Measuring beats guessing, and beats hard-coding a
  // number that is wrong in five of the six languages.
  const bar = $('#view-history .toolbar');
  // less the 22px it is pulled up by, which is what it actually covers
  const measure = () => document.documentElement.style.setProperty(
    '--bar-h', `${Math.round(bar.getBoundingClientRect().height) - 22}px`);
  new ResizeObserver(measure).observe(bar);
  measure();
  $$('#historyTable th[data-sort]').forEach((th) => {
    th.onclick = () => sortHistory(th.dataset.sort);
    th.title = t('his.sortBy', { what: th.textContent.trim() });
  });
  $('#hisGroupThese').onclick = () => groupThese(
    S.picked.size ? [...S.picked].map(byPrintId).filter(Boolean) : filteredPrints());
  $('#hisPickNone').onclick = clearPicked;
  $('#allProjects').onclick = openAllProjects;
  $('#projHistory').onclick = () => {
    const p = S.infoProject;
    hide('#projModal');
    hide('#projectsModal');
    hide('#pinfoModal');
    gotoHistory(p.group_id ? { group: String(p.group_id) } : { search: p.project });
  };
  $('#pinfoEdit').onclick = () => {
    hide('#pinfoModal');
    openPrint(S.infoPrint);
  };
  $('#mmWeigh').onclick = () => {
    hide('#mismatchModal');
    openRoll(S.mismatchTarget, 'adjust');
  };
  $('#mmNew').onclick = () => {
    hide('#mismatchModal');
    openRoll(S.mismatchTarget, 'new');
  };
  $('#gSave').onclick = saveGroup;
  $('#gName').onkeydown = (e) => { if (e.key === 'Enter') saveGroup(); };
  $('#hisClear').onclick = () => {
    S.his = { ...S.his, search: '', filament: '', from: '', to: '',
              failedOnly: false, group: '' };
    $('#hisSearch').value = ''; $('#hisFilament').value = ''; $('#hisGroup').value = '';
    $('#hisFrom').value = ''; $('#hisTo').value = ''; $('#hisFailed').checked = false;
    renderHistory();
  };

  $('#fSealed').onchange = sealedToggled;

  $('#pAddItem').onclick = () => addItemRow();
  $('#pSave').onclick = savePrint;
  $('#failSave').onclick = saveFail;

  $('#fSave').onclick = saveFilament;
  wireBrand('#fBrand', '#fBrandOther', () => loadCatalog($('#fHexTxt').value));
  $('#fMaterial').onchange = () => loadCatalog($('#fHexTxt').value);
  $('#fCatalog').onchange = (e) => {
    const opt = e.target.selectedOptions[0];
    if (!e.target.value) return;
    setHex(e.target.value);
    // the catalogue name is a better colour name than anything typed by hand
    if (opt && opt.dataset.name) $('#fColor').value = opt.dataset.name;
  };
  $('#fHex').oninput = (e) => { $('#fHexTxt').value = e.target.value; };
  $('#fHexTxt').oninput = (e) => {
    if (/^#[0-9a-f]{6}$/i.test(e.target.value)) $('#fHex').value = e.target.value;
  };
  $('#fColor').onblur = async () => {
    if (S.editingFilament) return;
    const hex = await call('guess_color', $('#fColor').value);
    if (!failed(hex) && hex) setHex(hex);
  };
  $('#fDelete').onclick = () => {
    const f = S.filaments.find((x) => x.id === S.editingFilament);
    confirmDialog(t('fil.deleteTitle'), t('fil.deleteText', { name: f.name }), async () => {
      await call('delete_filament', f.id);
      hide('#filModal');
      await reload();
      toast(t('toast.filDeleted'));
    });
  };

  $('#rSave').onclick = saveRoll;
  $('#sparesAdd').onclick = async () => {
    const r = await call('add_spare', { id: S.sparesTarget });
    if (failed(r)) return;
    await reload();
    renderSpares();
    const rows = $$('#sparesList .spare-row');
    if (rows.length) rows[rows.length - 1].querySelector('.sp-brand').focus();
  };

  $('#cOk').onclick = async () => {
    hide('#confirmModal');
    if (S.confirmFn) await S.confirmFn();
    S.confirmFn = null;
  };

  $('#setLang').onchange = async (e) => {
    S.lang = e.target.value;
    applyI18n();
    renderAll();
    await call('save_settings', { lang: S.lang });
  };
  $('#setTheme').onchange = (e) => applyTheme(e.target.value);
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', () => { if (S.settings.theme === 'auto') applyTheme(); });
  }
  $('#saveSettings').onclick = async () => {
    const r = await call('save_settings', {
      lang: $('#setLang').value,
      theme: $('#setTheme').value,
      temp_unit: $('#setTempUnit').value,
      currency: $('#setCurrency').value,
      slicer_watch: $('#setSlicerWatch').checked ? '1' : '0',
      low_threshold_pct: Number($('#setLow').value) || 15,
      default_spool_g: Number($('#setSpool').value) || 1000,
    });
    if (failed(r)) return;
    await reload();
    applyTheme();
    toast(t('toast.prefsSaved'));
  };
  $('#saveDry').onclick = async () => {
    const values = {};
    $$('[data-mat]').forEach((i) => { values[i.dataset.mat] = Number(i.value) || 45; });
    const r = await call('save_dry_days', values);
    if (failed(r)) return;
    await reload();
    toast(t('toast.drySaved'));
  };
  $('#btnImport').onclick = async () => {
    const path = await call('pick_excel');
    if (failed(path) || !path) return;
    toast(t('toast.importing'), 'info');
    const r = await call('import_excel', { path, replace: false });
    if (failed(r) || !r) return;
    await reload();
    toast(t('toast.imported', { f: r.filaments, p: r.prints }));
  };
  $('#btnExport').onclick = async () => {
    const p = await call('export_excel');
    if (!failed(p) && p) toast(t('toast.exported'));
  };
  $('#saveTare').onclick = async () => {
    const values = {};
    $$('[data-tare]').forEach((i) => {
      (values[i.dataset.tare] ||= {})[i.dataset.kind] = Number(i.value) || 220;
    });
    const r = await call('save_spool_tare', values);
    if (failed(r)) return;
    await reload();
    toast(t('toast.tareSaved'));
  };
  $('#btnBackup').onclick = async () => {
    const r = await call('make_backup');
    if (failed(r)) return;
    await reload();
    toast(t('toast.backupDone'));
  };
  $('#btnBackupsOpen').onclick = () => call('open_backups');
  $('#detailEdit').onclick = () => {
    const f = S.filaments.find((x) => x.id === S.detailTarget);
    hide('#detailModal');
    if (f) openFilament(f);
  };
  $('#btnFolder').onclick = () => call('open_data_folder');

  $$('[data-close]').forEach((b) => { b.onclick = () => { b.closest('.overlay').hidden = true; }; });
  $$('.overlay').forEach((o) => { o.onclick = (e) => { if (e.target === o) o.hidden = true; }; });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { const o = $$('.overlay').find((x) => !x.hidden); if (o) o.hidden = true; }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      if (!$('#printModal').hidden) savePrint();
      else if (!$('#failModal').hidden) saveFail();
      else if (!$('#filModal').hidden) saveFilament();
      else if (!$('#rollModal').hidden) saveRoll();
    }
    if (e.key === 'n' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); openPrint(null); }
  });
}

/* ---------- startup ---------- */
async function boot() {
  wire();
  const d = await call('bootstrap');
  if (failed(d) || !d) return;
  absorb(d);
  applyTheme();
  applyI18n();
  setView('dashboard');

  // A brand-new user has nothing to import: drop them where the work happens.
  if (d.empty) {
    setView('inventory');
    toast(t('toast.firstRun'), 'info');
  }

  // Slicing usually happens with this window in the background, so the check
  // runs on a timer as well as whenever the window is looked at again.
  S.sliceFolder = await call('slicer_folder');
  if (failed(S.sliceFolder)) S.sliceFolder = null;
  if (S.view === 'history') setView('history');   // the button appears once we know

  checkSlices();
  S.sliceTimer = setInterval(checkSlices, 45000);
  window.addEventListener('focus', checkSlices);
}

if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener('pywebviewready', boot);

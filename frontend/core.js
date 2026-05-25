/* ── API helpers ── */
async function api(method, path, body) {
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) { const e = await r.json().catch(()=>({error:r.statusText})); throw new Error(e.error || r.statusText); }
  return r.json();
}
const apiGet  = p      => api('GET',    p);
const apiPost = (p, b) => api('POST',   p, b);
const apiPut  = (p, b) => api('PUT',    p, b);
const apiDel  = p      => api('DELETE', p);

/* ── Placeholder SVGs ── */
const FOOD_SVG = {
  manual: `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#c0a880" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/><path d="M9 7h6M9 11h4"/></svg>`,
  ai:     `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#c0a880" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`,
  rss:    `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#c0a880" stroke-width="1.2" stroke-linecap="round"><path d="M4 11a9 9 0 019 9"/><path d="M4 4a16 16 0 0116 16"/><circle cx="5" cy="19" r="1.5" fill="#c0a880" stroke="none"/></svg>`,
  url:    `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#c0a880" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20"/></svg>`,
  camera: `<svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#c0a880" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>`,
};

/* ── Image helpers ── */
function _extract_ld_image(img) {
  if (!img) return null;
  if (typeof img === 'string') return img;
  if (Array.isArray(img) && img.length) return typeof img[0] === 'string' ? img[0] : (img[0].url || null);
  if (typeof img === 'object') return img.url || null;
  return null;
}

/* ── Source badge ── */
function srcBadge(src) {
  const l = { ai:'AI', rss:'RSS', url:'URL', manual:'Manual', camera:'Camera' };
  const c = { ai:'badge-ai', rss:'badge-rss', url:'badge-url', manual:'badge-manual', camera:'badge-camera' };
  return `<span class="src-badge ${c[src]||'badge-manual'}">${l[src]||src||'Manual'}</span>`;
}

function heartBtn(slug, favorited) {
  const filled = favorited ? `fill="var(--amber)" stroke="var(--amber)"` : `fill="none" stroke="white"`;
  return `<button class="heart-btn" onclick="event.stopPropagation();toggleFavorite('${slug}')" title="${favorited?'Remove from favorites':'Add to favorites'}">
    <svg width="14" height="14" viewBox="0 0 24 24" ${filled} stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
    </svg>
  </button>`;
}

/* ── Shared render helpers ── */
function _htmlAttr(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function recipeImageUrl(r) {
  if (!r || !r.image_url) return '';
  return r.image_url + (r.image_url.startsWith('http') ? '' : '?t=' + (r.updated_at || '').replace(/\D/g, ''));
}

function recipeImageHtml(r, opts={}) {
  const src = opts.src || recipeImageUrl(r);
  const alt = opts.alt ?? r?.name ?? '';
  const fallback = opts.fallback || (FOOD_SVG[r?.source_type] || FOOD_SVG.manual);
  const onerror = opts.clearOnError ? `this.parentElement.innerHTML=''` : `this.remove()`;
  return `${src ? `<img src="${_htmlAttr(src)}" alt="${_htmlAttr(alt)}" loading="lazy" onerror="${onerror}">` : ''}${fallback || ''}`;
}

function cardMetaHtml(r) {
  const time = r.total_time || r.cook_time;
  const timeHtml = time ? `<span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${time}</span>` : '';
  const servingsHtml = r.servings ? `<span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> ${r.servings}</span>` : '';
  return `${timeHtml}${servingsHtml}`;
}

function selectionCheckHtml() {
  return `<div class="sel-check"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>`;
}

function quickPlanButtonHtml(slug) {
  return `<button class="quick-plan-btn" onclick="event.stopPropagation();toggleQuickPlan(this,'${slug}')" title="Add to meal plan"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-mid)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="12" y1="14" x2="12" y2="18"/><line x1="10" y1="16" x2="14" y2="16"/></svg></button>`;
}

function renderEmptyState(message, opts={}) {
  const action = opts.actionHtml || '';
  if (opts.compact) return `<div class="empty-state empty-state-compact">${message}${action}</div>`;
  return `<div class="empty-state">${message}${action}</div>`;
}

function renderRecipeCard(r, opts={}) {
  const selectable = !!opts.selectionMode;
  const selected = !!opts.selected;
  const cardClasses = ['recipe-card', opts.className, selectable ? 'selectable' : '', selected ? 'selected' : '']
    .filter(Boolean).join(' ');
  const clickAction = opts.noClick ? '' : (selectable ? `toggleSelectRecipe('${r.slug}')` : (opts.clickAction || `openDrawer('${r.slug}')`));
  const clickAttr = clickAction ? ` onclick="${clickAction}"` : '';
  const imageAdornment = selectable ? selectionCheckHtml() : (opts.imageAdornment ?? srcBadge(r.source_type));
  const favorite = (!selectable && opts.showHeart) ? heartBtn(r.slug, opts.favoriteOverride ?? r.favorited) : '';
  const quickPlan = (!selectable && opts.showQuickPlan) ? quickPlanButtonHtml(r.slug) : '';
  const footExtra = opts.footExtra || '';
  const lastCooked = opts.lastCookedHtml || '';
  const actions = (!selectable && opts.actionsHtml) ? opts.actionsHtml : '';
  const style = opts.style ? ` style="${opts.style}"` : '';

  return `
    <div class="${cardClasses}"${opts.id ? ` id="${opts.id}"` : ''} data-slug="${r.slug}"${clickAttr}${style}>
      <div class="card-img-wrap">
        <div class="card-ph">${recipeImageHtml(r)}</div>
        ${imageAdornment}
        ${favorite}
        ${quickPlan}
      </div>
      <div class="card-body">
        <div class="card-cat">${r.category||'—'} · ${r.cuisine||'—'}</div>
        <div class="card-name">${r.name}</div>
        ${opts.hideMeta ? '' : `<div class="card-foot"><div class="card-meta">${cardMetaHtml(r)}</div>${footExtra}</div>`}
        ${lastCooked}
      </div>
      ${actions}
    </div>`;
}

/* ── Tabs ── */
let currentTab = 'recipes';
let _currentSubTabs = {};
document.querySelectorAll('.nav-item').forEach(el => el.addEventListener('click', () => switchTab(el.dataset.tab)));

function switchTab(tab) {
  if (_selMode) exitSelectMode();
  currentTab = tab;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  document.querySelectorAll('.mobile-nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));

  const activeSubTab = _currentSubTabs[tab];
  _updateSearchAndSelect(tab, activeSubTab);

  if (tab === 'recipes')     _loadSubContent('recipes', activeSubTab || 'library');
  else if (tab === 'planner')     _loadSubContent('planner', activeSubTab || 'plan');
  else if (tab === 'settings')    loadSettings();
  else if (tab === 'pantry')      loadPantry();
  else if (tab === 'generate')    checkAiKey();
}

function switchSubTab(parentTab, subTab) {
  _currentSubTabs[parentTab] = subTab;
  const container = document.getElementById(parentTab + '-sub-tabs');
  if (container) {
    container.querySelectorAll('.sub-tab').forEach(t => t.classList.toggle('active', t.dataset.subtab === subTab));
  }
  const page = document.getElementById('tab-' + parentTab);
  if (page) {
    page.querySelectorAll('.sub-panel').forEach(p => {
      p.classList.toggle('active', p.id === 'sub-' + parentTab + '-' + subTab);
    });
  }
  _updateSearchAndSelect(parentTab, subTab);
  _loadSubContent(parentTab, subTab);
}

function _updateSearchAndSelect(tab, subTab) {
  const searchable = tab === 'recipes' && ['library', 'favorites', 'staging', 'trash'].includes(subTab || 'library');
  document.getElementById('search-wrap').style.display = searchable ? 'flex' : 'none';
  const selectable = tab === 'recipes' && ['library', 'favorites', 'staging'].includes(subTab || 'library');
  const selBtn = document.getElementById('topbar-select-btn');
  if (selBtn) selBtn.style.display = selectable ? '' : 'none';
}

function _activeSubTab(tab) { return _currentSubTabs[tab] || (tab === 'recipes' ? 'library' : 'plan'); }

function _loadSubContent(parentTab, subTab) {
  if (parentTab === 'recipes') {
    if (subTab === 'library') loadRecipes();
    else if (subTab === 'favorites') loadFavorites();
    else if (subTab === 'staging') loadStaged();
    else if (subTab === 'trash') loadTrashed();
  } else if (parentTab === 'planner') {
    if (subTab === 'plan') { loadPlanner(); loadTemplates(); }
    else if (subTab === 'grocery') loadGrocery();
  }
}

document.getElementById('search-input').addEventListener('input', () => {
  const sub = _currentSubTabs['recipes'] || 'library';
  if (currentTab === 'recipes' && sub === 'library') renderRecipes();
  if (currentTab === 'recipes' && sub === 'favorites') renderFavorites();
});

/* ── Version ── */
async function loadVersion() {
  try {
    const v = await apiGet('/api/version');
    const el = document.getElementById('sidebar-version');
    if (!el) return;
    if (v.update_available && v.latest) {
      el.textContent = `v${v.current}`;
      el.insertAdjacentHTML('afterend',
        `<a class="version-badge update" href="${v.release_url}" target="_blank" title="v${v.latest} available">v${v.latest} available</a>`
      );
    } else {
      el.textContent = `v${v.current}`;
    }
  } catch(e) {}
}

/* ── Toast ── */
function toast(msg, type='ok') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ── Dark mode ── */
function applyDarkMode(on) {
  document.documentElement.setAttribute('data-theme', on ? 'dark' : '');
  localStorage.setItem('feedme-dark', on ? '1' : '0');
  const cb = document.getElementById('s-dark-mode');
  if (cb) cb.checked = on;
}

function initDarkMode() {
  const stored = localStorage.getItem('feedme-dark');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const on = stored !== null ? stored === '1' : prefersDark;
  applyDarkMode(on);
}

/* ── Print ── */
function printRecipe() {
  if (!_drawerData) return;
  window.print();
}

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

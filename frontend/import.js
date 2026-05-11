/* ── Add Recipe Modal ── */
let _addMode = null; // 'url' | 'image' | 'text' | 'manual'

function openAddModal() {
  document.getElementById('modal-overlay').classList.add('open');
  document.getElementById('add-modal').classList.add('open');
  _showAddPicker();
}

function closeAddModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('add-modal').classList.remove('open');
  _addMode = null;
}

function _showAddPicker() {
  _addMode = null;
  document.getElementById('add-modal-title').textContent = 'Add Recipe';
  document.getElementById('add-modal-picker').style.display = '';
  document.getElementById('add-modal-foot').style.display = 'none';
  ['url','image','text','manual'].forEach(m => {
    document.getElementById(`add-modal-${m}`).style.display = 'none';
  });
  // Clear results
  ['url-import-result','img-import-result','text-import-result'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
}

function _addBack() { _showAddPicker(); }

const _addTitles = { url: 'From URL', image: 'From Image', text: 'Paste Text', manual: 'Write Manually' };
const _addBtnLabels = { url: 'Import', image: 'Extract Recipe', text: 'Extract Recipe', manual: 'Add Recipe' };

function _addSource(mode) {
  _addMode = mode;
  document.getElementById('add-modal-title').textContent = _addTitles[mode];
  document.getElementById('add-modal-picker').style.display = 'none';
  ['url','image','text','manual'].forEach(m => {
    document.getElementById(`add-modal-${m}`).style.display = m === mode ? '' : 'none';
  });
  document.getElementById('add-modal-foot').style.display = 'flex';
  const btn = document.getElementById('add-modal-btn');
  btn.textContent = _addBtnLabels[mode];
  btn.disabled = mode === 'image'; // image btn enabled only when files selected
  // Clear inputs
  if (mode === 'url') document.getElementById('import-url-input').value = '';
  if (mode === 'text') document.getElementById('import-text-input').value = '';
  if (mode === 'manual') {
    ['m-name','m-desc','m-cat','m-cuisine','m-prep','m-cook','m-servings','m-ingredients','m-instructions'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
  }
}

async function _addSubmit() {
  if (_addMode === 'url')    return _submitUrl();
  if (_addMode === 'image')  return importFromImage();
  if (_addMode === 'text')   return _submitText();
  if (_addMode === 'manual') return _submitManual();
}

async function _submitUrl() {
  const url = document.getElementById('import-url-input').value.trim();
  if (!url) { toast('URL is required', 'err'); return; }
  const btn = document.getElementById('add-modal-btn');
  const result = document.getElementById('url-import-result');
  btn.disabled = true; btn.textContent = 'Importing…';
  result.innerHTML = '';
  try {
    const recipe = await apiPost('/api/import/url', { url });
    result.innerHTML = `<div style="color:var(--sage);font-size:12px;margin-top:6px">✓ <strong>${recipe.name}</strong> added to Staging.</div>`;
    btn.textContent = 'Import Another';
    btn.disabled = false;
    loadStaged();
  } catch(e) {
    result.innerHTML = `<div style="color:#c05040;font-size:12px;margin-top:6px">${e.message}</div>`;
    btn.disabled = false; btn.textContent = 'Import';
  }
}

async function _submitText() {
  const text = document.getElementById('import-text-input').value.trim();
  if (!text) { toast('Please paste some text first', 'err'); return; }
  const btn = document.getElementById('add-modal-btn');
  const result = document.getElementById('text-import-result');
  btn.disabled = true; btn.textContent = 'Extracting…';
  result.innerHTML = '';
  try {
    const recipe = await apiPost('/api/import/text', { text });
    result.innerHTML = `<div style="color:var(--sage);font-size:12px;margin-top:6px">✓ <strong>${recipe.name}</strong> added to Staging.</div>`;
    btn.textContent = 'Extract Another';
    btn.disabled = false;
    loadStaged();
  } catch(e) {
    result.innerHTML = `<div style="color:#c05040;font-size:12px;margin-top:6px">${e.message}</div>`;
    btn.disabled = false; btn.textContent = 'Extract Recipe';
  }
}

async function _submitManual() {
  const name = document.getElementById('m-name').value.trim();
  if (!name) { toast('Recipe name is required', 'err'); return; }
  const prep = parseInt(document.getElementById('m-prep').value) || 0;
  const cook = parseInt(document.getElementById('m-cook').value) || 0;
  const servings = parseInt(document.getElementById('m-servings').value) || 0;
  const ingredients = document.getElementById('m-ingredients').value
    .split('\n').map(l => l.trim()).filter(Boolean);
  const instructions = document.getElementById('m-instructions').value
    .split('\n').map(l => l.trim()).filter(Boolean)
    .map(text => ({ '@type': 'HowToStep', text }));
  const body = {
    '@context': 'https://schema.org', '@type': 'Recipe', name,
    description: document.getElementById('m-desc').value.trim(),
    recipeCategory: document.getElementById('m-cat').value.trim(),
    recipeCuisine: document.getElementById('m-cuisine').value.trim(),
    prepTime:  prep  ? `PT${prep}M`  : '',
    cookTime:  cook  ? `PT${cook}M`  : '',
    totalTime: (prep || cook) ? `PT${prep + cook}M` : '',
    recipeYield: servings ? `${servings} servings` : '',
    recipeIngredient: ingredients, recipeInstructions: instructions,
    nutrition: {}, source_type: 'manual', status: 'active',
  };
  const btn = document.getElementById('add-modal-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await apiPost('/api/import/manual', body);
    toast('Recipe added', 'ok');
    closeAddModal();
    if (currentTab === 'recipes') loadRecipes();
  } catch(e) { toast(e.message, 'err'); }
  btn.disabled = false; btn.textContent = 'Add Recipe';
}

/* ── RSS Import ── */
const RSS_STATUS_KEY = 'feedme_rss_status';

function getRssStatus() {
  try { return JSON.parse(localStorage.getItem(RSS_STATUS_KEY) || '{}'); } catch { return {}; }
}

function setRssStatus(url, data) {
  const all = getRssStatus();
  all[url] = { ...all[url], ...data };
  localStorage.setItem(RSS_STATUS_KEY, JSON.stringify(all));
}

function _timeAgo(ts) {
  if (!ts) return 'Never fetched';
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 2)   return 'Just now';
  if (mins < 60)  return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24)   return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function _feedStatusHtml(st) {
  if (!st || !st.ts) return { dot: '', text: 'Never fetched', tooltip: '' };
  if (st.error) return { dot: 'err', text: `Failed · ${_timeAgo(st.ts)}`, tooltip: st.error };
  const parts = [`${_timeAgo(st.ts)}`];
  if (st.staged > 0) parts.push(`${st.staged} staged`);
  else parts.push('0 new recipes');
  return { dot: 'ok', text: parts.join(' · '), tooltip: 'Last fetch succeeded' };
}

async function loadConnections() {
  try {
    const s = await apiGet('/api/settings');
    // RSS
    const feeds = (s.rss_feeds || '').split(',').map(f => f.trim()).filter(Boolean);
    renderFeedList(feeds);
    if (feeds.length) {
      apiGet('/api/import/rss/stats').then(stats => {
        for (const [url, count] of Object.entries(stats)) {
          const fid = btoa(url).replace(/[^a-zA-Z0-9]/g, '');
          const el = document.getElementById(`fc-${fid}`);
          if (el && count > 0) {
            el.textContent = `${count} recipe${count === 1 ? '' : 's'} imported`;
            el.style.display = '';
          }
        }
      }).catch(() => {});
    }
    const autoFetchSel = document.getElementById('rss-auto-fetch');
    if (autoFetchSel && s.rss_auto_fetch_hours != null) autoFetchSel.value = String(s.rss_auto_fetch_hours);
  } catch(e) {}
}

function renderFeedList(feeds) {
  const btn = document.getElementById('fetch-all-btn');
  const el  = document.getElementById('feed-list');
  btn.style.display = feeds.length ? '' : 'none';

  if (!feeds.length) {
    el.innerHTML = `<div style="color:var(--text-muted);font-size:13px;font-style:italic;padding:8px 0">No feeds yet. Paste a feed URL above and click Add Feed.</div>`;
    return;
  }

  const status = getRssStatus();
  el.innerHTML = feeds.map(f => {
    const st  = _feedStatusHtml(status[f]);
    const fid = btoa(f).replace(/[^a-zA-Z0-9]/g, '');
    return `
    <div class="feed-row" id="fr-${fid}">
      <div class="feed-dot ${st.dot}" id="fd-${fid}" ${st.tooltip ? `title="${st.tooltip.replace(/"/g,'&quot;')}"` : ''}></div>
      <div class="feed-info">
        <div class="feed-url" title="${f}">${f}</div>
        <div class="feed-status" id="fs-${fid}">${st.text}</div>
        <div class="feed-recipe-count" id="fc-${fid}" style="font-size:10px;color:var(--text-muted);margin-top:1px;display:none"></div>
      </div>
      <div class="feed-actions">
        <button class="btn btn-primary btn-xs" id="fb-${fid}" onclick="fetchOneFeed('${f}','${fid}')">Fetch</button>
        <button class="btn btn-ghost btn-xs" onclick="removeFeed('${f}')" style="color:#c05040" title="Remove feed">✕</button>
      </div>
    </div>`;
  }).join('');
}

async function _doFetch(url, fid) {
  const btn  = document.getElementById(`fb-${fid}`);
  const dot  = document.getElementById(`fd-${fid}`);
  const stat = document.getElementById(`fs-${fid}`);
  if (btn)  { btn.disabled = true; btn.textContent = '…'; }
  if (stat) stat.textContent = 'Fetching…';
  try {
    const result = await apiPost('/api/import/rss', { url });
    setRssStatus(url, { ts: Date.now(), staged: result.staged, error: null });
    const st = _feedStatusHtml(getRssStatus()[url]);
    if (dot)  { dot.className = `feed-dot ${st.dot}`; dot.title = st.tooltip || ''; }
    if (stat) stat.textContent = st.text;
    const stageData = await apiGet('/api/recipes?status=staged&per_page=1');
    updateStageBadge(stageData.total || 0);
    return result.staged;
  } catch(e) {
    setRssStatus(url, { ts: Date.now(), error: e.message });
    if (dot)  { dot.className = 'feed-dot err'; dot.title = e.message; }
    if (stat) stat.textContent = `Failed · ${e.message}`;
    return 0;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Fetch'; }
  }
}

async function fetchOneFeed(url, fid) {
  const n = await _doFetch(url, fid);
  if (n > 0) toast(`${n} recipe${n===1?'':'s'} staged`, 'ok');
  else toast('No new recipes found', 'ok');
}

async function fetchAllFeeds() {
  const s = await apiGet('/api/settings').catch(() => null);
  if (!s) return;
  const feeds = (s.rss_feeds || '').split(',').map(f => f.trim()).filter(Boolean);
  if (!feeds.length) return;
  const allBtn = document.getElementById('fetch-all-btn');
  allBtn.disabled = true; allBtn.textContent = 'Fetching…';
  let total = 0;
  for (const f of feeds) {
    const fid = btoa(f).replace(/[^a-zA-Z0-9]/g, '');
    total += await _doFetch(f, fid);
  }
  allBtn.disabled = false; allBtn.textContent = 'Fetch All Feeds';
  toast(total > 0 ? `${total} recipe${total===1?'':'s'} staged` : 'No new recipes found', 'ok');
}

async function addFeed() {
  const input = document.getElementById('rss-url-input');
  const url   = input.value.trim();
  if (!url) { toast('Enter a feed URL', 'err'); return; }
  try {
    const s = await apiGet('/api/settings');
    const feeds = (s.rss_feeds || '').split(',').map(f => f.trim()).filter(Boolean);
    if (feeds.includes(url)) { toast('Feed already saved', 'err'); return; }
    feeds.push(url);
    await apiPost('/api/settings', { ...s, rss_feeds: feeds.join(',') });
    input.value = '';
    renderFeedList(feeds);
    toast('Feed added', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function removeFeed(url) {
  try {
    const s = await apiGet('/api/settings');
    const feeds = (s.rss_feeds || '').split(',').map(f => f.trim()).filter(Boolean).filter(f => f !== url);
    await apiPost('/api/settings', { ...s, rss_feeds: feeds.join(',') });
    renderFeedList(feeds);
    toast('Feed removed', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

function toggleSecret(fieldId, btn) {
  const input = document.getElementById(fieldId);
  const showing = input.type === 'text';
  input.type = showing ? 'password' : 'text';
  // Swap eye icon to slashed version when visible
  btn.querySelector('svg').innerHTML = showing
    ? '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>'
    : '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';
}

/* ── RSS auto-fetch setting ── */
async function saveRssAutoFetch(val) {
  try {
    await apiPost('/api/settings', { rss_auto_fetch_hours: val });
  } catch(e) { toast('Could not save auto-fetch setting', 'err'); }
}

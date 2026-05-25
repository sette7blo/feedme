/* ── Recipes ── */
let recipesData = [];

/* ── Recipe filters ── */
let _filters = { max_time: null, servings: null, protein: null };
let _sort = 'newest';
let _cookTonight = false;
let _pantryCache = null;

const _PROTEINS = ['Chicken', 'Beef', 'Pork', 'Fish', 'Seafood', 'Lamb', 'Turkey', 'Tofu'];

async function toggleCookTonight() {
  _cookTonight = !_cookTonight;
  if (_cookTonight) {
    try {
      const data = await apiGet('/api/pantry');
      _pantryCache = (data || []).map(p => p.food.toLowerCase());
    } catch(e) {
      toast('Could not load pantry', 'err');
      _cookTonight = false;
    }
  }
  buildFilterChips();
  renderRecipes();
}

function _computeCoverage(r) {
  const ingredients = Array.isArray(r.ingredients) ? r.ingredients : [];
  if (!ingredients.length) return { matched: 0, total: 0 };
  const pantry = _pantryCache || [];
  let matched = 0;
  for (const ing of ingredients) {
    const ingLower = ing.toLowerCase();
    if (pantry.some(p => p && ingLower.includes(p))) matched++;
  }
  return { matched, total: ingredients.length };
}

function _parseTimeMinutes(str) {
  if (!str) return null;
  const h = (str.match(/(\d+)\s*h/) || [])[1];
  const m = (str.match(/(\d+)\s*min/) || [])[1];
  const total = (parseInt(h || 0) * 60) + parseInt(m || 0);
  return total || null;
}

function _recipeProtein(r) {
  const haystack = [r.name, r.tags, r.category].join(' ').toLowerCase();
  return _PROTEINS.find(p => haystack.includes(p.toLowerCase())) || null;
}

function buildFilterChips() {
  const bar = document.getElementById('filter-bar');
  if (!bar) return;
  const anyActive = _filters.max_time || _filters.servings || _filters.protein;
  const dd = (key) => `filter-dropdown${_filters[key] ? ' active' : ''}`;

  let html = `<button class="filter-chip cook-tonight-chip${_cookTonight ? ' active' : ''}" onclick="toggleCookTonight()">Cook tonight</button>`;

  html += `<select class="${dd('max_time')}" onchange="setFilter('max_time',this.value)">
    <option value="">Time</option>
    <option value="30"${_filters.max_time===30?' selected':''}>≤ 30 min</option>
    <option value="60"${_filters.max_time===60?' selected':''}>≤ 1 hour</option>
  </select>`;

  html += `<select class="${dd('servings')}" onchange="setFilter('servings',this.value)">
    <option value="">Servings</option>
    <option value="1-2"${_filters.servings==='1-2'?' selected':''}>1–2</option>
    <option value="3-4"${_filters.servings==='3-4'?' selected':''}>3–4</option>
    <option value="5+"${_filters.servings==='5+'?' selected':''}>5+</option>
  </select>`;

  html += `<select class="${dd('protein')}" onchange="setFilter('protein',this.value)">
    <option value="">Protein</option>
    ${_PROTEINS.map(p => `<option value="${p}"${_filters.protein===p?' selected':''}>${p}</option>`).join('')}
  </select>`;

  if (anyActive) {
    html += `<button class="filter-clear-btn" onclick="clearFilters()">Clear</button>`;
  }

  html += `<select class="sort-select" onchange="_sort=this.value;renderRecipes()">
    <option value="newest"${_sort==='newest'?' selected':''}>Newest</option>
    <option value="az"${_sort==='az'?' selected':''}>A – Z</option>
    <option value="cook_time"${_sort==='cook_time'?' selected':''}>Cook time</option>
  </select>`;

  bar.innerHTML = html;
}

function setFilter(key, value) {
  if (!value) {
    _filters[key] = null;
  } else {
    _filters[key] = key === 'max_time' ? parseInt(value) : value;
  }
  buildFilterChips();
  renderRecipes();
}

function clearFilters() {
  _filters = { max_time: null, servings: null, protein: null };
  buildFilterChips();
  renderRecipes();
}

async function loadRecipes() {
  try {
    const data = await apiGet('/api/recipes?status=active&per_page=200');
    recipesData = data.recipes || [];
    buildFilterChips();
    renderRecipes();
  } catch(e) { toast(e.message, 'err'); }
}

function renderRecipes() {
  const q = (document.getElementById('search-input').value || '').toLowerCase();
  const { max_time, servings, protein } = _filters;
  const list = recipesData.filter(r => {
    if (q && !r.name.toLowerCase().includes(q) &&
             !(r.cuisine||'').toLowerCase().includes(q) &&
             !(r.category||'').toLowerCase().includes(q)) return false;
    if (max_time) {
      const mins = _parseTimeMinutes(r.cook_time) || _parseTimeMinutes(r.total_time);
      if (!mins || mins > max_time) return false;
    }
    if (servings) {
      const s = r.servings || 0;
      if (servings === '1-2' && !(s >= 1 && s <= 2)) return false;
      if (servings === '3-4' && !(s >= 3 && s <= 4)) return false;
      if (servings === '5+'  && !(s >= 5)) return false;
    }
    if (protein && _recipeProtein(r) !== protein) return false;
    return true;
  });
  const isFiltered = q || max_time || servings || protein || _cookTonight;
  const countEl = document.getElementById('recipe-count');
  if (countEl) {
    if (isFiltered && list.length > 0) {
      countEl.textContent = `Showing ${list.length} of ${recipesData.length} recipes`;
      countEl.style.display = '';
    } else {
      countEl.style.display = 'none';
    }
  }

  let renderList = [...list];
  if (_cookTonight && _pantryCache) {
    renderList = renderList
      .map(r => ({ ...r, _cov: _computeCoverage(r) }))
      .filter(r => r._cov.matched > 0)
      .sort((a, b) => (b._cov.matched / Math.max(b._cov.total, 1)) - (a._cov.matched / Math.max(a._cov.total, 1)));
  } else if (_sort === 'az') {
    renderList.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  } else if (_sort === 'cook_time') {
    renderList.sort((a, b) => (_parseTimeMinutes(a.cook_time || a.total_time) || 999) - (_parseTimeMinutes(b.cook_time || b.total_time) || 999));
  }

  if (!renderList.length) {
    const hasRecipes = recipesData.length > 0;
    document.getElementById('recipe-grid').innerHTML = hasRecipes
      ? renderEmptyState('No recipes match your filters. ', { actionHtml: '<a href="#" onclick="clearFilters();return false">Clear filters</a>' })
      : renderEmptyState('No recipes yet. Generate one with AI or import from RSS.');
    return;
  }

  document.getElementById('recipe-grid').innerHTML = renderList.map(r => {
    const covBadge = (_cookTonight && r._cov && r._cov.total > 0)
      ? `<span class="coverage-badge">${r._cov.matched}/${r._cov.total} ingredients</span>`
      : '';
    return renderRecipeCard(r, {
      selectionMode: _selMode,
      selected: _selected.has(r.slug),
      showHeart: true,
      footExtra: covBadge,
    });
  }).join('');
}

function _daysAgo(iso) {
  if (!iso) return null;
  const d = Math.floor((Date.now() - new Date(iso + 'Z').getTime()) / 86400000);
  if (d < 1) return 'today';
  if (d === 1) return 'yesterday';
  if (d < 7) return d + ' days ago';
  if (d < 30) return Math.floor(d / 7) + (Math.floor(d / 7) === 1 ? ' week ago' : ' weeks ago');
  if (d < 365) return Math.floor(d / 30) + (Math.floor(d / 30) === 1 ? ' month ago' : ' months ago');
  return Math.floor(d / 365) + (Math.floor(d / 365) === 1 ? ' year ago' : ' years ago');
}

/* ── Favorites ── */
let favoritesData = [];

async function loadFavorites() {
  try {
    const data = await apiGet('/api/recipes?status=favorited&per_page=200');
    favoritesData = data.recipes || [];
    renderFavorites();
  } catch(e) { toast(e.message, 'err'); }
}

function renderFavorites() {
  const q = (document.getElementById('search-input').value || '').toLowerCase();
  const list = favoritesData.filter(r =>
    !q || r.name.toLowerCase().includes(q) ||
    (r.cuisine||'').toLowerCase().includes(q) ||
    (r.category||'').toLowerCase().includes(q)
  );
  const surpriseBtn = document.getElementById('surprise-btn');
  if (surpriseBtn) surpriseBtn.style.display = favoritesData.length >= 2 ? '' : 'none';
  if (!list.length) {
    document.getElementById('favorites-grid').innerHTML =
      renderEmptyState('No favorites yet. Press the heart on any recipe to save it here.');
    return;
  }
  document.getElementById('favorites-grid').innerHTML = list.map(r => renderRecipeCard(r, {
    selectionMode: _selMode,
    selected: _selected.has(r.slug),
    showHeart: true,
    favoriteOverride: true,
    showQuickPlan: true,
    lastCookedHtml: r.last_cooked
      ? `<div class="card-last-cooked">Last made ${_daysAgo(r.last_cooked)}</div>`
      : `<div class="card-last-cooked never">Never cooked</div>`,
  })).join('');
}

function toggleQuickPlan(btn, slug) {
  const existing = btn.parentElement.querySelector('.quick-plan-pop');
  if (existing) { existing.remove(); return; }
  document.querySelectorAll('.quick-plan-pop').forEach(p => p.remove());
  const today = new Date();
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const label = i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    days.push(`<option value="${iso}">${label}</option>`);
  }
  const pop = document.createElement('div');
  pop.className = 'quick-plan-pop';
  pop.onclick = e => e.stopPropagation();
  pop.innerHTML = `
    <select id="qp-day">${days.join('')}</select>
    <select id="qp-meal"><option value="breakfast">Breakfast</option><option value="lunch">Lunch</option><option value="dinner" selected>Dinner</option></select>
    <button class="btn btn-primary btn-xs" onclick="doQuickPlan('${slug}')">Add to plan</button>`;
  btn.parentElement.appendChild(pop);
}

async function doQuickPlan(slug) {
  const day = document.getElementById('qp-day').value;
  const meal = document.getElementById('qp-meal').value;
  try {
    await apiPost('/api/mealplan', { date: day, meal_type: meal, recipe_slug: slug });
    document.querySelectorAll('.quick-plan-pop').forEach(p => p.remove());
    toast('Added to meal plan', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

document.addEventListener('click', () => document.querySelectorAll('.quick-plan-pop').forEach(p => p.remove()));

function surpriseMe() {
  if (!favoritesData.length) return;
  const pick = favoritesData[Math.floor(Math.random() * favoritesData.length)];
  const card = document.querySelector(`#favorites-grid .recipe-card[data-slug="${pick.slug}"]`);
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.style.transition = 'box-shadow .3s';
    card.style.boxShadow = '0 0 0 3px var(--amber), var(--shadow-md)';
    setTimeout(() => { card.style.boxShadow = ''; }, 1500);
  }
  openDrawer(pick.slug);
}

async function toggleFavorite(slug) {
  // If called from drawer (no slug arg), use current drawer recipe
  const targetSlug = slug || _drawerData?.slug;
  if (!targetSlug) return;
  try {
    const result = await apiPost(`/api/recipes/favorite/${targetSlug}`);
    const isFav = result.favorited;
    // Update recipesData in-place
    const r = recipesData.find(r => r.slug === targetSlug);
    if (r) r.favorited = isFav ? 1 : 0;
    // Refresh favorites list if open
    if (currentTab === 'recipes' && _activeSubTab('recipes') === 'favorites') loadFavorites();
    // Re-render recipes grid to update heart state
    if (currentTab === 'recipes' && _activeSubTab('recipes') === 'library') renderRecipes();
    // Update drawer heart if open for this recipe
    const dfav = document.getElementById('d-fav-btn');
    if (dfav && _drawerData?.slug === targetSlug) {
      dfav.classList.toggle('active', isFav);
      dfav.querySelector('svg').setAttribute('fill', isFav ? 'var(--amber)' : 'none');
      dfav.querySelector('svg').setAttribute('stroke', isFav ? 'var(--amber)' : 'currentColor');
    }
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Staging ── */
let stagedData = [];

async function loadStaged() {
  try {
    const data = await apiGet('/api/recipes?status=staged&per_page=200');
    stagedData = data.recipes || [];
    renderStaged();
    updateStageBadge(data.total || 0);
  } catch(e) { toast(e.message, 'err'); }
}

function updateStageBadge(n) {
  const el = document.getElementById('stage-badge');
  el.textContent = n;
  el.style.display = n > 0 ? 'flex' : 'none';
  const stb = document.getElementById('staging-tab-badge');
  if (stb) { stb.textContent = n; stb.style.display = n > 0 ? '' : 'none'; }
  const mb = document.getElementById('mobile-stage-badge');
  if (mb) { mb.textContent = n; mb.style.display = n > 0 ? 'flex' : 'none'; }
}

function renderStaged() {
  if (!stagedData.length) {
    document.getElementById('staging-grid').innerHTML =
      renderEmptyState('No recipes pending review.');
    return;
  }
  const trashSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`;
  document.getElementById('staging-grid').innerHTML = stagedData.map(r => renderRecipeCard(r, {
    className: 'staged-card',
    selectionMode: _selMode,
    selected: _selected.has(r.slug),
    actionsHtml: `
      <div class="staged-actions" onclick="event.stopPropagation()">
        <button class="btn btn-xs" style="background:var(--sage);color:white;flex:1" onclick="approveRecipe('${r.slug}')">✓ Keep</button>
        <button class="btn btn-xs" style="background:#c05040;color:white;padding:4px 8px" onclick="trashRecipe('${r.slug}')" title="Discard">${trashSvg}</button>
      </div>`,
  })).join('');
}

async function approveRecipe(slug) {
  try {
    await apiPost(`/api/recipes/approve/${slug}`);
    stagedData = stagedData.filter(r => r.slug !== slug);
    renderStaged();
    updateStageBadge(stagedData.length);
    toast('Recipe approved', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function trashRecipe(slug) {
  try {
    await apiDel(`/api/recipes/${slug}`);
    stagedData = stagedData.filter(r => r.slug !== slug);
    renderStaged();
    updateStageBadge(stagedData.length);
    toast('Discarded', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Drawer ── */
let _wakeLock    = null;
let _drawerData         = null; // { slug, full } — set each time a drawer opens
let _drawerOrigServings = null;
let _drawerCurServings  = null;
let _noSleepVid  = null;

async function openDrawer(slug) {
  document.getElementById('overlay').classList.add('open');
  document.getElementById('drawer').classList.add('open');
  document.getElementById('d-title').textContent = 'Loading…';
  document.getElementById('d-cat').textContent = '';
  document.getElementById('d-meta').innerHTML = '';
  document.getElementById('d-body').innerHTML = '';
  document.getElementById('d-foot').innerHTML = '';
  document.getElementById('d-img').innerHTML = '';
  try {
    const r = await apiGet(`/api/recipes/${slug}`);
    const full = r.full || r;
    _drawerData = { slug, full };
    const src = r.source_type || 'manual';
    const rawImageUrl = r.image_url || _extract_ld_image(full.image);
    const imageUrl = rawImageUrl && !rawImageUrl.startsWith('http') ? `${rawImageUrl}?t=${Date.now()}` : rawImageUrl;
    document.getElementById('d-img').innerHTML = `
      <div class="d-img-ph">
        ${imageUrl ? `<img src="${imageUrl}" alt="${r.name}" onerror="this.remove()">` : ''}
        ${(FOOD_SVG[src]||FOOD_SVG.manual).replace('width="52" height="52"','width="72" height="72"').replace('stroke="#c0a880"','stroke="#b8906a"')}
        <div class="d-img-shimmer" id="d-img-shimmer"></div>
        <button class="d-img-regen" id="d-img-regen-btn" onclick="regenImage()" title="Regenerate AI photo" style="display:none">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="2" x2="12" y2="5"/>
            <circle cx="12" cy="1.5" r="1" fill="currentColor" stroke="none"/>
            <rect x="4" y="5" width="16" height="13" rx="2.5"/>
            <circle cx="9" cy="11" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="15" cy="11" r="1.5" fill="currentColor" stroke="none"/>
            <line x1="9" y1="15" x2="15" y2="15"/>
          </svg>
        </button>
      </div>`;
    document.getElementById('d-cat').textContent = `${r.category||''} · ${r.cuisine||''}`;
    document.getElementById('d-title').textContent = r.name;
    const origServings = r.servings || _extractServings(full.recipeYield);
    _drawerOrigServings = origServings;
    _drawerCurServings  = origServings;
    document.getElementById('d-meta').innerHTML =
      `${(r.total_time||r.cook_time) ? `<span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${r.total_time||r.cook_time}</span>` : ''}
       ${origServings ? `<div class="d-servings-stepper">
         <button onclick="scaleDrawer(-1)">−</button>
         <span id="d-servings-val">${origServings}</span>
         <button onclick="scaleDrawer(1)">+</button>
       </div><span class="d-servings-label">servings</span>` : ''}`;
    // Show/update favorite button (only for active recipes)
    const dfav = document.getElementById('d-fav-btn');
    if (r.status === 'active') {
      dfav.style.display = 'flex';
      dfav.classList.toggle('active', !!r.favorited);
      dfav.querySelector('svg').setAttribute('fill', r.favorited ? 'var(--amber)' : 'none');
      dfav.querySelector('svg').setAttribute('stroke', r.favorited ? 'var(--amber)' : 'currentColor');
    } else {
      dfav.style.display = 'none';
    }
    const ingredients = full.recipeIngredient || r.ingredients || [];
    const steps = full.recipeInstructions || [];
    const nutrition = full.nutrition || {};
    const hasNutrition = nutrition.calories != null;
    const nutHtml = hasNutrition ? `
      <div class="d-sec">Nutrition <span style="font-size:10px;font-weight:400;color:var(--text-muted);letter-spacing:0;text-transform:none">per serving</span></div>
      <div class="nutrition-grid">
        <div class="nutrition-cell"><div class="nutrition-val">${Math.round(nutrition.calories)}</div><div class="nutrition-lbl">Cal</div></div>
        <div class="nutrition-cell"><div class="nutrition-val">${(nutrition.proteinContent||'—').replace('g','')}</div><div class="nutrition-lbl">Protein</div></div>
        <div class="nutrition-cell"><div class="nutrition-val">${(nutrition.fatContent||'—').replace('g','')}</div><div class="nutrition-lbl">Fat</div></div>
        <div class="nutrition-cell"><div class="nutrition-val">${(nutrition.carbohydrateContent||'—').replace('g','')}</div><div class="nutrition-lbl">Carbs</div></div>
      </div>
      <div style="margin-top:6px;text-align:right"><button class="btn btn-ghost" style="font-size:11px;padding:3px 10px;border-radius:20px" onclick="estimateNutrition('${slug}')">Re-estimate</button></div>` : (r.status === 'active' ? `
      <div style="margin-top:16px">
        <button class="btn btn-ghost btn-sm" onclick="estimateNutrition('${slug}')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Estimate nutrition
        </button>
      </div>` : '');
    document.getElementById('d-body').innerHTML = `
      ${r.description ? `<p class="d-desc">${r.description}</p>` : ''}
      ${(full.tools||[]).length ? `<div class="d-sec">Equipment</div><ul class="ing-list">${(full.tools).map(t=>`<li>${t}</li>`).join('')}</ul>` : ''}
      <div class="d-sec">Ingredients</div>
      <ul class="ing-list" id="d-ing-list">${ingredients.map(i=>`<li>${i}</li>`).join('') || '<li style="color:var(--text-muted)">Not specified</li>'}</ul>
      ${steps.length ? `<div class="d-sec">Method</div><ol class="step-list">${steps.map(s=>`<li>${typeof s==='string'?s:s.text}</li>`).join('')}</ol>` : ''}
      ${nutHtml}
      <div class="cook-log-section" id="d-cook-log"><div style="font-size:12px;color:var(--text-muted)">Loading cook history…</div></div>
      ${full.source_url ? `<div style="margin-top:20px;padding-top:14px;border-top:1px solid var(--border-soft);display:flex;flex-direction:column;gap:7px">
        <a href="${full.source_url}" target="_blank" rel="noopener" style="font-size:11px;color:var(--text-muted);text-decoration:none;display:inline-flex;align-items:center;gap:5px"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>Original source</a>
      </div>` : ''}`;
    // Load cook history async
    if (r.status === 'active') loadCookHistory(slug);
    else { const el = document.getElementById('d-cook-log'); if (el) el.remove(); }
    const trashBtn = `<button class="btn btn-ghost btn-sm d-trash-btn" onclick="trashFromDrawer('${slug}')" title="Move to trash">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
    </button>`;
    const editBtn = `<button class="btn btn-ghost btn-sm" onclick="editDrawer()">Edit</button>`;
    if (r.status === 'staged') {
      document.getElementById('d-foot').innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="approveFromDrawer('${slug}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Keep
        </button>
        ${editBtn}
        ${trashBtn}`;
    } else {
      document.getElementById('d-foot').innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="switchTab('planner');closeDrawer()">+ Add to Plan</button>
        ${editBtn}
        <button class="btn btn-ghost btn-sm cook-mode-btn" id="cook-mode-btn" onclick="toggleCookMode()" title="Keep screen on while cooking">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a7 7 0 0 1 7 7c0 3-1.5 5.5-4 7v2H9v-2c-2.5-1.5-4-4-4-7a7 7 0 0 1 7-7z"/><line x1="9" y1="21" x2="15" y2="21"/></svg>
          Cook Mode
        </button>
        <button class="btn btn-ghost btn-sm" onclick="markAsCooked('${slug}')" title="Mark as cooked today">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Made It
        </button>
        <button class="btn btn-ghost btn-sm" onclick="printRecipe()" title="Print recipe">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
          Print
        </button>
        ${trashBtn}`;
    }
  } catch(e) {
    document.getElementById('d-title').textContent = 'Error loading recipe';
    document.getElementById('d-body').innerHTML = `<p style="color:#c05040">${e.message}</p>`;
  }
}

/* ── Recipe scaling ── */
function _extractServings(recipeYield) {
  if (!recipeYield) return null;
  const m = String(recipeYield).match(/\d+/);
  return m ? parseInt(m[0]) : null;
}

function _parseQty(str) {
  // Mixed fraction: "1 1/2"
  let m = str.match(/^(\d+)\s+(\d+)\/(\d+)/);
  if (m) return parseInt(m[1]) + parseInt(m[2]) / parseInt(m[3]);
  // Simple fraction: "1/2"
  m = str.match(/^(\d+)\/(\d+)/);
  if (m) return parseInt(m[1]) / parseInt(m[2]);
  // Decimal or integer
  m = str.match(/^(\d*\.?\d+)/);
  if (m) return parseFloat(m[1]);
  return null;
}

function _formatQty(n) {
  if (n <= 0) return '0';
  const whole = Math.floor(n);
  const frac  = n - whole;
  const FRACS = [[1/8,'⅛'],[1/4,'¼'],[1/3,'⅓'],[3/8,'⅜'],[1/2,'½'],[5/8,'⅝'],[2/3,'⅔'],[3/4,'¾'],[7/8,'⅞']];
  if (frac < 0.04) return String(whole || Math.round(n));
  for (const [val, sym] of FRACS) {
    if (Math.abs(frac - val) < 0.07) return whole > 0 ? `${whole}${sym}` : sym;
  }
  // Fall back to 1 decimal
  return n % 1 === 0 ? String(n) : n.toFixed(1).replace(/\.0$/, '');
}

function _scaleIngredient(str, ratio) {
  if (ratio === 1) return str;
  // Match a leading quantity (mixed fraction, fraction, or decimal/integer)
  const m = str.match(/^(\d+\s+\d+\/\d+|\d+\/\d+|\d*\.?\d+)(\s*)/);
  if (!m) return str;
  const qty = _parseQty(m[1]);
  if (!qty) return str;
  return _formatQty(qty * ratio) + m[2] + str.slice(m[0].length);
}

function scaleDrawer(delta) {
  if (!_drawerOrigServings) return;
  _drawerCurServings = Math.max(1, _drawerCurServings + delta);
  const valEl = document.getElementById('d-servings-val');
  if (valEl) valEl.textContent = _drawerCurServings;
  const list = document.getElementById('d-ing-list');
  if (!list || !_drawerData) return;
  const ratio = _drawerCurServings / _drawerOrigServings;
  const ingredients = _drawerData.full.recipeIngredient || [];
  list.innerHTML = ingredients.map(i => `<li>${_scaleIngredient(i, ratio)}</li>`).join('')
    || '<li style="color:var(--text-muted)">Not specified</li>';
}

async function trashFromDrawer(slug) {
  try {
    await apiDel(`/api/recipes/${slug}`);
    toast('Moved to trash', 'ok');
    closeDrawer();
    if (currentTab === 'recipes') {
      const sub = _activeSubTab('recipes');
      if (sub === 'library') loadRecipes();
      else if (sub === 'staging') loadStaged();
      else if (sub === 'favorites') loadFavorites();
    }
  } catch(e) { toast(e.message, 'err'); }
}

async function approveFromDrawer(slug) {
  try {
    await apiPost(`/api/recipes/approve/${slug}`);
    toast('Recipe approved', 'ok');
    closeDrawer();
    loadStaged();
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Recipe editing ── */
function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _isoToDisplay(iso) {
  if (!iso) return '';
  const s = iso.replace(/^PT/i, '');
  const h = (s.match(/(\d+)H/i)||[])[1];
  const m = (s.match(/(\d+)M/i)||[])[1];
  if (h && m) return `${h}h ${m}min`;
  if (h) return `${h}h`;
  if (m) return `${m}min`;
  return iso;
}

function _displayToIso(display) {
  if (!display) return '';
  const s = display.trim().toLowerCase();
  if (/^pt/i.test(s)) return s.toUpperCase();
  const h = (s.match(/(\d+)\s*h/)||[])[1];
  const m = (s.match(/(\d+)\s*m/)||[])[1];
  const hv = h ? parseInt(h) : 0;
  const mv = m ? parseInt(m) : 0;
  if (!hv && !mv) { const n = parseInt(s); return isNaN(n) ? '' : `PT${n}M`; }
  return 'PT' + (hv ? `${hv}H` : '') + (mv ? `${mv}M` : '');
}

function editDrawer() {
  if (!_drawerData) return;
  const regenBtn = document.getElementById('d-img-regen-btn');
  if (regenBtn) regenBtn.style.display = '';
  const { slug, full } = _drawerData;
  const ingredients = (full.recipeIngredient || []).join('\n');
  const steps = (full.recipeInstructions || []).map(s => typeof s === 'string' ? s : (s.text || '')).join('\n');
  const tools = (full.tools || []).join('\n');
  const servings = String(full.recipeYield || '').match(/\d+/)?.[0] || '';

  document.getElementById('d-body').innerHTML = `
    <div style="padding-bottom:8px">
      <div class="edit-field">
        <label>Name</label>
        <input class="form-input" id="ef-name" value="${_esc(full.name)}">
      </div>
      <div class="edit-field">
        <label>Description</label>
        <textarea class="form-input" id="ef-desc" rows="3">${_esc(full.description)}</textarea>
      </div>
      <div class="edit-grid">
        <div class="edit-field">
          <label>Category</label>
          <input class="form-input" id="ef-cat" value="${_esc(full.recipeCategory)}">
        </div>
        <div class="edit-field">
          <label>Cuisine</label>
          <input class="form-input" id="ef-cuisine" value="${_esc(full.recipeCuisine)}">
        </div>
      </div>
      <div class="edit-field">
        <label>Keywords</label>
        <input class="form-input" id="ef-keywords" value="${_esc(full.keywords)}">
      </div>
      <div class="edit-field">
        <label>Equipment — one item per line</label>
        <textarea class="form-input" id="ef-tools" rows="3" placeholder="e.g. Dutch oven\nBaking sheet\nStand mixer">${_esc(tools)}</textarea>
      </div>
      <div class="edit-grid">
        <div class="edit-field">
          <label>Prep Time</label>
          <input class="form-input" id="ef-prep" placeholder="e.g. 15min, 1h 30min" value="${_esc(_isoToDisplay(full.prepTime))}">
        </div>
        <div class="edit-field">
          <label>Cook Time</label>
          <input class="form-input" id="ef-cook" placeholder="e.g. 30min" value="${_esc(_isoToDisplay(full.cookTime))}">
        </div>
      </div>
      <div class="edit-grid">
        <div class="edit-field">
          <label>Total Time</label>
          <input class="form-input" id="ef-total" placeholder="e.g. 45min" value="${_esc(_isoToDisplay(full.totalTime))}">
        </div>
        <div class="edit-field">
          <label>Servings</label>
          <input class="form-input" id="ef-servings" type="number" min="1" value="${_esc(servings)}">
        </div>
      </div>
      <div class="edit-field">
        <label>Image</label>
        <div id="ef-img-preview" style="width:72px;height:72px;border-radius:6px;overflow:hidden;background:var(--border-soft)">
          ${full.image ? `<img id="ef-img-thumb" src="${full.image}" style="width:100%;height:100%;object-fit:cover" onerror="this.parentElement.innerHTML=''">` : ''}
        </div>
      </div>
      <div class="edit-field">
        <label>Ingredients — one per line</label>
        <textarea class="form-input" id="ef-ingredients" rows="8">${_esc(ingredients)}</textarea>
      </div>
      <div class="edit-field">
        <label>Instructions — one step per line</label>
        <textarea class="form-input" id="ef-steps" rows="10">${_esc(steps)}</textarea>
      </div>
    </div>`;

  document.getElementById('d-foot').innerHTML = `
    <button class="btn btn-primary btn-sm" onclick="saveDrawer()">Save</button>
    <button class="btn btn-ghost btn-sm" onclick="openDrawer(_drawerData.slug)">Cancel</button>`;
}

async function saveDrawer() {
  const slug = _drawerData?.slug;
  if (!slug) return;
  const name = document.getElementById('ef-name').value.trim();
  if (!name) { toast('Name is required', 'err'); return; }
  const servings = document.getElementById('ef-servings').value.trim();
  const ingredients = document.getElementById('ef-ingredients').value
    .split('\n').map(l => l.trim()).filter(Boolean);
  const steps = document.getElementById('ef-steps').value
    .split('\n').map(l => l.trim()).filter(Boolean)
    .map(t => ({ '@type': 'HowToStep', text: t }));
  const data = {
    name,
    description:        document.getElementById('ef-desc').value.trim(),
    recipeCategory:     document.getElementById('ef-cat').value.trim(),
    recipeCuisine:      document.getElementById('ef-cuisine').value.trim(),
    keywords:           document.getElementById('ef-keywords').value.trim(),
    prepTime:           _displayToIso(document.getElementById('ef-prep').value),
    cookTime:           _displayToIso(document.getElementById('ef-cook').value),
    totalTime:          _displayToIso(document.getElementById('ef-total').value),
    recipeYield:        servings ? `${servings} servings` : '',
    recipeIngredient:   ingredients,
    recipeInstructions: steps,
    tools:              document.getElementById('ef-tools').value.split('\n').map(l=>l.trim()).filter(Boolean),
  };
  try {
    await apiPut(`/api/recipes/${slug}`, data);
    toast('Saved', 'ok');
    openDrawer(slug);
    if (currentTab === 'recipes') _loadSubContent('recipes', _activeSubTab('recipes'));
  } catch(e) { toast(e.message || 'Save failed', 'err'); }
}

async function regenImage() {
  const slug = _drawerData?.slug;
  if (!slug) return;
  const btn = document.getElementById('d-img-regen-btn');
  const shimmer = document.getElementById('d-img-shimmer');
  if (btn) { btn.disabled = true; btn.classList.add('loading'); }
  if (shimmer) shimmer.classList.add('visible');
  try {
    const res = await apiPost(`/api/recipes/${slug}/regenerate-image`, {});
    if (res.image) {
      const src = res.image + '?t=' + Date.now();
      // Update drawer image
      const ph = document.getElementById('d-img').querySelector('.d-img-ph');
      if (ph) {
        let img = ph.querySelector('img');
        if (img) { img.src = src; } else { ph.insertAdjacentHTML('afterbegin', `<img src="${src}" alt="" onerror="this.remove()">`); }
      }
      // Update recipe card in grid
      const card = document.querySelector(`.recipe-card[data-slug="${slug}"]`);
      if (card) {
        const cardPh = card.querySelector('.card-ph');
        if (cardPh) {
          let img = cardPh.querySelector('img');
          if (img) { img.src = src; } else { cardPh.insertAdjacentHTML('afterbegin', `<img src="${src}" alt="" onerror="this.remove()">`); }
        }
      }
      // Update edit form preview
      const preview = document.getElementById('ef-img-preview');
      if (preview) preview.innerHTML = `<img src="${src}" style="width:100%;height:100%;object-fit:cover">`;
      toast('Image regenerated', 'ok');
    }
  } catch(e) { toast(e.message || 'Image generation failed', 'err'); }
  finally {
    if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
    if (shimmer) shimmer.classList.remove('visible');
  }
}

function closeDrawer() {
  document.getElementById('overlay').classList.remove('open');
  document.getElementById('drawer').classList.remove('open');
  _releaseCookMode();
}

/* ── Cook Mode (Wake Lock API; video fallback for non-iOS HTTP) ── */
async function toggleCookMode() {
  if (_wakeLock || _noSleepVid) {
    _releaseCookMode(); return;
  }
  _setCookModeUI(true);
  await _acquireWakeLock();
}

async function _acquireWakeLock() {
  if (_wakeLock || _noSleepVid) return;
  if ('wakeLock' in navigator) {
    try {
      _wakeLock = await navigator.wakeLock.request('screen');
      _wakeLock.addEventListener('release', _onWakeLockReleased);
      return;
    } catch(e) {}
  }
  try {
    _noSleepVid = document.createElement('video');
    _noSleepVid.setAttribute('playsinline', '');
    _noSleepVid.muted = true;
    _noSleepVid.loop  = true;
    _noSleepVid.style.cssText = 'position:fixed;top:-2px;left:-2px;width:1px;height:1px;opacity:0;pointer-events:none';
    // WebM for Chrome/Firefox, MP4 for Safari/iOS
    _noSleepVid.innerHTML = '<source src="/nosleep.webm" type="video/webm"><source src="/nosleep.mp4" type="video/mp4">';
    document.body.appendChild(_noSleepVid);
    await _noSleepVid.play();
  } catch(e) {
    if (_noSleepVid) { _noSleepVid.remove(); _noSleepVid = null; }
  }
}

function _releaseCookMode() {
  if (_wakeLock) { _wakeLock.release(); _wakeLock = null; }
  if (_noSleepVid) { _noSleepVid.pause(); _noSleepVid.remove(); _noSleepVid = null; }
  _setCookModeUI(false);
}

function _onWakeLockReleased() {
  _wakeLock = null;
  _setCookModeUI(false);
}

function _setCookModeUI(active) {
  const btn = document.getElementById('cook-mode-btn');
  if (!btn) return;
  btn.classList.toggle('active', active);
  btn.title = active ? 'Screen is kept on — click to turn off' : 'Keep screen on while cooking';
}

// Re-acquire wake lock when tab comes back to foreground (native API only)
document.addEventListener('visibilitychange', async () => {
  if (!_wakeLock || document.visibilityState !== 'visible') return;
  try {
    _wakeLock = await navigator.wakeLock.request('screen');
    _wakeLock.addEventListener('release', _onWakeLockReleased);
  } catch(e) { /* silently ignore */ }
});

/* ── Nutrition ── */
async function estimateNutrition(slug) {
  const bodyEl = document.getElementById('d-body');
  if (!bodyEl) return;
  // Find or insert a nutrition placeholder
  let nutEl = bodyEl.querySelector('.nutrition-estimating');
  if (!nutEl) {
    const btn = bodyEl.querySelector('button[onclick*="estimateNutrition"]');
    if (btn) { btn.disabled = true; btn.textContent = 'Estimating…'; }
  }
  try {
    const res = await apiPost(`/api/recipes/${slug}/nutrition`, {});
    // Reload drawer to show new nutrition data
    openDrawer(slug);
    toast('Nutrition estimated', 'ok');
  } catch(e) {
    toast(e.message || 'Estimation failed', 'err');
    const btn = bodyEl.querySelector('button[onclick*="estimateNutrition"]');
    if (btn) { btn.disabled = false; btn.textContent = 'Estimate nutrition'; }
  }
}

/* ── Cook log ── */
async function markAsCooked(slug) {
  const defaultServings = _drawerData?.servings || null;
  try {
    await apiPost(`/api/cooklog/${slug}`, { servings: defaultServings });
    toast('Marked as cooked', 'ok');
    loadCookHistory(slug);
  } catch(e) { toast(e.message, 'err'); }
}

async function loadCookHistory(slug) {
  const el = document.getElementById('d-cook-log');
  if (!el) return;
  try {
    const history = await apiGet(`/api/cooklog/${slug}`);
    if (!history.length) {
      el.innerHTML = `<div class="d-sec" style="margin-top:16px">Cook History</div><div style="font-size:12px;color:var(--text-muted);font-style:italic;padding:4px 0">Not cooked yet</div>`;
      return;
    }
    const fmt = iso => {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    };
    const days = iso => {
      const diff = Math.floor((Date.now() - new Date(iso)) / 86400000);
      if (diff === 0) return 'today';
      if (diff === 1) return 'yesterday';
      return `${diff}d ago`;
    };
    el.innerHTML = `<div class="d-sec" style="margin-top:16px">Cook History</div>` +
      history.map(e => `<div class="cook-log-entry">
        <span class="cook-log-date">${fmt(e.cooked_at)} <span style="opacity:.6">(${days(e.cooked_at)})</span></span>
        ${e.servings ? `<span style="font-size:12px;color:var(--text-muted)">${e.servings} srv</span>` : ''}
        ${e.notes ? `<span class="cook-log-note">${e.notes}</span>` : ''}
      </div>`).join('');
  } catch(e) {
    el.innerHTML = '';
  }
}

/* ── Trash ── */
let trashedData = [];

async function loadTrashed() {
  try {
    const data = await apiGet('/api/recipes?status=trashed&per_page=200');
    trashedData = data.recipes || [];
    renderTrashed();
  } catch(e) { toast(e.message, 'err'); }
}

function renderTrashed() {
  const btn = document.getElementById('empty-trash-btn');
  if (!trashedData.length) {
    document.getElementById('trash-grid').innerHTML = renderEmptyState('Trash is empty.');
    if (btn) btn.style.display = 'none';
    return;
  }
  if (btn) btn.style.display = '';
  document.getElementById('trash-grid').innerHTML = trashedData.map(r => renderRecipeCard(r, {
    id: `tr-${r.slug}`,
    style: 'opacity:.72',
    hideMeta: true,
    noClick: true,
    actionsHtml: `
      <div class="staged-actions" onclick="event.stopPropagation()">
        <button class="btn btn-xs" style="background:var(--sage);color:white;flex:1" onclick="restoreRecipe('${r.slug}')">↩ Restore</button>
        <button class="btn btn-xs" style="background:#c05040;color:white" onclick="permanentDelete('${r.slug}')">Delete Forever</button>
      </div>`,
  })).join('');
}

async function restoreRecipe(slug) {
  try {
    await apiPost(`/api/recipes/restore/${slug}`);
    trashedData = trashedData.filter(r => r.slug !== slug);
    renderTrashed();
    toast('Recipe restored', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function permanentDelete(slug) {
  if (!confirm('Permanently delete this recipe? This cannot be undone.')) return;
  try {
    await apiDel(`/api/recipes/permanent/${slug}`);
    trashedData = trashedData.filter(r => r.slug !== slug);
    renderTrashed();
    toast('Deleted permanently', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function emptyTrash() {
  if (!trashedData.length) return;
  if (!confirm(`Permanently delete all ${trashedData.length} recipe${trashedData.length===1?'':'s'} in trash? This cannot be undone.`)) return;
  try {
    const result = await _batchRecipeAction('permanent_delete', trashedData.map(r => r.slug));
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    trashedData = trashedData.filter(r => !okSlugs.includes(r.slug));
    renderTrashed();
    toast(_batchMessage(result, 'Trash emptied'), 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Selection mode ── */
let _selMode = false;
let _selected = new Set();

function _syncSelToggleBtns(active) {
  ['topbar-select-btn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', active);
  });
}

function _renderCurrentGrid() {
  const sub = _activeSubTab('recipes');
  if (currentTab === 'recipes' && sub === 'library') renderRecipes();
  else if (currentTab === 'recipes' && sub === 'favorites') renderFavorites();
  else if (currentTab === 'recipes' && sub === 'staging') renderStaged();
}

function toggleSelectMode() {
  _selMode = !_selMode;
  _selected.clear();
  _syncSelToggleBtns(_selMode);
  _updateBulkBar();
  _renderCurrentGrid();
}

function exitSelectMode() {
  _selMode = false;
  _selected.clear();
  _syncSelToggleBtns(false);
  _updateBulkBar();
  _renderCurrentGrid();
}

function toggleSelectRecipe(slug) {
  if (_selected.has(slug)) _selected.delete(slug);
  else _selected.add(slug);
  // Update just this card's visual state
  const card = document.querySelector(`.recipe-card[data-slug="${slug}"]`);
  if (card) card.classList.toggle('selected', _selected.has(slug));
  _updateBulkBar();
}

function _updateBulkBar() {
  const bar       = document.getElementById('bulk-bar');
  const selInfo   = document.getElementById('topbar-sel-info');
  const selCount  = document.getElementById('topbar-sel-count');
  const searchEl  = document.getElementById('search-wrap');
  const favBtn    = document.getElementById('bulk-fav-btn');
  const unfavBtn  = document.getElementById('bulk-unfav-btn');
  const keepBtn   = document.getElementById('bulk-keep-btn');
  const trashBtn  = document.getElementById('bulk-trash-btn');
  const delBtn    = document.getElementById('bulk-del-btn');
  if (!bar) return;
  const n = _selected.size;
  const searchable = currentTab === 'recipes';

  // Topbar: swap search ↔ count
  if (selInfo) selInfo.style.display = _selMode ? 'flex' : 'none';
  if (searchEl) searchEl.style.display = (_selMode || !searchable) ? 'none' : 'flex';
  if (selCount) selCount.textContent = n === 0
    ? 'Select recipes below'
    : `${n} recipe${n !== 1 ? 's' : ''} selected`;

  // Bulk bar slides up only when something is selected
  bar.classList.toggle('open', _selMode && n > 0);

  const sub     = _activeSubTab('recipes');
  const onFav   = currentTab === 'recipes' && sub === 'favorites';
  const onStage = currentTab === 'recipes' && sub === 'staging';
  if (favBtn)   favBtn.style.display   = (!onFav && !onStage) ? '' : 'none';
  if (unfavBtn) unfavBtn.style.display = onFav   ? '' : 'none';
  if (keepBtn)  keepBtn.style.display  = onStage ? '' : 'none';
  if (trashBtn) trashBtn.style.display = onStage ? '' : 'none';
  if (delBtn)   delBtn.style.display   = !onStage ? '' : 'none';
}

function deselectAll() {
  _selected.clear();
  document.querySelectorAll('.recipe-card.selected').forEach(c => c.classList.remove('selected'));
  _updateBulkBar();
}

function _batchMessage(result, label) {
  if (!result || !result.failed) return label;
  return `${label} · ${result.failed} failed`;
}

async function _batchRecipeAction(action, slugs) {
  return apiPost('/api/recipes/batch', { action, slugs });
}

async function bulkFavorite() {
  const slugs = [..._selected];
  if (!slugs.length) return;
  try {
    const result = await _batchRecipeAction('favorite', slugs);
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    okSlugs.forEach(slug => {
      const r = recipesData.find(r => r.slug === slug);
      if (r) r.favorited = 1;
    });
    toast(_batchMessage(result, `${result.ok} recipe${result.ok!==1?'s':''} added to favorites`));
    exitSelectMode();
  } catch(e) { toast(e.message, 'err'); }
}

async function bulkUnfavorite() {
  const slugs = [..._selected];
  if (!slugs.length) return;
  try {
    const result = await _batchRecipeAction('unfavorite', slugs);
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    favoritesData = favoritesData.filter(r => !okSlugs.includes(r.slug));
    okSlugs.forEach(slug => {
      const r = recipesData.find(r => r.slug === slug);
      if (r) r.favorited = 0;
    });
    toast(_batchMessage(result, `${result.ok} recipe${result.ok!==1?'s':''} removed from favorites`));
    exitSelectMode();
  } catch(e) { toast(e.message, 'err'); }
}

async function bulkTrash() {
  const slugs = [..._selected];
  if (!slugs.length) return;
  if (!confirm(`Move ${slugs.length} recipe${slugs.length!==1?'s':''} to trash?`)) return;
  try {
    const result = await _batchRecipeAction('trash', slugs);
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    recipesData   = recipesData.filter(r => !okSlugs.includes(r.slug));
    favoritesData = favoritesData.filter(r => !okSlugs.includes(r.slug));
    toast(_batchMessage(result, `${result.ok} recipe${result.ok!==1?'s':''} moved to trash`));
    exitSelectMode();
    if (currentTab === 'recipes') _loadSubContent('recipes', _activeSubTab('recipes'));
  } catch(e) { toast(e.message, 'err'); }
}

async function bulkKeep() {
  const slugs = [..._selected];
  if (!slugs.length) return;
  try {
    const result = await _batchRecipeAction('approve', slugs);
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    stagedData = stagedData.filter(r => !okSlugs.includes(r.slug));
    updateStageBadge(stagedData.length);
    toast(_batchMessage(result, `${result.ok} recipe${result.ok!==1?'s':''} approved`));
    exitSelectMode();
  } catch(e) { toast(e.message, 'err'); }
}

async function bulkTrashStaged() {
  const slugs = [..._selected];
  if (!slugs.length) return;
  if (!confirm(`Discard ${slugs.length} recipe${slugs.length!==1?'s':''}?`)) return;
  try {
    const result = await _batchRecipeAction('discard', slugs);
    const okSlugs = result.results.filter(r => r.ok).map(r => r.slug);
    stagedData = stagedData.filter(r => !okSlugs.includes(r.slug));
    updateStageBadge(stagedData.length);
    toast(_batchMessage(result, `${result.ok} recipe${result.ok!==1?'s':''} discarded`));
    exitSelectMode();
  } catch(e) { toast(e.message, 'err'); }
}

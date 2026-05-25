/* ── Meal Planner ── */
const DAYS  = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const MEALS = ['breakfast','lunch','dinner'];
let weekOffset = 0;
let planData = {};

function isoDate(d) { return d.toISOString().split('T')[0]; }
function mondayOf(d) { const day=new Date(d); day.setDate(day.getDate()-(day.getDay()+6)%7); return day; }
function shiftWk(n) { weekOffset += n; loadPlanner(); }

async function loadPlanner() {
  const base = mondayOf(new Date());
  base.setDate(base.getDate() + weekOffset * 7);
  try {
    const entries = await apiGet(`/api/mealplan?week=${isoDate(base)}`);
    planData = {};
    for (const e of entries) {
      if (!planData[e.date]) planData[e.date] = {};
      if (!planData[e.date][e.meal_type]) planData[e.date][e.meal_type] = [];
      planData[e.date][e.meal_type].push(e);
    }
  } catch(e) { planData = {}; }
  renderPlanner(base);
}

function renderPlanner(base) {
  if (!base) { base = mondayOf(new Date()); base.setDate(base.getDate()+weekOffset*7); }
  const today = new Date().toDateString();
  const end   = new Date(base); end.setDate(end.getDate()+6);
  const fmt   = d => d.toLocaleDateString('en-US',{month:'long',day:'numeric'});
  document.getElementById('week-label').textContent = `${fmt(base)} – ${fmt(end)}`;
  document.getElementById('week-grid').innerHTML = DAYS.map((d,i) => {
    const date    = new Date(base); date.setDate(date.getDate()+i);
    const dateStr = isoDate(date);
    const isToday = date.toDateString() === today;
    const day     = planData[dateStr] || {};
    return `<div>
      <div class="day-hdr"><div class="day-name">${d}</div>
        ${isToday
          ? `<div class="day-today">${date.getDate()}</div>`
          : `<span class="day-num">${date.getDate()}</span>`}
      </div>
      ${MEALS.map(m => {
        const entries = day[m] || [];
        if (!entries.length) return `<div class="meal-slot" onclick="openPicker('${dateStr}','${m}')"><div class="slot-lbl">${m}</div><div class="slot-add">+ Add</div></div>`;
        return `<div class="meal-slot filled">
          <div class="slot-lbl">${m}</div>
          ${entries.map(e => `<div class="slot-item" onclick="openDrawer('${e.recipe_slug}')">
            <div class="slot-name">${e.recipe_name||e.recipe_slug}</div>
            <div class="slot-servings">
              <button onclick="event.stopPropagation();updateMealServings(${e.id},${(e.servings||1)-1})">-</button>
              <span>${e.servings||1} srv</span>
              <button onclick="event.stopPropagation();updateMealServings(${e.id},${(e.servings||1)+1})">+</button>
              <span class="slot-remove" onclick="event.stopPropagation();removeMealSlot(${e.id},'${dateStr}','${m}')" title="Remove">&#x2715;</span>
            </div>
          </div>`).join('')}
          <div class="slot-add-more" onclick="openPicker('${dateStr}','${m}')">+ Add</div>
        </div>`;
      }).join('')}
    </div>`;
  }).join('');
}

async function generateGroceryList() {
  const base = mondayOf(new Date()); base.setDate(base.getDate()+weekOffset*7);
  const end  = new Date(base); end.setDate(end.getDate()+6);
  try {
    const result = await apiPost('/api/grocery/generate', {
      start: isoDate(base), end: isoDate(end), list_date: isoDate(new Date())
    });
    const added   = result.added   ?? 0;
    const covered = result.covered ?? 0;
    let msg = `${added} item${added===1?'':'s'} to buy`;
    if (covered > 0) msg += ` · ${covered} already in pantry`;
    toast(msg, 'ok');
    switchTab('planner');switchSubTab('planner','grocery');
    renderGrocery(result.items || [], result.pantry_items || []);
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Recipe picker ── */
let pickerAll = [];
let pickerDate = '';
let pickerMeal = '';

async function openPicker(date, meal) {
  pickerDate = date;
  pickerMeal = meal;
  const dayLabel = new Date(date + 'T12:00:00').toLocaleDateString('en-US', {weekday:'long', month:'short', day:'numeric'});
  document.getElementById('picker-title').textContent = `${meal.charAt(0).toUpperCase()+meal.slice(1)} · ${dayLabel}`;
  document.getElementById('picker-search').value = '';
  document.getElementById('picker-overlay').classList.add('open');
  document.getElementById('picker-modal').classList.add('open');
  document.getElementById('picker-grid').innerHTML = '<div style="color:var(--text-muted);font-size:13px">Loading…</div>';
  try {
    const data = await apiGet('/api/recipes?status=active&per_page=200');
    pickerAll = data.recipes || [];
    renderPickerGrid(pickerAll);
  } catch(e) {
    document.getElementById('picker-grid').innerHTML = `<div style="color:#c05040;font-size:13px">${e.message}</div>`;
  }
}

function closePicker() {
  document.getElementById('picker-overlay').classList.remove('open');
  document.getElementById('picker-modal').classList.remove('open');
}

function filterPicker(q) {
  const filtered = q.trim()
    ? pickerAll.filter(r => r.name.toLowerCase().includes(q.toLowerCase())
        || (r.category||'').toLowerCase().includes(q.toLowerCase()))
    : pickerAll;
  renderPickerGrid(filtered);
}

function renderPickerGrid(recipes) {
  if (!recipes.length) {
    document.getElementById('picker-grid').innerHTML =
      '<div style="color:var(--text-muted);font-size:13px;font-style:italic">No recipes found.</div>';
    return;
  }
  document.getElementById('picker-grid').innerHTML = recipes.map(r => `
    <div class="picker-card" onclick="pickRecipe('${r.slug}')">
      <div class="picker-card-img">
        ${r.image_url
          ? `<img src="${r.image_url}" alt="${r.name}" onerror="this.parentElement.innerHTML=''">`
          : `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M8 12c0-2.2 1.8-4 4-4s4 1.8 4 4"/><path d="M12 16v-4"/></svg>`}
      </div>
      <div class="picker-card-body">
        <div class="picker-card-cat">${r.category||'—'}</div>
        <div class="picker-card-name">${r.name}</div>
      </div>
    </div>`).join('');
}

async function pickRecipe(slug) {
  try {
    await apiPost('/api/mealplan', { date: pickerDate, meal_type: pickerMeal, recipe_slug: slug });
    closePicker();
    await loadPlanner();
    toast('Added to plan', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function updateMealServings(id, newServings) {
  if (newServings < 1) return;
  try {
    await apiPut(`/api/mealplan/${id}`, { servings: newServings });
    await loadPlanner();
  } catch(e) { toast(e.message, 'err'); }
}

async function removeMealSlot(id, date, meal) {
  try {
    await apiDel(`/api/mealplan/${id}`);
    await loadPlanner();
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Grocery ── */
async function loadGrocery() {
  try {
    const data = await apiGet('/api/grocery');
    renderGrocery(data.items || data, data.pantry_items || []);
  } catch(e) { toast(e.message, 'err'); }
}

function renderGrocery(items, pantryItems) {
  // Group items by category
  const catOrder = ['Produce','Meat & Fish','Dairy & Eggs','Bakery','Dry Goods','Canned & Jarred','Frozen','Condiments & Spices','Beverages','Other'];
  const groups = {};
  (items||[]).forEach(item => {
    const cat = item.category || 'Other';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(item);
  });
  const orderedCats = [...catOrder.filter(c => groups[c]), ...Object.keys(groups).filter(c => !catOrder.includes(c))];
  const buyHtml = orderedCats.map(cat => {
    const catItems = groups[cat];
    return `<div class="grocery-cat-header">${cat}</div>` +
      catItems.map(item => `
        <div class="grocery-item ${item.checked?'checked':''}" id="gi-${item.id}">
          <input type="checkbox" ${item.checked?'checked':''} onchange="toggleGrocery(${item.id},this.checked)">
          <span class="g-food">${item.food}</span>
          ${item.quantity != null ? `<span class="g-qty">${item.quantity} ${item.unit||''}</span>` : ''}
          ${item.recipes && item.recipes.length ? `<div class="g-recipes">${item.recipes.map(r => `<span class="g-recipe-tag" onclick="event.stopPropagation();openDrawer('${r.slug}')">${r.name}</span>`).join('')}</div>` : ''}
        </div>`).join('');
  }).join('');

  const pantryHtml = (pantryItems||[]).length ? `
    <div class="pantry-covered-section">
      <div class="pantry-covered-label">From your pantry</div>
      ${pantryItems.map(item => `
        <div class="pantry-covered-item">
          <svg class="pantry-covered-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 3h14M5 3a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2M9 12l2 2 4-4"/>
          </svg>
          <span class="pantry-covered-food">${item.food}</span>
          ${item.quantity != null ? `<span class="pantry-covered-qty">${item.quantity} ${item.unit||''}</span>` : ''}
        </div>`).join('')}
    </div>` : '';

  document.getElementById('grocery-list').innerHTML =
    (buyHtml || `<div style="color:var(--text-muted);font-style:italic;padding:8px 0">No items to buy. Generate from meal plan or add manually.</div>`)
    + pantryHtml;
}

async function toggleGrocery(id, checked) {
  try {
    await apiPut(`/api/grocery/${id}`, { checked });
    document.getElementById(`gi-${id}`).classList.toggle('checked', checked);
  } catch(e) { toast(e.message, 'err'); }
}

async function addGrocery() {
  const v = document.getElementById('gr-input').value.trim();
  if (!v) return;
  try {
    await apiPost('/api/grocery', { food: v });
    document.getElementById('gr-input').value = '';
    await loadGrocery();
  } catch(e) { toast(e.message, 'err'); }
}

async function clearChecked() {
  try {
    await apiDel('/api/grocery/clear');
    await loadGrocery();
    toast('Cleared', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function clearList() {
  if (!confirm('Clear the entire grocery list, including "From your pantry"?')) return;
  try {
    await apiDel('/api/grocery/clear-all');
    await loadGrocery();
    toast('List cleared', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Week plan modal ── */
let _wplanMeals = new Set(['dinner']);
let _wplanPlan  = [];

function openWeekPlanModal() {
  _wplanPlan = [];
  document.getElementById('wplan-result').style.display = 'none';
  document.getElementById('wplan-gen-btn').style.display = '';
  document.getElementById('wplan-regen-btn').style.display = 'none';
  document.getElementById('wplan-accept-btn').style.display = 'none';
  document.getElementById('wplan-overlay').classList.add('open');
  document.getElementById('wplan-modal').classList.add('open');
}

function closeWeekPlanModal() {
  document.getElementById('wplan-overlay').classList.remove('open');
  document.getElementById('wplan-modal').classList.remove('open');
}

function toggleWplanMeal(meal) {
  if (_wplanMeals.has(meal)) {
    if (_wplanMeals.size === 1) return; // keep at least one
    _wplanMeals.delete(meal);
  } else {
    _wplanMeals.add(meal);
  }
  document.getElementById(`wpm-${meal}`).classList.toggle('active', _wplanMeals.has(meal));
}

async function generateWeekPlan() {
  const genBtn  = document.getElementById('wplan-gen-btn');
  const regenBtn = document.getElementById('wplan-regen-btn');
  genBtn.disabled  = true;
  genBtn.textContent = 'Generating…';
  if (regenBtn) { regenBtn.disabled = true; }
  try {
    const dietary = Array.from(document.querySelectorAll('#wplan-dietary-chips .opt-chip.selected'))
      .map(el => el.textContent.trim());
    const res = await apiPost('/api/mealplan/generate', {
      week_start:          (() => { const b = mondayOf(new Date()); b.setDate(b.getDate()+weekOffset*7); return isoDate(b); })(),
      meals:               Array.from(_wplanMeals),
      people:              parseInt(document.getElementById('wplan-people').value) || null,
      max_weeknight_mins:  parseInt(document.getElementById('wplan-maxtime').value) || null,
      dietary,
      use_pantry:          document.getElementById('wplan-pantry').checked,
      prompt:              document.getElementById('wplan-prompt').value.trim(),
    });
    _wplanPlan = res.plan || [];
    _renderWplanResult();
    document.getElementById('wplan-result').style.display = '';
    document.getElementById('wplan-gen-btn').style.display = 'none';
    document.getElementById('wplan-regen-btn').style.display = '';
    document.getElementById('wplan-accept-btn').style.display = '';
    regenBtn.disabled = false;
  } catch(e) {
    toast(e.message || 'Generation failed', 'err');
  } finally {
    genBtn.disabled = false;
    genBtn.textContent = 'Generate';
    if (regenBtn) regenBtn.disabled = false;
  }
}

const _DAY_ABBR = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
function _renderWplanResult() {
  const list = document.getElementById('wplan-plan-list');
  if (!_wplanPlan.length) {
    list.innerHTML = '<div style="color:var(--text-muted);font-style:italic;padding:8px 0">No plan generated — try relaxing constraints.</div>';
    return;
  }
  const sorted = [..._wplanPlan].sort((a,b) => a.date.localeCompare(b.date) || a.meal_type.localeCompare(b.meal_type));
  list.innerHTML = sorted.map((e,i) => {
    const d = new Date(e.date + 'T00:00:00');
    const dayLabel = _DAY_ABBR[d.getDay() === 0 ? 6 : d.getDay() - 1] || e.date.slice(5);
    return `<div class="wplan-plan-item preview">
      <span class="wplan-day-label">${dayLabel}</span>
      <span class="wplan-meal-type">${e.meal_type}</span>
      <span class="wplan-recipe-name">${e.recipe_name || e.recipe_slug}</span>
    </div>`;
  }).join('');
}

async function acceptWeekPlan() {
  if (!_wplanPlan.length) return;
  const btn = document.getElementById('wplan-accept-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const result = await apiPost('/api/mealplan/batch', { slots: _wplanPlan.map(e => ({
      date: e.date, meal_type: e.meal_type, recipe_slug: e.recipe_slug
    })) });
    closeWeekPlanModal();
    loadPlanner();
    toast(result.failed ? `Week plan partly added · ${result.failed} failed` : 'Week plan added to planner', result.failed ? 'err' : 'ok');
  } catch(e) {
    toast(e.message || 'Could not save plan', 'err');
  } finally {
    btn.disabled = false; btn.textContent = 'Accept Plan';
  }
}

/* ── Meal plan templates ── */
async function saveWeekTemplate() {
  const name = prompt('Template name:');
  if (!name || !name.trim()) return;
  // Collect current week slots from planData
  const slots = [];
  for (const [dateStr, dayData] of Object.entries(planData)) {
    for (const [meal, entries] of Object.entries(dayData)) {
      for (const e of entries) {
        slots.push({ date_offset: _dateOffset(dateStr), meal_type: meal, recipe_slug: e.recipe_slug, recipe_name: e.recipe_name || e.recipe_slug });
      }
    }
  }
  if (!slots.length) { toast('No recipes in this week to save', 'err'); return; }
  try {
    await apiPost('/api/mealplan/templates', { name: name.trim(), slots });
    toast('Template saved', 'ok');
    loadTemplates();
    document.getElementById('templates-panel').style.display = '';
  } catch(e) { toast(e.message, 'err'); }
}

function _dateOffset(dateStr) {
  const _wb = mondayOf(new Date()); _wb.setDate(_wb.getDate()+weekOffset*7); const start = new Date(isoDate(_wb) + 'T00:00:00');
  const d = new Date(dateStr + 'T00:00:00');
  return Math.round((d - start) / 86400000);
}

async function loadTemplates() {
  try {
    const templates = await apiGet('/api/mealplan/templates');
    renderTemplates(templates);
    if (templates.length) document.getElementById('templates-panel').style.display = '';
  } catch(e) { /* silent */ }
}

function renderTemplates(templates) {
  const list = document.getElementById('templates-list');
  if (!list) return;
  if (!templates.length) {
    list.innerHTML = '<div style="font-size:12px;color:var(--text-muted);font-style:italic;padding:8px 0">No saved templates.</div>';
    return;
  }
  list.innerHTML = templates.map(t => {
    const slots = typeof t.slots === 'string' ? JSON.parse(t.slots) : (t.slots || []);
    return `<div class="template-row">
      <span class="template-name">${t.name}</span>
      <span class="template-meta">${slots.length} meal${slots.length===1?'':'s'}</span>
      <button class="btn btn-ghost btn-xs" onclick="applyTemplate(${t.id})">Load</button>
      <button class="btn btn-xs" style="color:#c05040;border-color:transparent" onclick="deleteTemplate(${t.id})">Delete</button>
    </div>`;
  }).join('');
}

async function applyTemplate(id) {
  if (!confirm('Load this template into the current week? Existing entries will not be removed.')) return;
  try {
    const templates = await apiGet('/api/mealplan/templates');
    const tmpl = templates.find(t => t.id === id);
    if (!tmpl) { toast('Template not found', 'err'); return; }
    const slots = typeof tmpl.slots === 'string' ? JSON.parse(tmpl.slots) : (tmpl.slots || []);
    const _wb = mondayOf(new Date()); _wb.setDate(_wb.getDate()+weekOffset*7); const start = new Date(isoDate(_wb) + 'T00:00:00');
    const slotsToAdd = slots.map(s => {
      const d = new Date(start.getTime() + s.date_offset * 86400000);
      const dateStr = d.toISOString().slice(0,10);
      return { date: dateStr, meal_type: s.meal_type, recipe_slug: s.recipe_slug };
    });
    const result = await apiPost('/api/mealplan/batch', { slots: slotsToAdd });
    loadPlanner();
    toast(result.failed ? `Template partly loaded · ${result.failed} failed` : 'Template loaded', result.failed ? 'err' : 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function deleteTemplate(id) {
  try {
    await apiDel(`/api/mealplan/templates/${id}`);
    toast('Template deleted', 'ok');
    loadTemplates();
  } catch(e) { toast(e.message, 'err'); }
}

function toggleTemplatesPanel() {
  const list = document.getElementById('templates-list');
  if (list) list.style.display = list.style.display === 'none' ? '' : 'none';
}

/* ── Generate with AI ── */
async function checkAiKey() {
  try {
    const s = await apiGet('/api/settings');
    const banner = document.getElementById('ai-no-key-banner');
    if (banner) banner.style.display = s.ppq_api_key ? 'none' : 'flex';
  } catch(e) {}
}

function setP(el) { document.getElementById('gen-prompt').value = el.textContent; }

const GEN_PHASES = [
  { msg: 'Thinking about your recipe…',      delay: 0    },
  { msg: 'Writing ingredients…',             delay: 5000 },
  { msg: 'Crafting the instructions…',       delay: 10000 },
  { msg: 'Adding finishing touches…',        delay: 16000 },
  { msg: 'Generating recipe image…',         delay: 22000 },
  { msg: 'Almost ready…',                    delay: 30000 },
];

let _genPhaseTimer = null;
let _advOpen = false;
let _advServings = 4;

function toggleAdvanced() {
  _advOpen = !_advOpen;
  document.getElementById('adv-panel').classList.toggle('open', _advOpen);
  document.getElementById('adv-toggle-btn').classList.toggle('open', _advOpen);
}

function adjServings(delta) {
  _advServings = Math.min(12, Math.max(1, _advServings + delta));
  document.getElementById('adv-servings').textContent = _advServings;
}

function selectOptChip(el, group) {
  document.querySelectorAll(`.opt-chip[data-group="${group}"]`).forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
}

async function togglePantryPicker() {
  const on = document.getElementById('adv-pantry-toggle').checked;
  const wrap = document.getElementById('adv-pantry-chips');
  if (!on) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'flex';
  wrap.innerHTML = '<span style="font-size:12px;color:var(--text-muted)">Loading pantry…</span>';
  try {
    const items = await apiGet('/api/pantry');
    if (!items.length) {
      wrap.innerHTML = '<span style="font-size:12px;color:var(--text-muted)">Your pantry is empty. Add items in the Pantry tab.</span>';
      return;
    }
    wrap.innerHTML = items.map(i =>
      `<div class="opt-chip multi" onclick="this.classList.toggle('selected')">${i.food}</div>`
    ).join('');
  } catch {
    wrap.innerHTML = '<span style="font-size:12px;color:var(--text-muted)">Could not load pantry.</span>';
  }
}

function buildEnhancedPrompt(base) {
  if (!_advOpen) return base;
  const parts = [base, `Make it for ${_advServings} servings.`];
  const ct = document.querySelector('.opt-chip[data-group="cooktime"].selected');
  if (ct && ct.textContent !== 'Any') parts.push(`Cook time should be ${ct.textContent}.`);
  const diff = document.querySelector('.opt-chip[data-group="diff"].selected');
  if (diff && diff.textContent !== 'Any') parts.push(`Difficulty level: ${diff.textContent}.`);
  const protein = document.querySelector('.opt-chip[data-group="protein"].selected');
  if (protein && protein.textContent !== 'Any') parts.push(`Main protein: ${protein.textContent}.`);
  const dietary = [...document.querySelectorAll('#adv-panel .opt-chip.multi.selected')]
    .filter(c => !c.closest('#adv-pantry-chips'))
    .map(c => c.textContent);
  if (dietary.length) parts.push(`Dietary requirements: ${dietary.join(', ')}.`);
  if (document.getElementById('adv-pantry-toggle').checked) {
    const pantryPicks = [...document.querySelectorAll('#adv-pantry-chips .opt-chip.selected')].map(c => c.textContent);
    if (pantryPicks.length) parts.push(`Try to incorporate these pantry ingredients: ${pantryPicks.join(', ')}.`);
  }
  return parts.join(' ');
}

function _startRobot() {
  const loader = document.getElementById('gen-loader');
  const msgEl  = document.getElementById('gen-status-msg');
  loader.classList.add('active');
  let i = 0;
  function nextPhase() {
    if (i >= GEN_PHASES.length) return;
    const phase = GEN_PHASES[i++];
    msgEl.style.animation = 'none';
    msgEl.offsetHeight; // reflow to restart animation
    msgEl.style.animation = '';
    msgEl.textContent = phase.msg;
    const next = GEN_PHASES[i];
    if (next) _genPhaseTimer = setTimeout(nextPhase, next.delay - phase.delay);
  }
  nextPhase();
}

function _stopRobot() {
  clearTimeout(_genPhaseTimer);
  document.getElementById('gen-loader').classList.remove('active');
}

function _findDuplicateRecipes(text) {
  if (!text || !recipesData.length) return [];
  const q = text.toLowerCase().trim();
  return recipesData.filter(r => {
    const name = (r.name || '').toLowerCase();
    return name.includes(q) || q.includes(name);
  });
}

async function generateRecipe() {
  const rawPrompt = document.getElementById('gen-prompt').value.trim();
  if (!rawPrompt && !_advOpen) { toast('Describe a recipe or open Advanced options', 'err'); return; }
  const base = rawPrompt || 'Create a recipe';

  // check for duplicate recipes before calling AI
  const res = document.getElementById('gen-result');
  if (rawPrompt && !generateRecipe._confirmed) {
    const dupes = _findDuplicateRecipes(rawPrompt);
    if (dupes.length) {
      const names = dupes.slice(0, 3).map(r => r.name).join(', ');
      const extra = dupes.length > 3 ? ` and ${dupes.length - 3} more` : '';
      res.style.display = 'block';
      res.innerHTML = `
        <div style="background:#fff8ee;border:1px solid #f0d9a0;border-radius:8px;padding:14px 16px">
          <div style="font-size:13px;color:var(--brown-dark);margin-bottom:10px">
            You already have <strong>${names}${extra}</strong> — generate anyway?
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary btn-xs" onclick="generateRecipe._confirmed=true;generateRecipe()">Continue</button>
            <button class="btn btn-ghost btn-xs" onclick="generateRecipe._confirmed=false;document.getElementById('gen-result').style.display='none'">Cancel</button>
          </div>
        </div>`;
      return;
    }
  }
  generateRecipe._confirmed = false;

  const prompt = buildEnhancedPrompt(base);
  const btn = document.getElementById('gen-btn');
  btn.disabled = true;
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg> Generating…';
  res.style.display = 'none'; res.innerHTML = '';
  _startRobot();
  try {
    const recipe = await apiPost('/api/ai/generate', { prompt });
    const stageData = await apiGet('/api/recipes?status=staged&per_page=1');
    updateStageBadge(stageData.total || 0);
    res.style.display = 'block';
    res.innerHTML = `
      <div style="font-family:'Cormorant Garamond',serif;font-size:18px;font-weight:600;color:var(--brown-dark);margin-bottom:4px">${recipe.name}</div>
      <div style="font-size:12px;color:var(--text-muted);font-style:italic;margin-bottom:11px">${recipe.description||'Saved to Staging for review.'}</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button class="btn btn-ghost btn-xs" onclick="switchTab('recipes');switchSubTab('recipes','staging')">View in Staging →</button>
        <button class="regen-btn" onclick="generateRecipe()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-5"/></svg>
          Regenerate
        </button>
      </div>`;
    toast('Recipe → Staging', 'ok');
  } catch(e) {
    res.style.display = 'block';
    res.innerHTML = `<div style="color:#c05040;font-size:13px">${e.message}</div>`;
    toast(e.message, 'err');
  }
  _stopRobot();
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg> Generate Recipe';
  btn.disabled = false;
}

/* ── Image Import ── */
let _selectedImages = []; // [{file, dataUrl}]

function handleImageSelect(files) {
  if (files && files.length) _addImageFiles(Array.from(files));
}

function handleImageDrop(files) {
  if (files && files.length) _addImageFiles(Array.from(files));
}

function _addImageFiles(files) {
  const allowed = ['image/jpeg','image/png','image/webp','image/gif'];
  files.filter(f => allowed.includes(f.type)).forEach(file => {
    if (_selectedImages.length >= 8) { toast('Maximum 8 images', 'err'); return; }
    const reader = new FileReader();
    reader.onload = e => {
      _selectedImages.push({ file, dataUrl: e.target.result });
      _renderThumbs();
    };
    reader.readAsDataURL(file);
  });
}

function _renderThumbs() {
  const strip = document.getElementById('img-thumb-strip');
  const content = document.getElementById('img-drop-content');
  const btn = document.getElementById('add-modal-btn');
  const label = document.getElementById('img-count-label');
  const n = _selectedImages.length;

  if (!n) {
    strip.style.display = 'none';
    content.style.display = 'block';
    if (btn) btn.disabled = true;
    if (label) label.textContent = '';
    return;
  }

  content.style.display = 'none';
  strip.style.display = 'flex';
  strip.innerHTML = _selectedImages.map((img, i) => `
    <div class="img-thumb-item">
      <img src="${img.dataUrl}" alt="Image ${i+1}">
      <button class="img-thumb-remove" onclick="event.stopPropagation();removeImage(${i})" title="Remove">✕</button>
    </div>`).join('') + (n < 8 ? `
    <button class="img-add-more" onclick="document.getElementById('img-file-input').click()" title="Add more images">+</button>` : '');

  if (btn) btn.disabled = false;
  if (label) label.textContent = n === 1 ? '1 image selected' : `${n} images — AI will combine them into one recipe`;
}

function removeImage(index) {
  _selectedImages.splice(index, 1);
  _renderThumbs();
}

function clearImageSelection() {
  _selectedImages = [];
  document.getElementById('img-file-input').value = '';
  document.getElementById('img-import-result').innerHTML = '';
  _renderThumbs();
}

async function importFromImage() {
  if (!_selectedImages.length) { toast('Select at least one image', 'err'); return; }
  const btn = document.getElementById('add-modal-btn');
  const result = document.getElementById('img-import-result');
  const n = _selectedImages.length;
  if (btn) { btn.disabled = true; btn.textContent = 'Extracting…'; }
  result.innerHTML = '';
  const formData = new FormData();
  _selectedImages.forEach(img => formData.append('images', img.file));
  try {
    const resp = await fetch('/api/import/camera', { method: 'POST', body: formData });
    if (!resp.ok) { const e = await resp.json().catch(() => ({error: resp.statusText})); throw new Error(e.error || resp.statusText); }
    const recipe = await resp.json();
    result.innerHTML = `<div style="background:var(--amber-pale);border:1px solid var(--amber-soft);border-radius:var(--radius-sm);padding:11px 14px;font-size:13px;color:var(--text-mid)">
      <strong style="color:var(--brown-dark);display:block;margin-bottom:2px">${recipe.name}</strong>
      ${n > 1 ? `Extracted from ${n} images. ` : ''}Saved to Staging for review. <span style="cursor:pointer;color:var(--amber);text-decoration:underline" onclick="switchTab('recipes');switchSubTab('recipes','staging');closeAddModal()">View in Staging →</span>
    </div>`;
    const stageData = await apiGet('/api/recipes?status=staged&per_page=1');
    updateStageBadge(stageData.total || 0);
    clearImageSelection();
    toast('Recipe → Staging', 'ok');
  } catch(e) {
    result.innerHTML = `<div style="color:#c05040;font-size:13px;padding:8px 0">${e.message}</div>`;
    toast(e.message, 'err');
  }
  if (btn) { btn.disabled = false; btn.textContent = 'Extract Recipe'; }
}

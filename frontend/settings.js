/* ── Settings ── */
async function loadSettings() {
  try {
    const s = await apiGet('/api/settings');
    document.getElementById('s-ppq-key').value           = s.ppq_api_key      || '';
    document.getElementById('s-ppq-credit-id').value     = s.ppq_credit_id    || '';
    document.getElementById('s-ppq-url').value            = s.ppq_base_url     || 'https://api.ppq.ai/v1';
    document.getElementById('s-ppq-model').value          = s.ppq_model        || '';
    document.getElementById('s-ppq-image-model').value    = s.ppq_image_model  || '';
    document.getElementById('s-ppq-vision-model').value   = s.ppq_vision_model || '';
    const detailSel = document.getElementById('s-ai-vision-detail');
    if (detailSel) detailSel.value = s.ai_vision_detail || 'low';
    const genImages = document.getElementById('s-generate-images');
    if (genImages) genImages.checked = s.generate_images_by_default !== false;
    _setAiStatusBadge(s.ppq_api_key ? 'unchecked' : 'none');
    if (s.ppq_credit_id) _fetchBalance();
    _loadEquipmentChips(s.equipment || '');
    // Dark mode toggle state (reflects current theme, not server setting)
    const dmCb = document.getElementById('s-dark-mode');
    if (dmCb) dmCb.checked = document.documentElement.getAttribute('data-theme') === 'dark';
    // RSS auto-fetch
    const autoFetchSel = document.getElementById('rss-auto-fetch');
    if (autoFetchSel && s.rss_auto_fetch_hours != null) autoFetchSel.value = String(s.rss_auto_fetch_hours);
    // Preferred units
    const prefUnits = document.getElementById('s-preferred-units');
    if (prefUnits) prefUnits.value = s.preferred_units || '';
  } catch(e) { toast('Could not load settings', 'err'); }
  loadConnections();
}

function _setAiStatusBadge(state, model) {
  const badge = document.getElementById('ai-status-badge');
  const banner = document.getElementById('ai-no-key-banner');
  if (state === 'none') {
    badge.style.display = 'inline-block';
    badge.textContent = 'No key set';
    badge.style.background = '#fde8e8'; badge.style.color = '#c05040';
    if (banner) banner.style.display = 'flex';
  } else if (state === 'ok') {
    badge.style.display = 'inline-block';
    badge.textContent = `Connected · ${model || ''}`;
    badge.style.background = '#e8f5e9'; badge.style.color = '#3a6a40';
    if (banner) banner.style.display = 'none';
  } else if (state === 'err') {
    badge.style.display = 'inline-block';
    badge.textContent = 'Connection failed';
    badge.style.background = '#fde8e8'; badge.style.color = '#c05040';
    if (banner) banner.style.display = 'flex';
  } else {
    // unchecked — key is set but not tested yet
    badge.style.display = 'inline-block';
    badge.textContent = 'Key saved';
    badge.style.background = '#fff4e0'; badge.style.color = '#9a6010';
    if (banner) banner.style.display = 'none';
  }
}

async function _fetchBalance() {
  const el = document.getElementById('ai-balance');
  const topupBtn = document.getElementById('topup-btn');
  try {
    const r = await apiGet('/api/ai/balance');
    if (r.ok) {
      el.textContent = `Balance: $${r.balance.toFixed(2)}`;
      el.style.display = '';
      el.style.color = r.balance < 1 ? '#c05040' : 'var(--text-mid)';
      if (topupBtn) topupBtn.style.display = '';
    } else { el.style.display = 'none'; if (topupBtn) topupBtn.style.display = 'none'; }
  } catch { el.style.display = 'none'; if (topupBtn) topupBtn.style.display = 'none'; }
}

async function testAiConnection() {
  const btn = document.getElementById('ai-test-btn');
  btn.disabled = true; btn.textContent = 'Testing…';
  try {
    const r = await apiGet('/api/ai/test');
    const modelLabel = r.ok ? `${r.recipe_model} · ${r.image_model} · ${r.vision_model}` : '';
    _setAiStatusBadge(r.ok ? 'ok' : 'err', modelLabel);
    toast(r.ok ? `Connected · ${r.recipe_model} / ${r.image_model} / ${r.vision_model}` : r.error, r.ok ? 'ok' : 'err');
  } catch(e) {
    _setAiStatusBadge('err');
    toast('Connection test failed', 'err');
  }
  btn.disabled = false; btn.textContent = 'Test Connection';
}

/* ── Top-Up Modal ── */
let _topupState = { method: 'btc-lightning', invoiceId: null, pollTimer: null, countdownTimer: null };

function openTopup() {
  _topupState = { method: 'xmr', invoiceId: null, pollTimer: null, countdownTimer: null };
  document.getElementById('topup-step1').style.display = '';
  document.getElementById('topup-step2').style.display = 'none';
  document.getElementById('topup-amount').value = '';
  document.getElementById('topup-err').style.display = 'none';
  document.getElementById('topup-overlay').classList.add('open');
  document.getElementById('topup-modal').classList.add('open');
}

function closeTopup() {
  document.getElementById('topup-overlay').classList.remove('open');
  document.getElementById('topup-modal').classList.remove('open');
  document.getElementById('topup-iframe').src = '';
  if (_topupState.pollTimer) clearInterval(_topupState.pollTimer);
  if (_topupState.countdownTimer) clearInterval(_topupState.countdownTimer);
}

function _topupAmount(val) {
  document.getElementById('topup-amount').value = val;
  document.querySelectorAll('#topup-step1 .opt-chip').forEach(c => {
    if (c.textContent.trim() === `$${val}`) c.classList.add('selected');
    else if (c.textContent.trim().startsWith('$') && c.textContent.trim().match(/^\$\d+$/)) c.classList.remove('selected');
  });
}

async function createTopup() {
  const amount = parseFloat(document.getElementById('topup-amount').value);
  const errEl = document.getElementById('topup-err');
  if (!amount || isNaN(amount)) { errEl.textContent = 'Enter an amount'; errEl.style.display = ''; return; }
  if (amount < 5 || amount > 10000) { errEl.textContent = 'Amount must be $5-$10,000'; errEl.style.display = ''; return; }
  errEl.style.display = 'none';

  const btn = document.getElementById('topup-create-btn');
  btn.disabled = true; btn.textContent = 'Creating…';
  try {
    const r = await apiPost('/api/ai/topup', { method: 'xmr', amount, currency: 'USD' });
    if (!r.ok) { errEl.textContent = r.error || 'Failed to create invoice'; errEl.style.display = ''; return; }
    _topupState.invoiceId = r.invoice_id;

    // Load checkout page in iframe
    document.getElementById('topup-step1').style.display = 'none';
    document.getElementById('topup-step2').style.display = '';
    if (r.checkout_url) document.getElementById('topup-iframe').src = r.checkout_url;
    document.getElementById('topup-pay-amount').textContent = `$${amount.toFixed(2)}`;
    document.getElementById('topup-pay-status').textContent = 'Waiting for payment…';
    document.getElementById('topup-pay-status').style.color = 'var(--text-mid)';

    // Countdown timer
    const expiresAt = r.expires_at * 1000;
    _topupState.countdownTimer = setInterval(() => {
      const remaining = Math.max(0, expiresAt - Date.now());
      const mins = Math.floor(remaining / 60000);
      const secs = Math.floor((remaining % 60000) / 1000);
      const timerEl = document.getElementById('topup-timer');
      timerEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
      timerEl.style.color = remaining < 120000 ? '#c05040' : 'var(--brown-dark)';
      if (remaining <= 0) {
        clearInterval(_topupState.countdownTimer);
        clearInterval(_topupState.pollTimer);
        document.getElementById('topup-pay-status').textContent = 'Expired';
        document.getElementById('topup-pay-status').style.color = '#c05040';
      }
    }, 1000);

    // Poll status
    _topupState.pollTimer = setInterval(async () => {
      try {
        const st = await apiGet(`/api/ai/topup/status/${_topupState.invoiceId}`);
        if (st.status === 'Settled' || st.status === 'Complete') {
          clearInterval(_topupState.pollTimer);
          clearInterval(_topupState.countdownTimer);
          document.getElementById('topup-pay-status').textContent = 'Paid';
          document.getElementById('topup-pay-status').style.color = '#3a6a40';
          toast('Payment received — balance updated', 'ok');
          _fetchBalance();
          setTimeout(closeTopup, 1500);
        } else if (st.status === 'Expired' || st.status === 'Invalid') {
          clearInterval(_topupState.pollTimer);
          clearInterval(_topupState.countdownTimer);
          document.getElementById('topup-pay-status').textContent = st.status;
          document.getElementById('topup-pay-status').style.color = '#c05040';
        }
      } catch {}
    }, 5000);
  } catch(e) {
    errEl.textContent = e.message || 'Failed to create invoice';
    errEl.style.display = '';
  } finally {
    btn.disabled = false; btn.textContent = 'Create Invoice';
  }
}

function _topupBack() {
  if (_topupState.pollTimer) clearInterval(_topupState.pollTimer);
  if (_topupState.countdownTimer) clearInterval(_topupState.countdownTimer);
  document.getElementById('topup-iframe').src = '';
  document.getElementById('topup-step1').style.display = '';
  document.getElementById('topup-step2').style.display = 'none';
}

/* ── Equipment chips ── */
const PRESET_EQUIPMENT = ['Dutch oven','Cast iron skillet','Pressure cooker','Slow cooker','Instant Pot','Air fryer','Wok','Stand mixer','Food processor','Blender','Sous vide','Steamer','Grill','Mandoline'];

function _loadEquipmentChips(saved) {
  const items = saved.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  // Mark preset chips
  document.querySelectorAll('#equip-chips .opt-chip').forEach(chip => {
    chip.classList.toggle('selected', items.includes(chip.textContent.trim().toLowerCase()));
  });
  // Render custom chips (items not in preset list)
  const presetLower = PRESET_EQUIPMENT.map(s => s.toLowerCase());
  const customs = items.filter(i => !presetLower.includes(i));
  const container = document.getElementById('equip-custom-chips');
  container.innerHTML = customs.map(c => _customEquipChip(c)).join('');
}

function _readEquipmentChips() {
  const selected = [];
  document.querySelectorAll('#equip-chips .opt-chip.selected').forEach(c => selected.push(c.textContent.trim()));
  document.querySelectorAll('#equip-custom-chips .equip-custom-chip').forEach(c => selected.push(c.dataset.value));
  return selected.join(', ');
}

function _customEquipChip(value) {
  return `<span class="equip-custom-chip opt-chip selected" data-value="${value}" style="cursor:default">
    ${value}
    <span onclick="this.parentElement.remove()" style="margin-left:5px;cursor:pointer;opacity:.6;font-size:11px">✕</span>
  </span>`;
}

function addCustomEquipment() {
  const input = document.getElementById('equip-custom-input');
  const val = input.value.trim();
  if (!val) return;
  // Don't add if already a preset
  const presetLower = PRESET_EQUIPMENT.map(s => s.toLowerCase());
  if (presetLower.includes(val.toLowerCase())) {
    // Just select the preset chip instead
    document.querySelectorAll('#equip-chips .opt-chip').forEach(c => {
      if (c.textContent.trim().toLowerCase() === val.toLowerCase()) c.classList.add('selected');
    });
  } else {
    // Check not already added as custom
    const exists = [...document.querySelectorAll('#equip-custom-chips .equip-custom-chip')]
      .some(c => c.dataset.value.toLowerCase() === val.toLowerCase());
    if (!exists) {
      document.getElementById('equip-custom-chips').insertAdjacentHTML('beforeend', _customEquipChip(val));
    }
  }
  input.value = '';
}

async function saveSettings() {
  // Preserve existing rss_feeds — managed in RSS tab, not here
  const existing = await apiGet('/api/settings').catch(() => ({}));
  const body = {
    ppq_api_key:      document.getElementById('s-ppq-key').value,
    ppq_credit_id:    document.getElementById('s-ppq-credit-id').value,
    ppq_base_url:     document.getElementById('s-ppq-url').value,
    ppq_model:        document.getElementById('s-ppq-model').value,
    ppq_image_model:  document.getElementById('s-ppq-image-model').value,
    ppq_vision_model: document.getElementById('s-ppq-vision-model').value,
    ai_vision_detail: document.getElementById('s-ai-vision-detail')?.value || 'low',
    generate_images_by_default: document.getElementById('s-generate-images')?.checked ? 'true' : 'false',
    rss_feeds:        existing.rss_feeds || '',
    equipment:        _readEquipmentChips(),
    preferred_units:  document.getElementById('s-preferred-units').value,
  };
  try {
    await apiPost('/api/settings', body);
    toast('Settings saved', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function syncRecipes() {
  try {
    const r = await apiPost('/api/recipes/sync');
    toast(`Synced ${r.synced} recipe${r.synced===1?'':'s'}`, 'ok');
    if (currentTab === 'recipes') _loadSubContent('recipes', _activeSubTab('recipes'));
  } catch(e) { toast(e.message, 'err'); }
}

function downloadBackup() {
  const a = document.createElement('a');
  a.href = '/api/backup';
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast('Backup downloading...', 'ok');
}

async function restoreBackup(input) {
  const file = input.files[0];
  if (!file) return;
  if (!confirm('This will overwrite existing recipes and settings with the backup contents. Continue?')) {
    input.value = '';
    return;
  }
  const status = document.getElementById('backup-status');
  status.style.display = 'block';
  status.textContent = 'Restoring backup...';
  const form = new FormData();
  form.append('backup', file);
  try {
    const resp = await fetch('/api/backup/restore', { method: 'POST', body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Restore failed');
    status.textContent = `Restored ${data.recipes} recipe${data.recipes===1?'':'s'} and ${data.images} image${data.images===1?'':'s'}`;
    toast('Backup restored', 'ok');
    loadSettings();
    if (currentTab === 'recipes') _loadSubContent('recipes', _activeSubTab('recipes'));
  } catch(e) {
    status.textContent = '';
    status.style.display = 'none';
    toast(e.message, 'err');
  }
  input.value = '';
}

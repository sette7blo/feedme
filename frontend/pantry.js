/* ── Pantry ── */
async function loadPantry() {
  try {
    const data = await apiGet('/api/pantry');
    renderPantry(data);
  } catch(e) { toast(e.message, 'err'); }
}

function renderPantry(items) {
  document.getElementById('pantry-tbody').innerHTML = (items||[]).map(p => `
    <tr>
      <td>${p.food}</td>
      <td>${p.quantity != null ? p.quantity : ''}</td>
      <td>${p.unit||''}</td>
      <td><button class="btn btn-ghost" style="padding:3px 9px;font-size:11px" onclick="deletePantryItem(${p.id})">✕</button></td>
    </tr>`).join('');
}

async function addPantryItem() {
  const food = document.getElementById('p-food').value.trim();
  if (!food) { toast('Enter a food name', 'err'); return; }
  const qty  = parseFloat(document.getElementById('p-qty').value) || null;
  const unit = document.getElementById('p-unit').value.trim() || null;
  try {
    await apiPost('/api/pantry', { food, quantity: qty, unit });
    document.getElementById('p-food').value = '';
    document.getElementById('p-qty').value  = '';
    document.getElementById('p-unit').value = '';
    await loadPantry();
    toast('Item added', 'ok');
  } catch(e) { toast(e.message, 'err'); }
}

async function deletePantryItem(id) {
  try {
    await apiDel(`/api/pantry/${id}`);
    await loadPantry();
  } catch(e) { toast(e.message, 'err'); }
}

/* ── Barcode scanner ── */
let _scanner = null;
let _scannerStarted = false;
let _scanResult = null;
let _scanLibsLoaded = false;

function _loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load ' + src));
    document.head.appendChild(s);
  });
}

async function _ensureScanLibs() {
  if (_scanLibsLoaded) return;
  await _loadScript('https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js');
  await _loadScript('https://cdn.jsdelivr.net/npm/@ericblade/quagga2@1.8.4/dist/quagga.min.js');
  _scanLibsLoaded = true;
}

async function openScannerModal() {
  _scanResult = null;
  _scannerStarted = false;
  document.getElementById('scan-result').classList.remove('visible');
  document.getElementById('scan-result').textContent = '';
  document.getElementById('scan-use-btn').style.display = 'none';
  document.getElementById('scan-status').textContent = _scanLibsLoaded ? 'Point your camera at a barcode' : 'Loading scanner…';
  document.getElementById('scan-overlay').classList.add('open');
  document.getElementById('scan-modal').classList.add('open');
  const fileInput = document.getElementById('scan-file-input');
  fileInput.value = '';
  fileInput.onchange = () => scanFromFile(fileInput);

  try {
    await _ensureScanLibs();
  } catch(e) {
    document.getElementById('scan-status').textContent = 'Failed to load scanner library';
    return;
  }
  document.getElementById('scan-status').textContent = 'Point your camera at a barcode';

  _scanner = new Html5Qrcode('scan-reader');
  _scanner.start(
    { facingMode: 'environment' },
    { fps: 10, qrbox: { width: 260, height: 120 } },
    _onBarcodeDetected,
    () => {}
  ).then(() => {
    _scannerStarted = true;
  }).catch(() => {
    document.getElementById('scan-status').textContent = 'Camera access denied or not available';
    _scanner.clear();
    _scanner = null;
  });
}

function closeScannerModal() {
  document.getElementById('scan-overlay').classList.remove('open');
  document.getElementById('scan-modal').classList.remove('open');
  if (_scanner && _scannerStarted) {
    _scanner.stop().catch(() => {}).finally(() => { _scanner.clear(); _scanner = null; _scannerStarted = false; });
  } else {
    _scanner = null;
    _scannerStarted = false;
  }
}

async function scanFromFile(input) {
  const file = input.files[0];
  if (!file) return;
  input.value = '';
  document.getElementById('scan-status').textContent = 'Reading barcode…';
  document.getElementById('scan-result').classList.remove('visible');
  document.getElementById('scan-use-btn').style.display = 'none';
  _scanResult = null;
  let tmp = document.getElementById('_scan_file_tmp');
  if (!tmp) { tmp = document.createElement('div'); tmp.id = '_scan_file_tmp'; tmp.style.display = 'none'; document.body.appendChild(tmp); }
  try {
    await _ensureScanLibs();
    document.getElementById('scan-status').textContent = 'Scanning (' + Math.round(file.size/1024) + 'KB, ' + file.type + ')…';
    const objectUrl = URL.createObjectURL(file);
    const barcode = await new Promise((resolve, reject) => {
      Quagga.decodeSingle({
        src: objectUrl,
        numOfWorkers: 0,
        locate: true,
        inputStream: { size: 800 },
        decoder: { readers: ['ean_reader','ean_8_reader','upc_reader','upc_e_reader','code_128_reader','code_39_reader'] }
      }, result => {
        URL.revokeObjectURL(objectUrl);
        if (result && result.codeResult) resolve(result.codeResult.code);
        else reject(new Error('No barcode detected'));
      });
    });
    await _onBarcodeDetected(barcode);
  } catch(e) {
    document.getElementById('scan-status').textContent = 'Error: ' + (e?.message || String(e));
  }
}

async function _onBarcodeDetected(barcode) {
  if (_scanResult) return; // already got one
  _scanResult = barcode;
  document.getElementById('scan-status').textContent = 'Looking up product…';
  if (_scanner) _scanner.pause();

  try {
    const r = await fetch(`https://world.openfoodfacts.org/api/v0/product/${encodeURIComponent(barcode)}.json`);
    const d = await r.json();
    if (d.status === 1 && d.product) {
      const name = d.product.product_name || d.product.product_name_en || '';
      if (name) {
        let qty = null, unit = null;
        const rawQty = d.product.quantity || '';
        const m = rawQty.match(/^(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)/);
        if (m) { qty = parseFloat(m[1].replace(',', '.')); unit = m[2].toLowerCase(); }
        _scanResult = { barcode, name, qty, unit };
        const el = document.getElementById('scan-result');
        el.textContent = name + (rawQty ? ' — ' + rawQty : '');
        el.classList.add('visible');
        document.getElementById('scan-use-btn').style.display = '';
        document.getElementById('scan-status').textContent = 'Product found';
      } else {
        document.getElementById('scan-status').textContent = 'Product found but name is missing — enter manually';
        _scanResult = null;
        if (_scanner) _scanner.resume();
      }
    } else {
      document.getElementById('scan-status').textContent = 'Product not found in database — enter manually';
      _scanResult = null;
      if (_scanner) _scanner.resume();
    }
  } catch(e) {
    document.getElementById('scan-status').textContent = 'Lookup failed — check connection';
    _scanResult = null;
    if (_scanner) _scanner.resume();
  }
}

function useScanResult() {
  if (_scanResult && _scanResult.name) {
    document.getElementById('p-food').value = _scanResult.name;
    if (_scanResult.qty)  document.getElementById('p-qty').value  = _scanResult.qty;
    if (_scanResult.unit) document.getElementById('p-unit').value = _scanResult.unit;
    document.getElementById('p-food').focus();
  }
  closeScannerModal();
}

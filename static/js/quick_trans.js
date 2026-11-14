/**
 * AL-CIVIL WMS - Mode Transaksi Cepat (POS-Style Fast Transaction Engine)
 * Mendukung Keyboard First & Barcode Scanner
 */

document.addEventListener('DOMContentLoaded', () => {
  // State
  let currentTxType = 'OUT'; // 'OUT' (Barang Keluar / SJ) or 'IN' (Barang Masuk)
  let cart = [];
  let searchResults = [];
  let searchResultsQuery = '';
  let focusedResultIndex = -1;

  // DOM Elements
  const btnTypeOut = document.getElementById('btnTypeOut');
  const btnTypeIn = document.getElementById('btnTypeIn');
  const searchInput = document.getElementById('materialSearchInput');
  const searchDropdown = document.getElementById('searchResultsDropdown');
  const cartTableBody = document.getElementById('cartTableBody');
  const emptyCartState = document.getElementById('emptyCartState');
  const cartTotalQty = document.getElementById('cartTotalQty');
  const cartTotalAmount = document.getElementById('cartTotalAmount');
  const btnSubmitTransaction = document.getElementById('btnSubmitTransaction');
  const projectSelectGroup = document.getElementById('projectSelectGroup');
  const supplierSelectGroup = document.getElementById('supplierSelectGroup');
  const formProject = document.getElementById('formProject');
  const formSupplier = document.getElementById('formSupplier');
  const formVehicle = document.getElementById('formVehicle');
  const formDriver = document.getElementById('formDriver');
  const formOperator = document.getElementById('formOperator');
  const formNotes = document.getElementById('formNotes');

  // Success Modal Elements
  const successModal = document.getElementById('successModal');
  const successTxNumber = document.getElementById('successTxNumber');
  const successPrintBtn = document.getElementById('successPrintBtn');

  // 1. Transaction Type Toggle
  if (btnTypeOut && btnTypeIn) {
    btnTypeOut.addEventListener('click', () => setTransactionType('OUT'));
    btnTypeIn.addEventListener('click', () => setTransactionType('IN'));
  }

  function setTransactionType(type) {
    currentTxType = type;
    if (type === 'OUT') {
      btnTypeOut.className = 'pos-type-btn active outbound';
      btnTypeIn.className = 'pos-type-btn';
      projectSelectGroup.style.display = 'block';
      supplierSelectGroup.style.display = 'none';
      btnSubmitTransaction.innerHTML = `<span>🚀 Proses & Terbitkan Surat Jalan</span> <span class="kbd-badge">F9</span>`;
    } else {
      btnTypeIn.className = 'pos-type-btn active inbound';
      btnTypeOut.className = 'pos-type-btn';
      projectSelectGroup.style.display = 'none';
      supplierSelectGroup.style.display = 'block';
      btnSubmitTransaction.innerHTML = `<span>📥 Proses Penerimaan Material</span> <span class="kbd-badge">F9</span>`;
    }
    renderCart();
  }

  // 2. Live Debounced Search
  let searchTimeout = null;
  if (searchInput) {
    searchInput.focus();

    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      const query = e.target.value.trim();
      if (query.length === 0) {
        hideDropdown();
        return;
      }
      searchTimeout = setTimeout(() => {
        fetchMaterials(query);
      }, 150);
    });

    // Keyboard navigation in search dropdown
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (searchResults.length > 0) {
          focusedResultIndex = Math.min(focusedResultIndex + 1, searchResults.length - 1);
          highlightResultRow();
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (searchResults.length > 0) {
          focusedResultIndex = Math.max(focusedResultIndex - 1, 0);
          highlightResultRow();
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const query = searchInput.value.trim();
        // Hanya percaya hasil dropdown jika benar-benar hasil untuk query saat
        // ini. Ini penting untuk barcode scanner yang mengetik + Enter sangat
        // cepat, agar item dari pencarian sebelumnya tidak salah terpilih.
        const resultsAreCurrent = query !== '' && searchResultsQuery === query;

        if (resultsAreCurrent && focusedResultIndex >= 0 && searchResults[focusedResultIndex]) {
          addToCart(searchResults[focusedResultIndex]);
          clearSearch();
        } else if (resultsAreCurrent && searchResults.length === 1) {
          addToCart(searchResults[0]);
          clearSearch();
        } else if (query !== '') {
          // Direct barcode / exact query
          fetch(`/api/materials/search?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
              if (!data || data.length === 0) {
                showToast(`Material '${query}' tidak ditemukan!`, 'danger');
                return;
              }
              const upperQuery = query.toUpperCase();
              const exact = data.find(i =>
                i.barcode === query || String(i.sku || '').toUpperCase() === upperQuery
              );
              if (exact || data.length === 1) {
                addToCart(exact || data[0]);
                clearSearch();
              } else {
                // Banyak hasil mirip: tampilkan daftar, jangan asal pilih.
                searchResults = data;
                searchResultsQuery = query;
                focusedResultIndex = -1;
                renderDropdown(data);
                showToast('Beberapa material cocok. Pilih salah satu dari daftar.', 'warning');
              }
            })
            .catch(err => showToast(`Gagal mencari material: ${err}`, 'danger'));
        }
      } else if (e.key === 'Escape') {
        clearSearch();
      }
    });
  }

  // Hide dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (searchInput && !searchInput.contains(e.target) && searchDropdown && !searchDropdown.contains(e.target)) {
      hideDropdown();
    }
  });

  function fetchMaterials(q) {
    fetch(`/api/materials/search?q=${encodeURIComponent(q)}`)
      .then(res => res.json())
      .then(data => {
        // Abaikan respons lama yang datang terlambat (out-of-order response).
        if (!searchInput || searchInput.value.trim() !== q) return;
        searchResults = data;
        searchResultsQuery = q;
        focusedResultIndex = -1;
        renderDropdown(data);
      })
      .catch(err => {
        console.error('Error fetching materials:', err);
      });
  }

  function renderDropdown(items) {
    if (!searchDropdown) return;
    if (items.length === 0) {
      searchDropdown.innerHTML = `<div style="padding: 1rem; text-align: center; color: #64748b; font-size: 0.85rem;">Tidak ada material yang sesuai</div>`;
      searchDropdown.style.display = 'block';
      return;
    }

    let html = '';
    items.forEach((item, index) => {
      const stockBadgeClass = item.stock <= item.min_stock ? 'badge-danger' : 'badge-success';
      html += `
        <div class="search-item-row" data-index="${index}" onclick="window.pickSearchedMaterial(${index})">
          <div>
            <div class="search-item-main">${escapeHtml(item.name)}</div>
            <div class="search-item-sub">
              <span>SKU: <b>${escapeHtml(item.sku)}</b></span>
              <span>•</span>
              <span>Lokasi: ${escapeHtml(item.location || '-')}</span>
              <span>•</span>
              <span>Harga: ${formatRupiah(item.unit_price)}</span>
            </div>
          </div>
          <div style="text-align: right;">
            <span class="badge ${stockBadgeClass}">Stok: ${item.stock} ${escapeHtml(item.unit)}</span>
          </div>
        </div>
      `;
    });

    searchDropdown.innerHTML = html;
    searchDropdown.style.display = 'block';
  }

  function highlightResultRow() {
    const rows = searchDropdown.querySelectorAll('.search-item-row');
    rows.forEach((row, i) => {
      if (i === focusedResultIndex) {
        row.classList.add('focused');
        row.scrollIntoView({ block: 'nearest' });
      } else {
        row.classList.remove('focused');
      }
    });
  }

  window.pickSearchedMaterial = function(index) {
    if (searchResults[index]) {
      addToCart(searchResults[index]);
      clearSearch();
    }
  };

  function hideDropdown() {
    if (searchDropdown) {
      searchDropdown.style.display = 'none';
      focusedResultIndex = -1;
    }
  }

  function clearSearch() {
    if (searchInput) {
      searchInput.value = '';
      searchInput.focus();
    }
    searchResults = [];
    searchResultsQuery = '';
    hideDropdown();
  }

  // 3. Popular Tiles Click
  document.querySelectorAll('.popular-card').forEach(card => {
    card.addEventListener('click', () => {
      const matId = card.getAttribute('data-id');
      fetch(`/api/materials/${matId}`)
        .then(res => res.json())
        .then(mat => {
          // Material bisa saja sudah dihapus saat halaman masih terbuka
          if (!mat || mat.error || mat.id === undefined) {
            showToast('Material tidak ditemukan. Muat ulang halaman.', 'danger');
            return;
          }
          addToCart(mat);
        })
        .catch(err => {
          showToast(`Gagal memuat material: ${err}`, 'danger');
        });
    });
  });

  // 4. Cart Management
  function addToCart(material) {
    const existingIndex = cart.findIndex(i => i.material_id === material.id);
    if (existingIndex > -1) {
      // Check stock if OUT
      const newQty = cart[existingIndex].qty + 1;
      if (currentTxType === 'OUT' && newQty > material.stock) {
        showToast(`Stok ${material.name} hanya tersedia ${material.stock} ${material.unit}!`, 'danger');
        return;
      }
      cart[existingIndex].qty = newQty;
    } else {
      if (currentTxType === 'OUT' && material.stock <= 0) {
        showToast(`Stok ${material.name} habis (0 ${material.unit})! Tidak dapat dikeluarkan.`, 'danger');
        return;
      }
      cart.push({
        material_id: material.id,
        sku: material.sku,
        material_name: material.name,
        unit: material.unit,
        stock: material.stock,
        unit_price: material.unit_price,
        qty: 1,
        notes: ''
      });
    }

    showToast(`Ditambahkan: ${material.name}`, 'success');
    renderCart();
  }

  function renderCart() {
    if (!cartTableBody) return;

    if (cart.length === 0) {
      cartTableBody.innerHTML = '';
      if (emptyCartState) emptyCartState.style.display = 'block';
      if (cartTotalQty) cartTotalQty.textContent = '0';
      if (cartTotalAmount) cartTotalAmount.textContent = 'Rp 0';
      return;
    }

    if (emptyCartState) emptyCartState.style.display = 'none';

    let totalQty = 0;
    let totalVal = 0;

    let html = '';
    cart.forEach((item, index) => {
      const lineTotal = item.qty * item.unit_price;
      totalQty += Number(item.qty);
      totalVal += lineTotal;

      const isOverStock = currentTxType === 'OUT' && item.qty > item.stock;

      html += `
        <tr class="cart-row${isOverStock ? ' is-overstock' : ''}">
          <td class="cart-cell-desc">
            <div class="cart-item-name">${escapeHtml(item.material_name)}</div>
            <div class="cart-item-meta">
              SKU: ${escapeHtml(item.sku)} | Sisa Stok: <b>${item.stock} ${escapeHtml(item.unit)}</b>
              ${isOverStock ? '<span class="badge badge-danger" style="margin-left: 6px;">Melebihi Stok!</span>' : ''}
            </div>
            <input type="text" class="form-control form-control-sm cart-item-notes"
                   placeholder="Catatan batch/lot/spesifikasi..." value="${escapeHtml(item.notes || '')}"
                   onchange="window.updateCartItemNotes(${index}, this.value)">
          </td>
          <td class="cart-cell-qty">
            <div class="cart-qty-control">
              <button class="btn btn-outline cart-qty-btn" onclick="window.changeCartQty(${index}, -1)" type="button">-</button>
              <input type="number" min="0.1" step="any" class="form-control cart-qty-input"
                     value="${item.qty}" onchange="window.setCartQty(${index}, this.value)">
              <button class="btn btn-outline cart-qty-btn" onclick="window.changeCartQty(${index}, 1)" type="button">+</button>
            </div>
            <div class="cart-qty-unit">${escapeHtml(item.unit)}</div>
          </td>
          <td class="cart-cell-total">
            ${formatRupiah(lineTotal)}
          </td>
          <td class="cart-cell-action">
            <button class="btn btn-outline cart-remove-btn"
                    onclick="window.removeCartItem(${index})" title="Hapus">
              ✕
            </button>
          </td>
        </tr>
      `;
    });

    cartTableBody.innerHTML = html;
    if (cartTotalQty) cartTotalQty.textContent = totalQty.toLocaleString('id-ID');
    if (cartTotalAmount) cartTotalAmount.textContent = formatRupiah(totalVal);
  }

  // Window functions for cart event handlers
  window.changeCartQty = function(index, delta) {
    if (cart[index]) {
      const newQty = Math.max(1, cart[index].qty + delta);
      if (currentTxType === 'OUT' && newQty > cart[index].stock) {
        showToast(`Stok ${cart[index].material_name} hanya tersedia ${cart[index].stock} ${cart[index].unit}!`, 'danger');
        return;
      }
      cart[index].qty = newQty;
      renderCart();
    }
  };

  window.setCartQty = function(index, val) {
    const qty = parseFloat(val);
    if (!isNaN(qty) && qty > 0 && cart[index]) {
      // BUG-02 FIX: Tambahkan `return` agar qty tidak diupdate saat melebihi stok
      if (currentTxType === 'OUT' && qty > cart[index].stock) {
        showToast(`Stok ${cart[index].material_name} hanya tersedia ${cart[index].stock} ${cart[index].unit}!`, 'danger');
        renderCart(); // Reset tampilan input ke nilai yang valid
        return;
      }
      cart[index].qty = qty;
      renderCart();
    }
  };

  window.updateCartItemNotes = function(index, notes) {
    if (cart[index]) {
      cart[index].notes = notes;
    }
  };

  window.removeCartItem = function(index) {
    if (cart[index]) {
      cart.splice(index, 1);
      renderCart();
      showToast('Item dihapus dari daftar.', 'warning');
    }
  };

  window.clearAllCart = function() {
    if (cart.length > 0 && confirm('Kosongkan daftar transaksi?')) {
      cart = [];
      renderCart();
    }
  };

  // 5. Submit Transaction
  if (btnSubmitTransaction) {
    btnSubmitTransaction.addEventListener('click', processTransaction);
  }

  function processTransaction() {
    if (cart.length === 0) {
      showToast('Pilih minimal 1 material untuk melakukan transaksi!', 'danger');
      if (searchInput) searchInput.focus();
      return;
    }

    // Validation
    let projectName = '';
    let projectId = null;
    let supplierName = '';
    let supplierId = null;

    if (currentTxType === 'OUT') {
      const prjVal = formProject ? formProject.value : '';
      if (!prjVal) {
        showToast('Pilih Proyek Tujuan Pengiriman!', 'danger');
        if (formProject) formProject.focus();
        return;
      }
      const prjOpt = formProject.options[formProject.selectedIndex];
      projectId = prjVal;
      projectName = prjOpt ? prjOpt.text : '';

      // Check stock limit for all items
      for (const item of cart) {
        if (item.qty > item.stock) {
          showToast(`Stok '${item.material_name}' tidak mencukupi (Diminta: ${item.qty}, Tersedia: ${item.stock})!`, 'danger');
          return;
        }
      }
    } else {
      const supVal = formSupplier ? formSupplier.value : '';
      if (!supVal) {
        showToast('Pilih Vendor / Supplier Penerimaan!', 'danger');
        if (formSupplier) formSupplier.focus();
        return;
      }
      const supOpt = formSupplier.options[formSupplier.selectedIndex];
      supplierId = supVal;
      supplierName = supOpt ? supOpt.text : '';
    }

    const payload = {
      type: currentTxType,
      project_id: projectId,
      project_name: projectName,
      supplier_id: supplierId,
      supplier_name: supplierName,
      vehicle_number: formVehicle ? formVehicle.value : '',
      driver_name: formDriver ? formDriver.value : '',
      operator_name: formOperator ? formOperator.value : 'Officer AL-CIVIL',
      notes: formNotes ? formNotes.value : '',
      items: cart
    };

    btnSubmitTransaction.disabled = true;
    btnSubmitTransaction.innerHTML = `<span>⏳ Menyimpan Transaksi...</span>`;

    fetch('/api/transaction/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(data => {
        btnSubmitTransaction.disabled = false;
        setTransactionType(currentTxType);

        if (data.success) {
          showToast(data.message, 'success');
          
          // Clear form & cart
          cart = [];
          renderCart();
          if (formVehicle) formVehicle.value = '';
          if (formDriver) formDriver.value = '';
          if (formNotes) formNotes.value = '';

          // Show Success Modal
          if (successModal) {
            if (successTxNumber) successTxNumber.textContent = data.transaction_number;
            if (successPrintBtn) successPrintBtn.href = data.slip_url;
            successModal.style.display = 'flex';
          } else {
            window.location.href = data.slip_url;
          }
        } else {
          showToast(`Gagal: ${data.message}`, 'danger');
        }
      })
      .catch(err => {
        btnSubmitTransaction.disabled = false;
        setTransactionType(currentTxType);
        showToast(`Terjadi kesalahan jaringan: ${err}`, 'danger');
      });
  }

  // 6. Global Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    // F2: Focus Search
    if (e.key === 'F2') {
      e.preventDefault();
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }
    // F9: Submit Transaction
    else if (e.key === 'F9') {
      e.preventDefault();
      processTransaction();
    }
  });

  // 7. Android Camera Barcode Scanner Engine
  const btnOpenScanner = document.getElementById('btnOpenScanner');
  const btnQuickScanIcon = document.getElementById('btnQuickScanIcon');
  const cameraScannerModal = document.getElementById('cameraScannerModal');
  const btnCloseScanner = document.getElementById('btnCloseScanner');
  const cameraVideo = document.getElementById('cameraVideo');
  const cameraStatusText = document.getElementById('cameraStatusText');
  const btnTorchToggle = document.getElementById('btnTorchToggle');

  let mediaStream = null;
  let scanInterval = null;
  let isScanning = false;
  let barcodeDetector = null;
  let torchTrack = null;
  let torchEnabled = false;

  function playScanBeep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1046, ctx.currentTime);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.12);
    } catch (e) {}
  }

  function triggerScanHaptic() {
    if (navigator.vibrate) {
      try { navigator.vibrate([60, 40, 60]); } catch (e) {}
    }
  }

  async function openCameraScanner() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showToast('Kamera tidak didukung pada browser ini.', 'danger');
      return;
    }

    if (cameraScannerModal) cameraScannerModal.style.display = 'flex';
    if (cameraStatusText) cameraStatusText.textContent = 'Memulai kamera Android...';

    try {
      if ('BarcodeDetector' in window) {
        barcodeDetector = new BarcodeDetector({
          formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e']
        });
      }

      mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });

      if (cameraVideo) {
        cameraVideo.srcObject = mediaStream;
        await cameraVideo.play();
      }

      const videoTrack = mediaStream.getVideoTracks()[0];
      if (videoTrack) {
        const capabilities = videoTrack.getCapabilities ? videoTrack.getCapabilities() : {};
        if (capabilities.torch && btnTorchToggle) {
          torchTrack = videoTrack;
          btnTorchToggle.style.display = 'inline-block';
        }
      }

      if (cameraStatusText) cameraStatusText.textContent = 'Arahkan kamera ke barcode material';
      isScanning = true;
      startScanLoop();

    } catch (err) {
      console.error('Camera error:', err);
      if (cameraStatusText) cameraStatusText.textContent = `Akses kamera ditolak: ${err.message}`;
      showToast(`Tidak dapat membuka kamera: ${err.message}`, 'danger');
    }
  }

  function closeCameraScanner() {
    isScanning = false;
    if (scanInterval) {
      clearInterval(scanInterval);
      scanInterval = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    torchTrack = null;
    torchEnabled = false;
    if (cameraVideo) cameraVideo.srcObject = null;
    if (cameraScannerModal) cameraScannerModal.style.display = 'none';
  }

  function toggleTorch() {
    if (torchTrack) {
      torchEnabled = !torchEnabled;
      torchTrack.applyConstraints({
        advanced: [{ torch: torchEnabled }]
      }).catch(err => console.log('Torch error:', err));
    }
  }

  let lastScannedCode = '';
  let lastScannedTime = 0;

  function startScanLoop() {
    if (!barcodeDetector) {
      if (cameraStatusText) {
        cameraStatusText.textContent = 'Kamera aktif. Silakan ketik SKU/Barcode pada form pencarian.';
      }
      return;
    }

    scanInterval = setInterval(async () => {
      if (!isScanning || !cameraVideo || cameraVideo.readyState < 2) return;

      try {
        const barcodes = await barcodeDetector.detect(cameraVideo);
        if (barcodes.length > 0) {
          const rawVal = barcodes[0].rawValue ? barcodes[0].rawValue.trim() : '';

          // BUG: kode yang sama ditambahkan berulang tiap 2 detik selama
          // barcode masih terlihat. Sekarang kode hanya diproses sekali;
          // baru boleh diproses lagi setelah barcode hilang dari kamera.
          if (rawVal && rawVal !== lastScannedCode) {
            lastScannedCode = rawVal;
            lastScannedTime = Date.now();
            onBarcodeScanned(rawVal);
          }
        } else if (lastScannedCode && Date.now() - lastScannedTime > 1500) {
          // Beri jeda agar satu barcode bisa sengaja discan dua kali:
          // arahkan kamera menjauh ±1,5 detik lalu scan lagi.
          lastScannedCode = '';
        }
      } catch (e) {
        // detection cycle error
      }
    }, 200);
  }

  async function onBarcodeScanned(code) {
    playScanBeep();
    triggerScanHaptic();
    if (cameraStatusText) cameraStatusText.textContent = `✅ Barcode Terdeteksi: ${code}`;

    try {
      const res = await fetch(`/api/materials/search?q=${encodeURIComponent(code)}`);
      const items = await res.json();
      if (items.length > 0) {
        const exact = items.find(i => i.barcode === code || i.sku === code) || items[0];
        addToCart(exact);
        if (cameraStatusText) cameraStatusText.textContent = `✅ Ditambahkan: ${exact.name}`;
      } else {
        showToast(`Material '${code}' belum terdaftar di gudang!`, 'warning');
      }
    } catch (err) {
      showToast(`Gagal memuat barang: ${err}`, 'danger');
    }
  }

  if (btnOpenScanner) btnOpenScanner.addEventListener('click', openCameraScanner);
  if (btnQuickScanIcon) btnQuickScanIcon.addEventListener('click', openCameraScanner);
  if (btnCloseScanner) btnCloseScanner.addEventListener('click', closeCameraScanner);
  if (btnTorchToggle) btnTorchToggle.addEventListener('click', toggleTorch);
});

# 🏗️ AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
**Sistem Gudang & Logistik Material Teknik Sipil Profesional (Server Lokal)**

Aplikasi manajemen pergudangan material konstruksi dan teknik sipil dirancang khusus dengan **tampilan cerah (Bright Professional UI)**, **kinerja tinggi pada server lokal**, dan **Mode Transaksi Cepat (Fast Dispatch & Intake)** berstandar POS/Barcode Scanner.

---

## 🌟 Fitur Utama

1. **⚡ Mode Transaksi Cepat (Quick Transaction / POS Mode):**
   - Mendukung **Pindai Barcode (Hardware USB/Bluetooth)** dan pencarian instan via SKU/Nama Material.
   - Pintasan keyboard: **`F2`** untuk fokus pencarian cepat, **`F9`** untuk langsung cetak & terbitkan Surat Jalan.
   - Dual-Mode: **Pengeluaran Material (Surat Jalan ke Proyek)** dan **Penerimaan Material (dari Supplier)**.
   - Quick Tiles untuk material sipil yang sering keluar (1-klik tambah).
   - Validasi stok fisik real-time (mencegah over-dispatch dengan peringatan visual).
   - Pengisian otomatis nomor polisi armada, nama mandor, dan penerima proyek.

2. **📄 Penerbitan Dokumen Resmi & Printable Slip:**
   - Surat Jalan Resmi (**SJ-YYYYMMDD-XXX**) berstandar proyek teknik sipil.
   - Bukti Penerimaan Barang (**BPP-YYYYMMDD-XXX**) dari vendor/pabrik.
   - Berita Acara Penyesuaian Stok (**ADJ-YYYYMMDD-XXX**).
   - Format cetak rapi dengan 4 kolom otorisasi tanda tangan: *Petugas Gudang/Checker, Mandor Lapangan, Logistik Lapangan Proyek, dan Site Manager*.

3. **📦 Master Material Sipil & Kontrol Stok Kritis:**
   - Katalog material konstruksi lengkap: *Besi & Baja SNI, Semen & Binder Kimia, Agregat & Pasir, Pipa & Drainase, Geosintetik, Kayu & Bekisting, Alat & K3 Sipil*.
   - Notifikasi dan visual badge untuk stok menipis / kritis (*stok <= batas minimum*).
   - Input/Edit spesifikasi teknis (SNI, mutu beton, toleransi ukuran) & lokasi zona/rak gudang.

4. **⚖️ Stock Opname & Audit Fisik:**
   - Fitur audit fisik langsung menghitung selisih (*selisih + atau -*).
   - Pencatatan alasan penyesuaian (susut timbunan pasir/koral, sisa potongan tulangan, kerusakan sak semen).
   - Audit trail lengkap mencatat tanggal, auditor, dan selisih kuantitas.

5. **🏗️ Proyek Konstruksi & Rekanan Vendor:**
   - Database lokasi site proyek (Tol, Jembatan, Gedung, Drainase, Perumahan).
   - Database rekanan pabrik & supplier material.

6. **📥 Export Data Laporan (Excel / CSV):**
   - 1-Klik download inventaris material lengkap dengan valuasi aset.
   - 1-Klik download arsip riwayat transaksi.

7. **💾 Backup & Migrasi Data Penuh (Pindah HP / Termux):**
   - **Download Database SQLite Utuh (`.db`)**: Salinan atomik lengkap seluruh tabel, relasi, riwayat transaksi, dan inventaris.
   - **Ekspor Format JSON (`.json`)**: Format cadangan standar portabel dan human-readable.
   - **Snapshot Lokal di Server**: Pembuatan salinan cadangan langsung di server Termux ke folder `backups/`.
   - **Impor & Pulihkan (Restore)**: Form upload untuk memulihkan sistem dari file `.db` atau `.json` saat berpindah server atau HP baru, dilengkapi *safety auto-snapshot* pencegah kehilangan data.

---

## 📱 Optimalisasi Khusus Android & Termux

Aplikasi gudang ini telah dioptimalkan khusus untuk lingkungan **Android & Termux**:

1. **🔋 Hemat Baterai & Anti-Sleep (Termux Wake-Lock):**
   - Skrip `start.sh` otomatis mengaktifkan `termux-wake-lock` sehingga server tidak dimatikan Android saat layar mati atau berpindah aplikasi.
   - Flask berjalan dalam mode multi-threading efisien tanpa watchdog stat loop yang menguras baterai.
   - Database SQLite dioptimalkan dengan mode **WAL (Write-Ahead Logging)** untuk kecepatan I/O tinggi di flash storage Android.

2. **📲 Tampilan Mobile App & Navigasi Bawah (Bottom Bar):**
   - Navigasi bawah ramah jempol (*thumb-friendly bottom navigation bar*) saat diakses lewat layar HP Android.
   - Tombol transaksi cepat di tengah dengan akses instan.
   - Drawer menu geser atas (*bottom-sheet*) untuk akses proyek, opname, dan ekspor data.

3. **📷 Pindai Barcode Kamera HP (In-App Camera Scanner):**
   - Petugas gudang dapat langsung memindai barcode fisik pada kemasan/surat material menggunakan kamera belakang HP Android.
   - Dilengkapi targeting reticle, animasi laser, getaran haptik (*vibration feedback*), dan nada konfirmasi audio.

4. **⚡ PWA (Progressive Web App - Installable Standalone App):**
   - Buka di Google Chrome Android, tap menu titik tiga (⋮) -> pilih **"Tambahkan ke Layar Utama" / "Install App"**.
   - Aplikasi akan tampil dengan ikon resmi **AL-CIVIL** di layar utama Android dan berjalan dalam mode layar penuh (*standalone*, tanpa bilah URL browser).

---

## 🚀 Cara Menjalankan Server Lokal (Android / Termux)

Dari direktori mana saja di Termux, cukup ketik:

```bash
al-civil
```
*(Atau `./start.sh` di dalam folder `al-civil`)*

Perintah ini akan otomatis:
1. Mengaktifkan anti-sleep Termux
2. Menjalankan server di latar belakang (*background daemon*)
3. Otomatis membuka aplikasi di browser Chrome Android Anda

### 🕹️ Perintah Manajemen Server Termux:
- `al-civil` atau `al-civil start` : Menjalankan server & buka browser
- `al-civil status` : Memeriksa status proses, PID, dan alamat IP
- `al-civil stop` : Menghentikan server & melepas wake-lock
- `al-civil restart` : Memulai ulang server
- `al-civil open` : Membuka browser ke aplikasi
- `al-civil log` : Melihat log server secara real-time

### 🌐 Alamat Akses:
- **Di Browser Perangkat Ini (Lokal):**
  - [http://localhost:5000](http://localhost:5000) atau [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Dari Laptop / Tablet / HP lain di jaringan WiFi / Hotspot yang sama:**
  - `http://<IP-LOKAL-ANDA>:5000` (misalnya `http://192.168.1.15:5000`)

---

## ⌨️ Daftar Pintasan Keyboard (Mode Cepat)

| Tombol | Fungsi |
|---|---|
| **`F2`** | Langsung fokus ke kolom pencarian material / pemindai barcode |
| **`Enter`** | Memasukkan material hasil pencarian ke daftar muatan |
| **`F9`** | Memproses transaksi dan menerbitkan Surat Jalan resmi |
| **`Esc`** | Membersihkan pencarian atau menutup popup modal |

---

## 🏛️ Struktur Berkas

```
al-civil/
├── app.py                     # Server Flask & REST API
├── database.py                # Database SQLite & Seed Data Sipil
├── alcivil.db                 # Database SQLite aktif
├── start.sh                   # Script peluncur otomatis
├── templates/
│   ├── base.html              # Template layout dasar & navigasi
│   ├── dashboard.html         # Ringkasan KPI & grafik status
│   ├── quick_transaction.html # MODE TRANSAKSI CEPAT (POS System)
│   ├── inventory.html         # Master Material & filter stok
│   ├── transactions.html      # Riwayat Surat Jalan & transaksi
│   ├── slip.html              # Template cetak Surat Jalan resmi
│   ├── projects.html          # Data Proyek & Mitra Supplier
│   └── stock_opname.html      # Form audit fisik & selisih stok
└── static/
    ├── css/style.css          # Desain cerah modern & cetak
    └── js/
        ├── app.js             # Toast & helper modal
        └── quick_trans.js     # Engine transaksi cepat & shortcut
```

# 🏗️ AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
**Sistem Gudang & Logistik Material Teknik Sipil Profesional (Server Lokal)**

Aplikasi manajemen pergudangan material konstruksi dan teknik sipil dirancang khusus dengan **Executive Premium UI** (palet navy–sapphire–gold, tipografi presisi, kartu KPI eksekutif, dan navigasi mobile bergaya aplikasi native), **kinerja tinggi pada server lokal**, serta **Mode Transaksi Cepat (Fast Dispatch & Intake)** berstandar POS/Barcode Scanner.

---

## 🌟 Fitur Utama

1. **⚡ Mode Transaksi Cepat (Quick Transaction / POS Mode):**
   - Mendukung **Pindai Barcode (Hardware USB/Bluetooth)** dan pencarian instan via SKU/Nama Material.
   - Pintasan keyboard: **`F2`** untuk fokus pencarian cepat, **`F9`** untuk langsung cetak & terbitkan Surat Jalan.
   - Dual-Mode: **Pengeluaran Material (Surat Jalan ke Proyek)** dan **Penerimaan Material (dari Supplier)**.
   - Quick Tiles untuk material sipil yang sering keluar (1-klik tambah).
   - Validasi stok fisik real-time (mencegah over-dispatch dengan peringatan visual).
   - **Update Harga Beli saat Penerimaan:** isi harga satuan aktual per item; harga master material otomatis diperbarui (dapat dinonaktifkan) sehingga valuasi stok dan transaksi berikutnya memakai harga terbaru.
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

## 📲 Unduh Aplikasi Android (APK) Siap Pakai

Untuk perangkat Android lain yang tidak menggunakan Termux atau ingin langsung memakai aplikasi AL-CIVIL seperti aplikasi biasa:

1. Kunjungi halaman rilis di browser HP: **[Download APK AL-CIVIL Terbaru](https://github.com/Alfiandi-ux/Al-civil/releases)**
2. Pada rilis terbaru (*Latest Release*), unduh file **`al-civil.apk`** yang ada di bagian **Assets**.
3. Buka file yang selesai diunduh lalu pilih **Install / Pasang**.
4. Jika muncul konfirmasi keamanan *"Izinkan instalasi dari sumber tidak dikenal"*, pilih **Izinkan (Allow)**.
5. Buka aplikasi **AL-CIVIL** di layar utama Android — server Python lokal dan database otomatis aktif 100% offline tanpa perlu menginstal Termux atau Python manual di HP tersebut!

> [!TIP]
> **Opsi Jaringan (Dual-Mode):**
> - **Mode Mandiri (Offline / Standalone)**: Database & server Flask berjalan langsung di dalam HP pengguna.
> - **Mode Klien (Multi-User via WiFi Proyek)**: Jika mandor / checker lapangan ingin terhubung ke server utama di kantor direksi keet, cukup tap tombol *"⚙️ Hubungkan ke Server Lain"* di layar pembuka dan masukkan IP server (contoh: `http://192.168.1.15:5000`).

---

## 🔐 Kunci Tanda Tangan APK (Signing Key)

Semua APK rilis **wajib ditandatangani dengan keystore yang sama** agar versi baru
bisa dipasang sebagai pembaruan (tanpa uninstall). Keystore tidak disimpan di
repositori; GitHub Actions memulihkannya dari *repository secrets*:

| Secret | Isi |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | File `release.keystore` yang di-encode base64 |
| `ANDROID_KEYSTORE_PASSWORD` | Password keystore |
| `ANDROID_KEY_ALIAS` | Alias kunci (default `alcivil`) |
| `ANDROID_KEY_PASSWORD` | Password kunci |

Sekali saja, dari Termux/laptop:

```bash
gh auth login
./android/scripts/setup-signing.sh
```

Skrip membuat `android/app/release.keystore`, menulis `android/keystore.properties`
(untuk build lokal), lalu mengunggah keempat secret ke GitHub. Bila `gh` belum
tersedia, skrip menampilkan nilai yang perlu diisi manual di
**Settings → Secrets and variables → Actions**.

> [!IMPORTANT]
> Cadangkan `release.keystore` beserta password-nya di tempat aman (mis. password
> manager). Jika file ini hilang, APK baru tidak dapat memperbarui aplikasi yang
> sudah terpasang sehingga pengguna harus uninstall terlebih dahulu.
>
> Catatan: APK **v1.1.1** ditandatangani dengan kunci sementara yang sudah tidak
> tersedia. Satu kali instalasi setelah perubahan ini perlu **uninstall dulu**;
> rilis berikutnya akan bisa diperbarui normal.

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

## 🚀 Instalasi & Menjalankan Server

### 1. Prasyarat
- **Python 3.10+**
- Terminal **Termux** (Android) atau shell Linux/macOS/Windows

### 2. Pasang dependensi

```bash
git clone https://github.com/Alfiandi-ux/al-civil.git
cd al-civil
pip install -r requirements.txt
```

*(Di Termux, jika `pip` belum ada: `pkg install python`.)*

### 3. Jalankan

**Android / Termux (mode background + buka browser otomatis):**

```bash
./start.sh start
```

**Semua platform (foreground):**

```bash
python3 app.py
```

Saat pertama kali dijalankan, aplikasi otomatis membuat database `alcivil.db`
beserta data contoh material sipil, proyek, dan supplier.

### ⚙️ Konfigurasi Environment

Salin `.env.example` menjadi `.env` lalu sesuaikan bila perlu:

| Variabel | Default | Keterangan |
|---|---|---|
| `SECRET_KEY` | acak per proses | Kunci sesi Flask. Isi nilai tetap saat deploy publik. |
| `PORT` | `5000` | Port server lokal. |
| `DEBUG` | `false` | Aktifkan mode debug Flask (`true`/`false`). |

### 🕹️ Perintah Manajemen Server Termux:
- `./start.sh start` : Menjalankan server & buka browser
- `./start.sh status` : Memeriksa status proses, PID, dan alamat IP
- `./start.sh stop` : Menghentikan server & melepas wake-lock
- `./start.sh restart` : Memulai ulang server
- `./start.sh open` : Membuka browser ke aplikasi
- `./start.sh log` : Melihat log server secara real-time

> Opsional: tambahkan `alias al-civil='~/al-civil/start.sh'` di `~/.bashrc`
> agar cukup mengetik `al-civil` dari direktori mana saja.

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

## 🧪 Menjalankan Tes Otomatis

```bash
python3 -m unittest test_alcivil -v
```

Saat ini ada **23 tes** yang mencakup autentikasi, CSRF, pembatasan role,
transaksi & stok, serta **backup/restore SQLite dan JSON**:

- snapshot SQLite valid & konsisten,
- ekspor JSON lengkap tanpa membocorkan hash password,
- restore `replace` dan `merge` (idempoten, relasi transaksi tetap utuh),
- penolakan file rusak, trigger berbahaya, dan referensi yatim + rollback,
- pembuatan snapshot pengaman sebelum restore,
- endpoint backup/unduh/upload/restore lokal/hapus beserta batas role.

Tes memakai database dan folder `backups/` sementara, sehingga data produksi
(`alcivil.db`) tidak tersentuh.

---

## 🏛️ Struktur Berkas

```
al-civil/
├── app.py                     # Server Flask & REST API
├── database.py                # Skema SQLite & seed data material sipil
├── test_alcivil.py            # Tes otomatis (auth, transaksi, backup/restore)
├── requirements.txt           # Dependensi Python
├── start.sh                   # Script peluncur otomatis (Termux)
├── .env.example               # Contoh konfigurasi environment
├── templates/
│   ├── base.html              # Layout dasar & navigasi
│   ├── dashboard.html         # Ringkasan KPI & grafik status
│   ├── quick_transaction.html # MODE TRANSAKSI CEPAT (POS System)
│   ├── inventory.html         # Master material & filter stok
│   ├── transactions.html      # Riwayat surat jalan & transaksi
│   ├── slip.html              # Template cetak surat jalan resmi
│   ├── projects.html          # Data proyek & mitra supplier
│   ├── stock_opname.html      # Form audit fisik & selisih stok
│   └── backup.html            # Backup, restore & migrasi data
└── static/
    ├── css/style.css          # Desain dasar & tata letak
    ├── css/premium.css        # Tema Executive Premium UI
    ├── js/app.js              # Toast & helper modal
    ├── js/quick_trans.js      # Engine transaksi cepat & shortcut
    ├── icons/                 # Ikon PWA (SVG, 192px, 512px)
    ├── manifest.json          # Manifest PWA
    └── sw.js                  # Service worker (cache offline)
```

**Dibuat otomatis saat runtime (tidak ikut Git):** `alcivil.db`,
`alcivil.db-wal`, `alcivil.db-shm`, `backups/`, `server.log`, `.server.pid`.

---

## 🤝 Kontribusi

1. Fork repositori ini.
2. Buat branch fitur: `git checkout -b fitur/nama-fitur`.
3. Commit perubahan: `git commit -m "feat: deskripsi singkat"`.
4. Push branch dan buka Pull Request.

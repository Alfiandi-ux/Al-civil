"""
AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
Database Layer & Seed Data
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alcivil.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # BUG-13 FIX: PRAGMA synchronous harus diset per-koneksi (tidak persisten seperti journal_mode)
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Performance optimizations for Android flash storage
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")

    # Materials Table (Master Barang Material Sipil & Konstruksi)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        barcode TEXT UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit TEXT NOT NULL,
        stock REAL NOT NULL DEFAULT 0,
        min_stock REAL NOT NULL DEFAULT 10,
        unit_price REAL NOT NULL DEFAULT 0,
        location TEXT DEFAULT 'Zona A-01',
        specification TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Projects Table (Proyek Penerima Material)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        client TEXT,
        location TEXT,
        status TEXT DEFAULT 'Aktif',
        contact_person TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Suppliers Table (Vendor / Pemasok Material)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT,
        phone TEXT,
        address TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Transactions Table (Surat Jalan / Bukti Penerimaan / Penyesuaian)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_number TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL, -- 'OUT' (Barang Keluar / SJ), 'IN' (Barang Masuk / BPP), 'ADJUST'
        project_id INTEGER,
        project_name TEXT,
        supplier_id INTEGER,
        supplier_name TEXT,
        vehicle_number TEXT,
        driver_name TEXT,
        operator_name TEXT DEFAULT 'Officer AL-CIVIL',
        total_items INTEGER DEFAULT 0,
        total_qty REAL DEFAULT 0,
        total_amount REAL DEFAULT 0,
        notes TEXT,
        status TEXT DEFAULT 'Selesai',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
    )
    ''')

    # Transaction Items Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transaction_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL,
        material_id INTEGER NOT NULL,
        sku TEXT,
        material_name TEXT,
        unit TEXT,
        qty REAL NOT NULL,
        unit_price REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )
    ''')

    # Stock Adjustments (Audit / Opname Fisik)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        material_id INTEGER NOT NULL,
        old_stock REAL NOT NULL,
        new_stock REAL NOT NULL,
        difference REAL NOT NULL,
        reason TEXT NOT NULL,
        adjusted_by TEXT DEFAULT 'Site Auditor',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (material_id) REFERENCES materials(id)
    )
    ''')

    # Check if materials are already seeded
    cursor.execute('SELECT COUNT(*) FROM materials')
    if cursor.fetchone()[0] == 0:
        seed_initial_data(cursor)

    conn.commit()
    conn.close()

def seed_initial_data(cursor):
    # Initial Materials (Civil & Construction Specific)
    materials = [
        # Besi & Baja
        ('BES-001', '8991001001', 'Besi Beton Ulir D13 SNI (Panjang 12m)', 'Besi & Baja', 'Batang', 450, 80, 118000, 'Yard Baja - Rak 01', 'TS 420B, Standar SNI 2052:2017'),
        ('BES-002', '8991001002', 'Besi Beton Ulir D16 SNI (Panjang 12m)', 'Besi & Baja', 'Batang', 280, 50, 178000, 'Yard Baja - Rak 02', 'TS 420B, Standar SNI 2052:2017'),
        ('BES-003', '8991001003', 'Besi Beton Polos D10 SNI (Panjang 12m)', 'Besi & Baja', 'Batang', 12, 100, 72000, 'Yard Baja - Rak 03', 'TP 280, Standar SNI 2052:2017 [STOK KRITIS]'),
        ('BES-004', '8991001004', 'Besi Wiremesh M8 (2.1m x 5.4m)', 'Besi & Baja', 'Lembar', 65, 20, 485000, 'Yard Baja - Blok C', 'BJKU Ulir U-50'),
        ('BES-005', '8991001005', 'Baja WF 200x100x5.5x8 (Panjang 12m)', 'Besi & Baja', 'Batang', 34, 15, 2750000, 'Yard Baja - Bay 1', 'SS400 / ASTM A36'),
        ('BES-006', '8991001006', 'Kawat Bendrat Beton (Roll 20kg)', 'Besi & Baja', 'Roll', 85, 25, 340000, 'Gudang Utama - Rak B1', 'Kawat Hitam Ikat Tulangan'),

        # Semen & Binder
        ('SMN-001', '8991002001', 'Semen Portland Type 1 (50 Kg)', 'Semen & Binder', 'Sak', 850, 150, 68000, 'Gudang Semen - Palet A', 'SNI 2049:2015, Tiga Roda / Holcim'),
        ('SMN-002', '8991002002', 'Semen Mortar Acian Plester (40 Kg)', 'Semen & Binder', 'Sak', 320, 80, 88000, 'Gudang Semen - Palet B', 'MU-200 / Demix'),
        ('SMN-003', '8991002003', 'SikaGrout 215 Non-Shrink Grout (25 Kg)', 'Semen & Binder', 'Sak', 45, 20, 195000, 'Gudang Semen - Rak Kimia', 'Mortar grouting mutu tinggi'),
        ('SMN-004', '8991002004', 'Concrete Admixture Sikament LN (Pail 20L)', 'Semen & Binder', 'Pail', 18, 10, 620000, 'Gudang Kimia Sipil', 'Superplasticizer pengurang air'),

        # Agregat, Pasir & Batu
        ('AGR-001', '8991003001', 'Pasir Cor Cuci Muntilan', 'Agregat & Pasir', 'M3', 140, 40, 310000, 'Open Yard - Bin 1', 'Kadar lumpur < 3%, gradasi zona 2'),
        ('AGR-002', '8991003002', 'Pasir Pasang Kali Progo', 'Agregat & Pasir', 'M3', 95, 30, 260000, 'Open Yard - Bin 2', 'Pasir halus untuk spesi plesteran'),
        ('AGR-003', '8991003003', 'Batu Split 2/3 (Koral Cor Beton)', 'Agregat & Pasir', 'M3', 210, 50, 275000, 'Open Yard - Bin 3', 'Batu pecah mesin 20-30 mm'),
        ('AGR-004', '8991003004', 'Batu Belah Pondasi (Pondasi Kali)', 'Agregat & Pasir', 'M3', 80, 25, 230000, 'Open Yard - Bin 4', 'Batu andesit keras untuk talud'),
        ('AGR-005', '8991003005', 'Base Course Agregat Kelas A', 'Agregat & Pasir', 'M3', 6, 30, 210000, 'Open Yard - Bin 5', 'Spesifikasi Bina Marga 2018 [STOK KRITIS]'),

        # Pipa & Drainase
        ('PIP-001', '8991004001', 'Pipa PVC Rucika AW 4 Inch (4 Meter)', 'Pipa & Drainase', 'Batang', 120, 30, 165000, 'Gudang Pipa - Rak P1', 'Kelas AW Tekanan Kerja 10 kg/cm2'),
        ('PIP-002', '8991004002', 'Pipa HDPE PE-100 OD 90mm PN10 SDR17', 'Pipa & Drainase', 'Roll', 8, 3, 4200000, 'Yard Pipa - Slot 2', 'Roll 100m, Pipa Air Minum Tekanan'),
        ('PIP-003', '8991004003', 'Geotextile Woven 200 gsm (4m x 150m)', 'Pipa & Drainase', 'Roll', 14, 5, 2850000, 'Gudang Kimia & Geotek', 'Stabilisasi tanah dasar timbunan'),

        # Bekisting & Kayu
        ('KAY-001', '8991005001', 'Plywood Film Faced Phenolic 18mm (1.22x2.44m)', 'Kayu & Bekisting', 'Lembar', 240, 50, 265000, 'Gudang Bekisting - Blok A', 'Triplek film hitam 2 sisi anti-air'),
        ('KAY-002', '8991005002', 'Kayu Kaso Meranti 5x7 cm (Panjang 4m)', 'Kayu & Bekisting', 'Batang', 500, 100, 38000, 'Gudang Bekisting - Blok B', 'Kayu pengaku bekisting & perancah'),
        ('KAY-003', '8991005003', 'Scaffolding Main Frame 1.70m', 'Kayu & Bekisting', 'Set', 160, 40, 425000, 'Yard Scaffolding', 'Lengkap Cross Brace & Joint Pin'),

        # Alat, Safety & K3 Sipil
        ('K3S-001', '8991006001', 'Helm Safety Proyek V-Gard Putih SNI', 'Alat & K3 Sipil', 'Pcs', 75, 20, 48000, 'Gudang K3 - Lemari 1', 'Suspensi Fastrac putar'),
        ('K3S-002', '8991006002', 'Rompi Safety Jaring Hijau Stabilo 4 Line', 'Alat & K3 Sipil', 'Pcs', 130, 30, 24000, 'Gudang K3 - Lemari 2', 'Pita reflektor scothlite terang'),
        ('K3S-003', '8991006003', 'Safety Shoes Cheetah Steel Toe Cap 42', 'Alat & K3 Sipil', 'Pasang', 25, 10, 365000, 'Gudang K3 - Rak Sepatu', 'Sol PU tahan minyak & tusukan'),
        ('K3S-004', '8991006004', 'Vibrator Cor Beton Portable Mesin Honda', 'Alat & K3 Sipil', 'Unit', 4, 2, 3850000, 'Ruang Alat Berat Ringan', 'Selang jarum 38mm x 4m')
    ]

    cursor.executemany('''
    INSERT INTO materials (sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', materials)

    # Initial Projects
    projects = [
        ('PRJ-TOL-01', 'Pembangunan Jalan Tol Segmen STA 14+200', 'PT Jasa Marga Persero', 'Jalur Selatan KM 14-22', 'Aktif', 'Ir. Bambang S. (Site Manager)'),
        ('PRJ-JBT-02', 'Pembangunan Jembatan Gelder Baja Cisadane', 'Dinas PUPR Provinsi', 'Cisadane Utara', 'Aktif', 'Hendro Cahyono, ST'),
        ('PRJ-GDG-03', 'Pembangunan Gedung Laboratorium Teknik 5 Lantai', 'Universitas Al-Madani', 'Kampus Terpadu Blok C', 'Aktif', 'Arif Wicaksono, MT'),
        ('PRJ-DRN-04', 'Normalisasi Saluran Drainase & Box Culvert Kota', 'Dinas Bina Marga', 'Kawasan Timur STA 0+800', 'Aktif', 'Dodi Kurniawan, ST'),
        ('PRJ-RSH-05', 'Proyek Perumahan Griya Sipil Asri Tahap 2', 'PT Cipta Karya Utama', 'Kavling Harmoni 1-50', 'Aktif', 'Siti Rahmawati, ST')
    ]

    cursor.executemany('''
    INSERT INTO projects (code, name, client, location, status, contact_person)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', projects)

    # Initial Suppliers
    suppliers = [
        ('SUP-KRK-01', 'PT Krakatau Steel Tbk', 'Besi & Baja', '021-3847721', 'Kawasan Industri Cilegon, Banten'),
        ('SUP-SMI-02', 'PT Semen Indonesia Group', 'Semen & Binder', '021-5261177', 'South Quarter Tower A, Jakarta'),
        ('SUP-WKA-03', 'PT Waskita Beton Precast', 'Agregat & Beton', '021-29838020', 'Gedung Terpadu Cawang, Jakarta'),
        ('SUP-RCK-04', 'PT Wahana Duta Rucika', 'Pipa & Plumbing', '021-6530188', 'Jl. Danau Sunter Barat, Jakarta'),
        ('SUP-SKT-05', 'PT Sika Indonesia', 'Kimia Konstruksi', '021-8233660', 'Jl. Raya Cibinong KM 37, Bogor')
    ]

    cursor.executemany('''
    INSERT INTO suppliers (code, name, category, phone, address)
    VALUES (?, ?, ?, ?, ?)
    ''', suppliers)

    # Initial Sample Transactions (To show active history in Dashboard)
    # 1. Outbound (Surat Jalan ke Tol)
    cursor.execute('''
    INSERT INTO transactions (
        transaction_number, type, project_id, project_name, vehicle_number, driver_name,
        operator_name, total_items, total_qty, total_amount, notes, status, created_at
    ) VALUES (
        'SJ-20261109-001', 'OUT', 1, 'Pembangunan Jalan Tol Segmen STA 14+200', 'B 9241 UDE', 'Pak Joko Santoso',
        'Staff Logistik AL-CIVIL', 3, 110, 24800000, 'Pengiriman batch 1 untuk pengecoran pile cap pier 4', 'Selesai',
        datetime('now', '-2 hours')
    )
    ''')
    trans1_id = cursor.lastrowid

    cursor.execute('''
    INSERT INTO transaction_items (transaction_id, material_id, sku, material_name, unit, qty, unit_price, total_price, notes)
    VALUES
        (?, 1, 'BES-001', 'Besi Beton Ulir D13 SNI (Panjang 12m)', 'Batang', 60, 118000, 7080000, 'Toleransi SNI'),
        (?, 2, 'BES-002', 'Besi Beton Ulir D16 SNI (Panjang 12m)', 'Batang', 40, 178000, 7120000, 'Mill Sheet Terlampir'),
        (?, 6, 'BES-006', 'Kawat Bendrat Beton (Roll 20kg)', 'Roll', 10, 340000, 3400000, 'Segel utuh')
    ''', (trans1_id, trans1_id, trans1_id))

    # 2. Inbound (Bukti Penerimaan Barang dari Semen Gresik / SIG)
    cursor.execute('''
    INSERT INTO transactions (
        transaction_number, type, supplier_id, supplier_name, vehicle_number, driver_name,
        operator_name, total_items, total_qty, total_amount, notes, status, created_at
    ) VALUES (
        'BPP-20261109-002', 'IN', 2, 'PT Semen Indonesia Group', 'H 8112 QA (Tronton)', 'Bpk. Yudi Purnomo',
        'Staff Logistik AL-CIVIL', 1, 200, 13600000, 'Penerimaan PO #PO-SMI-9821, kondisi sak utuh kering', 'Selesai',
        datetime('now', '-4 hours')
    )
    ''')
    trans2_id = cursor.lastrowid

    cursor.execute('''
    INSERT INTO transaction_items (transaction_id, material_id, sku, material_name, unit, qty, unit_price, total_price, notes)
    VALUES
        (?, 7, 'SMN-001', 'Semen Portland Type 1 (50 Kg)', 'Sak', 200, 68000, 13600000, 'Lot Produksi Nov-2026')
    ''', (trans2_id,))

def generate_transaction_number(tx_type, cursor=None):
    """Generate sequential number: SJ-YYYYMMDD-XXX, BPP-YYYYMMDD-XXX, ADJ-YYYYMMDD-XXX.

    Nomor berikutnya dihitung dari nomor urut TERBESAR yang sudah ada, bukan
    dari COUNT(*). Dengan cara ini, nomor tidak akan bentrok walaupun ada
    dokumen lama yang dihapus (menyisakan celah nomor).
    """
    today_str = datetime.now().strftime('%Y%m%d')
    if tx_type == 'OUT':
        prefix = 'SJ'
    elif tx_type == 'IN':
        prefix = 'BPP'
    else:
        prefix = 'ADJ'  # prefix dokumen, type record tetap 'ADJUST'
    pattern = f"{prefix}-{today_str}-%"

    close_conn = False
    if cursor is None:
        # Fallback jika dipanggil tanpa cursor
        conn = get_db()
        cursor = conn.cursor()
        close_conn = True

    cursor.execute("SELECT transaction_number FROM transactions WHERE transaction_number LIKE ?", (pattern,))
    next_number = 1
    for row in cursor.fetchall():
        try:
            sequence = int(str(row[0]).rsplit('-', 1)[1])
        except (IndexError, TypeError, ValueError):
            continue
        if sequence >= next_number:
            next_number = sequence + 1

    if close_conn:
        conn.close()

    return f"{prefix}-{today_str}-{next_number:03d}"

# ==========================================================
# BACKUP & RESTORE UTILITIES (MIGRASI DATA & SERVER)
# ==========================================================
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

def format_file_size(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"

def get_database_stats():
    """Mengambil statistik ukuran file dan jumlah baris per tabel."""
    stats = {
        'file_size_bytes': 0,
        'file_size_formatted': '0 KB',
        'materials_count': 0,
        'projects_count': 0,
        'suppliers_count': 0,
        'transactions_count': 0,
        'transaction_items_count': 0,
        'stock_adjustments_count': 0,
        'last_transaction': None,
        'db_path': DB_PATH
    }
    if os.path.exists(DB_PATH):
        size = os.path.getsize(DB_PATH)
        wal_path = DB_PATH + '-wal'
        if os.path.exists(wal_path):
            size += os.path.getsize(wal_path)
        stats['file_size_bytes'] = size
        stats['file_size_formatted'] = format_file_size(size)

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM materials")
        stats['materials_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM projects")
        stats['projects_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM suppliers")
        stats['suppliers_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM transactions")
        stats['transactions_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM transaction_items")
        stats['transaction_items_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM stock_adjustments")
        stats['stock_adjustments_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT created_at, transaction_number FROM transactions ORDER BY id DESC LIMIT 1")
        last_tx = cursor.fetchone()
        if last_tx:
            stats['last_transaction'] = f"{last_tx['transaction_number']} ({last_tx['created_at']})"

        conn.close()
    except Exception as e:
        stats['error'] = str(e)

    return stats

def backup_to_sqlite(dest_path=None):
    """Membuat salinan database SQLite online atomik yang konsisten."""
    if not dest_path:
        filename = f"alcivil_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        dest_path = os.path.join(BACKUP_DIR, filename)
    else:
        filename = os.path.basename(dest_path)

    # Flush WAL ke database utama
    src = get_db()
    src.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    dest = sqlite3.connect(dest_path)
    with dest:
        src.backup(dest, pages=100)
    dest.close()
    src.close()

    return filename, dest_path

def backup_to_json():
    """Mengekspor seluruh data tabel ke format JSON yang portabel."""
    conn = get_db()
    cursor = conn.cursor()

    tables = ['materials', 'projects', 'suppliers', 'transactions', 'transaction_items', 'stock_adjustments']
    data = {}
    summary = {}

    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        rows = [dict(row) for row in cursor.fetchall()]
        data[table] = rows
        summary[table] = len(rows)

    conn.close()

    payload = {
        'app': 'AL-CIVIL WMS',
        'version': '3.0',
        'format': 'alcivil_json_backup',
        'exported_at': datetime.now().isoformat(),
        'summary': summary,
        'data': data
    }
    return payload

def validate_sqlite_backup(file_path):
    """Validasi file SQLite: cek integritas dan tabel-tabel utama."""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False, "File database tidak ditemukan atau kosong."

    try:
        conn = sqlite3.connect(file_path, timeout=5.0)
        cursor = conn.cursor()

        # Cek integritas SQLite
        cursor.execute("PRAGMA quick_check")
        check_res = cursor.fetchone()
        if not check_res or check_res[0].lower() != 'ok':
            conn.close()
            return False, f"Pemeriksaan integritas SQLite gagal: {check_res[0] if check_res else 'Unknown'}"

        # Cek tabel wajib
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        required = ['materials', 'projects', 'suppliers', 'transactions', 'transaction_items']
        missing = [t for t in required if t not in tables]
        if missing:
            return False, f"File database tidak valid untuk AL-CIVIL (tabel hilang: {', '.join(missing)})."

        return True, "Valid"
    except Exception as e:
        return False, f"File bukan database SQLite yang valid ({str(e)})."

def restore_from_sqlite(source_path):
    """Memulihkan seluruh database dari file SQLite eksternal dengan auto-rollback."""
    valid, msg = validate_sqlite_backup(source_path)
    if not valid:
        return False, msg

    # Buat backup pengaman sebelum restore
    safety_name = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    safety_path = os.path.join(BACKUP_DIR, safety_name)
    try:
        backup_to_sqlite(safety_path)
    except Exception:
        pass

    try:
        # Flush WAL saat ini
        conn = get_db()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        # Gunakan backup API untuk menulis ulang alcivil.db dari source_path
        src = sqlite3.connect(source_path, timeout=10.0)
        dest = sqlite3.connect(DB_PATH, timeout=10.0)
        with dest:
            src.backup(dest)
        src.close()
        dest.close()

        # Inisialisasi PRAGMA & skema baru
        init_db()
        return True, "Database berhasil dipulihkan secara penuh."
    except Exception as e:
        return False, f"Gagal memulihkan database: {str(e)}"

def restore_from_json(payload, mode='replace'):
    """Memulihkan data dari dictionary/JSON backup."""
    if not isinstance(payload, dict) or 'data' not in payload:
        return False, "Format file JSON backup tidak valid (tidak ada root 'data')."

    data = payload.get('data', {})
    for req in ['materials', 'projects', 'suppliers']:
        if req not in data:
            return False, f"Tabel '{req}' tidak ditemukan dalam data JSON."

    safety_name = f"pre_restore_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    safety_path = os.path.join(BACKUP_DIR, safety_name)
    try:
        backup_to_sqlite(safety_path)
    except Exception:
        pass

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = OFF")

        if mode == 'replace':
            cursor.execute("DELETE FROM transaction_items")
            cursor.execute("DELETE FROM transactions")
            cursor.execute("DELETE FROM stock_adjustments")
            cursor.execute("DELETE FROM materials")
            cursor.execute("DELETE FROM projects")
            cursor.execute("DELETE FROM suppliers")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('materials', 'projects', 'suppliers', 'transactions', 'transaction_items', 'stock_adjustments')")

        # 1. Projects
        for p in data.get('projects', []):
            keys = [k for k in p.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [p[k] for k in keys]
            if mode == 'replace' and 'id' in p:
                cursor.execute(f"INSERT OR REPLACE INTO projects (id, {cols}) VALUES (?, {placeholders})", [p['id']] + vals)
            else:
                cursor.execute(f"INSERT OR REPLACE INTO projects ({cols}) VALUES ({placeholders})", vals)

        # 2. Suppliers
        for s in data.get('suppliers', []):
            keys = [k for k in s.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [s[k] for k in keys]
            if mode == 'replace' and 'id' in s:
                cursor.execute(f"INSERT OR REPLACE INTO suppliers (id, {cols}) VALUES (?, {placeholders})", [s['id']] + vals)
            else:
                cursor.execute(f"INSERT OR REPLACE INTO suppliers ({cols}) VALUES ({placeholders})", vals)

        # 3. Materials
        for m in data.get('materials', []):
            keys = [k for k in m.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [m[k] for k in keys]
            if mode == 'replace' and 'id' in m:
                cursor.execute(f"INSERT OR REPLACE INTO materials (id, {cols}) VALUES (?, {placeholders})", [m['id']] + vals)
            else:
                cursor.execute(f"INSERT OR REPLACE INTO materials ({cols}) VALUES ({placeholders})", vals)

        # 4. Transactions
        for t in data.get('transactions', []):
            keys = [k for k in t.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [t[k] for k in keys]
            if mode == 'replace' and 'id' in t:
                cursor.execute(f"INSERT OR REPLACE INTO transactions (id, {cols}) VALUES (?, {placeholders})", [t['id']] + vals)
            else:
                cursor.execute(f"INSERT OR IGNORE INTO transactions ({cols}) VALUES ({placeholders})", vals)

        # 5. Transaction Items
        for item in data.get('transaction_items', []):
            keys = [k for k in item.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [item[k] for k in keys]
            if mode == 'replace' and 'id' in item:
                cursor.execute(f"INSERT OR REPLACE INTO transaction_items (id, {cols}) VALUES (?, {placeholders})", [item['id']] + vals)
            else:
                cursor.execute(f"INSERT INTO transaction_items ({cols}) VALUES ({placeholders})", vals)

        # 6. Stock Adjustments
        for adj in data.get('stock_adjustments', []):
            keys = [k for k in adj.keys() if k != 'id']
            cols = ", ".join(keys)
            placeholders = ", ".join(["?"] * len(keys))
            vals = [adj[k] for k in keys]
            if mode == 'replace' and 'id' in adj:
                cursor.execute(f"INSERT OR REPLACE INTO stock_adjustments (id, {cols}) VALUES (?, {placeholders})", [adj['id']] + vals)
            else:
                cursor.execute(f"INSERT INTO stock_adjustments ({cols}) VALUES ({placeholders})", vals)

        cursor.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        conn.close()
        return True, "Data berhasil diimpor dari file JSON."
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Gagal mengimpor data JSON: {str(e)}"

def list_local_backups():
    """Mendapatkan daftar file backup yang tersimpan di direktori server."""
    if not os.path.exists(BACKUP_DIR):
        return []

    files = []
    for fname in os.listdir(BACKUP_DIR):
        if fname.endswith('.db') or fname.endswith('.json'):
            fpath = os.path.join(BACKUP_DIR, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                ftype = 'SQLite Database' if fname.endswith('.db') else 'JSON Data'
                is_auto = 'pre_restore' in fname or 'auto' in fname
                files.append({
                    'filename': fname,
                    'path': fpath,
                    'size_bytes': stat.st_size,
                    'size_formatted': format_file_size(stat.st_size),
                    'modified_at': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S'),
                    'mtime': stat.st_mtime,
                    'type': ftype,
                    'is_auto': is_auto
                })

    files.sort(key=lambda x: x['mtime'], reverse=True)
    return files

def delete_local_backup(filename):
    """Menghapus file backup lokal secara aman."""
    safe_name = os.path.basename(filename)
    if not (safe_name.endswith('.db') or safe_name.endswith('.json')):
        return False, "Tipe file tidak valid."
    fpath = os.path.join(BACKUP_DIR, safe_name)
    if os.path.exists(fpath):
        os.remove(fpath)
        return True, "File backup berhasil dihapus."
    return False, "File backup tidak ditemukan."

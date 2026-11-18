"""
AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
Database Layer & Seed Data
"""
import sqlite3
import os
import json
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

DATA_DIR = os.environ.get('ALCIVIL_DATA_DIR') or os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH') or os.path.join(DATA_DIR, 'alcivil.db')

# Kredensial admin awal. Bila ALCIVIL_ADMIN_PASSWORD tidak diisi, aplikasi
# memakai sandi default dan mewajibkan penggantian saat login pertama.
DEFAULT_ADMIN_USERNAME = os.environ.get('ALCIVIL_ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ALCIVIL_ADMIN_PASSWORD', 'admin123')
USING_DEFAULT_ADMIN_PASSWORD = not bool(os.environ.get('ALCIVIL_ADMIN_PASSWORD'))

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # BUG-13 FIX: PRAGMA synchronous harus diset per-koneksi (tidak persisten seperti journal_mode)
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

# ==========================================================
# USER & AUTHENTICATION HELPERS
# ==========================================================
def get_user_by_id(user_id):
    if not user_id:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, is_active, must_change_password, "
            "last_login_at, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def authenticate(username, password):
    """Kembalikan data user bila username + password benar dan akun aktif."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            return None
        if not row['is_active']:
            return None
        if not check_password_hash(row['password_hash'], password):
            return None
        return dict(row)
    finally:
        conn.close()

def touch_last_login(user_id):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (user_id,)
        )
        conn.commit()
    finally:
        conn.close()

def list_users():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role, is_active, must_change_password, "
            "last_login_at, created_at FROM users ORDER BY role ASC, username ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def create_user(username, password, role='operator', display_name='', must_change_password=0):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password) VALUES (?, ?, ?, ?, 1, ?)",
            (username, display_name or username, generate_password_hash(password),
             role, 1 if must_change_password else 0)
        )
        conn.commit()
        return True, "Akun berhasil dibuat."
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "Username tersebut sudah dipakai."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def set_user_password(user_id, password, must_change_password=0):
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (generate_password_hash(password), 1 if must_change_password else 0, user_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False, "Akun tidak ditemukan."
        conn.commit()
        return True, "Password berhasil diperbarui."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def set_user_active(user_id, active):
    """Aktif/nonaktifkan akun. Admin terakhir tidak boleh dinonaktifkan."""
    conn = get_db()
    try:
        row = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            conn.rollback()
            return False, "Akun tidak ditemukan."

        if not active and row['role'] == 'admin':
            admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
                (user_id,)
            ).fetchone()[0]
            if admins == 0:
                conn.rollback()
                return False, "Tidak dapat menonaktifkan admin terakhir yang aktif."

        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if active else 0, user_id)
        )
        conn.commit()
        return True, "Status akun diperbarui."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def count_active_users():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
    finally:
        conn.close()

def migrate_schema(cursor):
    """Tambahkan kolom baru yang belum ada pada database versi lama.

    Idempoten: aman dipanggil setiap kali aplikasi start.
    """
    columns = {row['name'] for row in cursor.execute("PRAGMA table_info(materials)")}
    if 'is_active' not in columns:
        cursor.execute(
            "ALTER TABLE materials ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )
    if 'archived_at' not in columns:
        cursor.execute("ALTER TABLE materials ADD COLUMN archived_at DATETIME")

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
        is_active INTEGER NOT NULL DEFAULT 1,
        archived_at DATETIME,
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

    # Users & Authentication (login, role admin/operator)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL COLLATE NOCASE,
        display_name TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'operator',
        is_active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        last_login_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Index untuk query laporan yang sering dipakai (dashboard, arsip, opname).
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_active ON materials(is_active, name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_category ON materials(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_items_transaction ON transaction_items(transaction_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_items_material ON transaction_items(material_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_adjustments_material ON stock_adjustments(material_id, created_at DESC)")

    # Migrasi skema untuk database lama: kolom soft-delete material.
    # SQLite tidak bisa ALTER CONSTRAINT, tapi bisa ALTER TABLE ADD COLUMN.
    migrate_schema(cursor)

    # Check if materials are already seeded
    cursor.execute('SELECT COUNT(*) FROM materials')
    if cursor.fetchone()[0] == 0:
        seed_initial_data(cursor)

    # Pastikan selalu ada akun admin agar aplikasi bisa diakses pertama kali.
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (username, display_name, password_hash, role,
                               is_active, must_change_password)
            VALUES (?, ?, ?, 'admin', 1, ?)
        ''', (
            DEFAULT_ADMIN_USERNAME,
            'Administrator Gudang',
            generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            1 if USING_DEFAULT_ADMIN_PASSWORD else 0
        ))

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
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
try:
    os.makedirs(BACKUP_DIR, exist_ok=True)
except Exception:
    pass

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
        'archived_materials_count': 0,
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

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 1")
        stats['materials_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 0")
        stats['archived_materials_count'] = cursor.fetchone()[0]

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
    except Exception as e:
        stats['error'] = str(e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return stats

def backup_to_sqlite(dest_path=None):
    """Membuat salinan database SQLite online atomik yang konsisten."""
    if not dest_path:
        filename = f"alcivil_backup_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
        dest_path = os.path.join(BACKUP_DIR, filename)
    else:
        filename = os.path.basename(dest_path)

    src = get_db()
    dest = None
    try:
        # Flush WAL ke database utama
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dest = sqlite3.connect(dest_path, timeout=10.0)
        with dest:
            src.backup(dest, pages=100)
    finally:
        if dest is not None:
            dest.close()
        src.close()

    return filename, dest_path

def backup_to_json():
    """Mengekspor seluruh data tabel ke format JSON yang portabel."""
    conn = get_db()
    try:
        cursor = conn.cursor()

        tables = ['materials', 'projects', 'suppliers', 'transactions', 'transaction_items', 'stock_adjustments']
        data = {}
        summary = {}

        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            rows = [dict(row) for row in cursor.fetchall()]
            data[table] = rows
            summary[table] = len(rows)
    finally:
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
    """Validasi file SQLite: integritas, tabel wajib, dan tidak ada trigger/view.

    Trigger/view ditolak karena file backup AL-CIVIL tidak pernah memakainya,
    sementara file berbahaya bisa menyisipkan trigger yang ikut tereksekusi
    saat aplikasi menulis ke database hasil restore.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False, "File database tidak ditemukan atau kosong."

    # Periksa header lebih dulu agar pesan galat bisa menjelaskan penyebabnya
    # (mis. file hasil unduhan ternyata halaman login HTML).
    try:
        with open(file_path, 'rb') as fh:
            header = fh.read(16)
    except Exception as e:
        return False, f"File database tidak dapat dibaca ({str(e)})."

    if not header.startswith(b'SQLite format 3\x00'):
        stripped = header.lstrip()
        if stripped.startswith(b'<'):
            return False, (
                "File bukan database SQLite (isinya halaman HTML/login). "
                "Unduh ulang backup dari menu Backup setelah login."
            )
        if stripped.startswith(b'{') or stripped.startswith(b'['):
            return False, (
                "File berisi data JSON, bukan database SQLite. "
                "Impor sebagai file .json."
            )
        return False, (
            "File bukan database SQLite yang valid (header tidak dikenali, "
            f"ukuran {os.path.getsize(file_path)} byte)."
        )

    conn = None
    try:
        conn = sqlite3.connect(file_path, timeout=5.0)
        cursor = conn.cursor()

        # Cek integritas SQLite
        cursor.execute("PRAGMA quick_check")
        check_res = cursor.fetchone()
        if not check_res or str(check_res[0]).lower() != 'ok':
            return False, f"Pemeriksaan integritas SQLite gagal: {check_res[0] if check_res else 'Unknown'}"

        # Tolak trigger/view asing (indikasi file tidak sah / berbahaya)
        cursor.execute("SELECT name, type FROM sqlite_master WHERE type IN ('trigger', 'view')")
        unsafe = cursor.fetchall()
        if unsafe:
            names = ', '.join(f"{r[1]}: {r[0]}" for r in unsafe[:5])
            return False, f"File database mengandung objek yang tidak diizinkan ({names})."

        # Cek tabel wajib
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        required = ['materials', 'projects', 'suppliers', 'transactions', 'transaction_items']
        missing = [t for t in required if t not in tables]
        if missing:
            return False, f"File database tidak valid untuk AL-CIVIL (tabel hilang: {', '.join(missing)})."

        # Cek kolom kunci agar restore tidak menghasilkan skema setengah jadi.
        required_columns = {
            'materials': ['id', 'sku', 'name', 'category', 'unit', 'stock'],
            'transactions': ['id', 'transaction_number', 'type'],
            'transaction_items': ['transaction_id', 'material_id', 'qty'],
            'projects': ['id', 'code', 'name'],
            'suppliers': ['id', 'code', 'name'],
        }
        for table, cols in required_columns.items():
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            missing_cols = [c for c in cols if c not in existing]
            if missing_cols:
                return False, (
                    f"Struktur tabel '{table}' tidak cocok "
                    f"(kolom hilang: {', '.join(missing_cols)})."
                )

        return True, "Valid"
    except Exception as e:
        return False, f"File bukan database SQLite yang valid ({str(e)})."
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

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
        try:
            dest = sqlite3.connect(DB_PATH, timeout=10.0)
            try:
                with dest:
                    src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()

        # Inisialisasi PRAGMA & skema baru
        init_db()
        return True, "Database berhasil dipulihkan secara penuh."
    except Exception as e:
        return False, f"Gagal memulihkan database: {str(e)}"

TABLE_NATURAL_KEYS = {
    'projects': 'code',
    'suppliers': 'code',
    'materials': 'sku',
    'transactions': 'transaction_number',
}

def _table_columns(conn, table):
    """Daftar kolom sah sebuah tabel (whitelist, mencegah injeksi identifier)."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def _filter_row(row, allowed, table):
    if not isinstance(row, dict):
        raise ValueError(f"Baris pada tabel '{table}' tidak valid.")
    data = {k: v for k, v in row.items() if k in allowed}
    if not data:
        raise ValueError(f"Baris pada tabel '{table}' tidak memiliki kolom yang dikenali.")
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            raise ValueError(f"Nilai kolom '{table}.{k}' tidak valid (harus teks/angka).")
    return data

def _insert_row(cursor, table, row, allowed, keep_id=True):
    data = _filter_row(row, allowed, table)
    if not keep_id:
        data.pop('id', None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    cursor.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values())
    )
    return cursor.lastrowid

def _update_row(cursor, table, row, allowed, key_col):
    data = _filter_row(row, allowed, table)
    key_value = data.get(key_col)
    updates = {k: v for k, v in data.items() if k not in ('id', key_col)}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates.keys())
    cursor.execute(
        f"UPDATE {table} SET {cols} WHERE {key_col} = ?",
        list(updates.values()) + [key_value]
    )

def restore_from_json(payload, mode='replace'):
    """Memulihkan data dari dictionary/JSON backup.

    Mode 'replace' mengosongkan tabel lalu memasang ulang data beserta ID asli.
    Mode 'merge' mencocokkan baris berdasarkan kunci alami (code/SKU/nomor
    dokumen) dan MEMPERTAHANKAN ID yang sudah ada, sehingga relasi transaksi
    tidak menjadi yatim. Item transaksi hanya dimasukkan untuk transaksi baru
    agar tidak terjadi duplikasi saat impor diulang.
    """
    if mode not in ('replace', 'merge'):
        return False, "Mode impor tidak valid."
    if not isinstance(payload, dict) or 'data' not in payload:
        return False, "Format file JSON backup tidak valid (tidak ada root 'data')."

    data = payload.get('data', {})
    if not isinstance(data, dict):
        return False, "Struktur 'data' pada file JSON tidak valid."
    for req in ['materials', 'projects', 'suppliers']:
        if req not in data:
            return False, f"Tabel '{req}' tidak ditemukan dalam data JSON."
    for table in ['materials', 'projects', 'suppliers', 'transactions',
                  'transaction_items', 'stock_adjustments']:
        if table in data and not isinstance(data[table], list):
            return False, f"Tabel '{table}' pada file JSON harus berupa daftar."

    safety_name = f"pre_restore_json_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    safety_path = os.path.join(BACKUP_DIR, safety_name)
    try:
        backup_to_sqlite(safety_path)
    except Exception:
        pass

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = OFF")
        allowed = {
            table: _table_columns(conn, table)
            for table in ['projects', 'suppliers', 'materials', 'transactions',
                          'transaction_items', 'stock_adjustments']
        }

        if mode == 'replace':
            cursor.execute("DELETE FROM transaction_items")
            cursor.execute("DELETE FROM transactions")
            cursor.execute("DELETE FROM stock_adjustments")
            cursor.execute("DELETE FROM materials")
            cursor.execute("DELETE FROM projects")
            cursor.execute("DELETE FROM suppliers")
            cursor.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('materials', 'projects', 'suppliers', 'transactions', "
                "'transaction_items', 'stock_adjustments')"
            )

            for table in ['projects', 'suppliers', 'materials',
                          'transactions', 'transaction_items', 'stock_adjustments']:
                for row in data.get(table, []):
                    _insert_row(cursor, table, row, allowed[table], keep_id=True)

            # Hanya data yang konsisten yang boleh masuk.
            fk_errors = cursor.execute("PRAGMA foreign_key_check").fetchall()
            if fk_errors:
                raise ValueError(
                    f"Data backup tidak konsisten: {len(fk_errors)} referensi yatim."
                )
            conn.commit()
            return True, "Data berhasil diganti penuh dari file JSON."

        # ---------- MERGE ----------
        id_maps = {'projects': {}, 'suppliers': {}, 'materials': {}, 'transactions': {}}
        stats = {'projects': 0, 'suppliers': 0, 'materials': 0, 'transactions': 0,
                 'transaction_items': 0, 'stock_adjustments': 0}

        for table in ['projects', 'suppliers', 'materials']:
            key_col = TABLE_NATURAL_KEYS[table]
            for row in data.get(table, []):
                clean = _filter_row(row, allowed[table], table)
                key_value = clean.get(key_col)
                if not key_value:
                    raise ValueError(f"Baris tabel '{table}' tidak memiliki '{key_col}'.")
                existing = cursor.execute(
                    f"SELECT id FROM {table} WHERE {key_col} = ?", (key_value,)
                ).fetchone()
                if existing:
                    _update_row(cursor, table, clean, allowed[table], key_col)
                    new_id = existing['id']
                elif table == 'materials':
                    try:
                        new_id = _insert_row(cursor, table, clean, allowed[table], keep_id=False)
                    except sqlite3.IntegrityError:
                        # Barcode bentrok dengan material lain -> simpan tanpa barcode.
                        clean['barcode'] = None
                        new_id = _insert_row(cursor, table, clean, allowed[table], keep_id=False)
                else:
                    new_id = _insert_row(cursor, table, clean, allowed[table], keep_id=False)
                stats[table] += 1
                if clean.get('id') is not None:
                    id_maps[table][clean['id']] = new_id

        # Transaksi: pertahankan nomor dokumen, petakan ID lama -> ID sebenarnya.
        new_transaction_old_ids = set()
        for row in data.get('transactions', []):
            clean = _filter_row(row, allowed['transactions'], 'transactions')
            tx_num = clean.get('transaction_number')
            if not tx_num:
                raise ValueError("Baris transaksi tidak memiliki transaction_number.")
            existing = cursor.execute(
                "SELECT id FROM transactions WHERE transaction_number = ?", (tx_num,)
            ).fetchone()
            if existing:
                new_id = existing['id']
            else:
                new_id = _insert_row(cursor, 'transactions', clean, allowed['transactions'],
                                     keep_id=False)
                if clean.get('id') is not None:
                    new_transaction_old_ids.add(clean['id'])
            stats['transactions'] += 1
            if clean.get('id') is not None:
                id_maps['transactions'][clean['id']] = new_id

        # Item transaksi: hanya untuk transaksi yang benar-benar baru.
        seen_items = set()
        for row in data.get('transaction_items', []):
            clean = _filter_row(row, allowed['transaction_items'], 'transaction_items')
            old_tx_id = clean.get('transaction_id')
            old_mat_id = clean.get('material_id')
            if old_tx_id not in new_transaction_old_ids:
                continue
            new_tx_id = id_maps['transactions'].get(old_tx_id)
            new_mat_id = id_maps['materials'].get(old_mat_id, old_mat_id)
            if not new_tx_id or not new_mat_id:
                continue
            clean['transaction_id'] = new_tx_id
            clean['material_id'] = new_mat_id
            if 'id' in clean:
                clean = {k: v for k, v in clean.items() if k != 'id'}
            fingerprint = (
                new_tx_id, new_mat_id, clean.get('qty'),
                clean.get('unit_price'), clean.get('notes')
            )
            if fingerprint in seen_items:
                continue
            seen_items.add(fingerprint)
            _insert_row(cursor, 'transaction_items', clean, allowed['transaction_items'],
                        keep_id=False)
            stats['transaction_items'] += 1

        # Penyesuaian stok: hindari duplikasi baris yang identik.
        for row in data.get('stock_adjustments', []):
            clean = _filter_row(row, allowed['stock_adjustments'], 'stock_adjustments')
            clean['material_id'] = id_maps['materials'].get(
                clean.get('material_id'), clean.get('material_id')
            )
            if not clean.get('material_id'):
                continue
            exists = cursor.execute(
                "SELECT 1 FROM stock_adjustments WHERE material_id = ? AND old_stock = ? "
                "AND new_stock = ? AND COALESCE(reason, '') = COALESCE(?, '') "
                "AND COALESCE(created_at, '') = COALESCE(?, '')",
                (clean.get('material_id'), clean.get('old_stock'), clean.get('new_stock'),
                 clean.get('reason'), clean.get('created_at'))
            ).fetchone()
            if exists:
                continue
            clean.pop('id', None)
            _insert_row(cursor, 'stock_adjustments', clean, allowed['stock_adjustments'],
                        keep_id=False)
            stats['stock_adjustments'] += 1

        fk_errors = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise ValueError(
                f"Data gabungan tidak konsisten: {len(fk_errors)} referensi yatim."
            )
        conn.commit()
        return True, (
            f"Data berhasil digabungkan: {stats['materials']} material, "
            f"{stats['transactions']} transaksi, "
            f"{stats['transaction_items']} item baru."
        )
    except Exception as e:
        conn.rollback()
        return False, f"Gagal mengimpor data JSON: {str(e)}"
    finally:
        try:
            # PRAGMA foreign_keys tidak berlaku di dalam transaksi, jadi
            # dijalankan setelah commit/rollback pada koneksi yang sama.
            conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        conn.close()

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
    fpath = os.path.realpath(os.path.join(BACKUP_DIR, safe_name))
    backup_root = os.path.realpath(BACKUP_DIR)
    if os.path.dirname(fpath) != backup_root:
        return False, "Lokasi file tidak valid."
    if os.path.isfile(fpath):
        os.remove(fpath)
        return True, "File backup berhasil dihapus."
    return False, "File backup tidak ditemukan."

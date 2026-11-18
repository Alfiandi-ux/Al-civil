import os
import sys
import tempfile
import unittest
import json
import shutil
import sqlite3
from io import BytesIO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALCIVIL_DIR = os.path.join(BASE_DIR, 'al-civil') if os.path.exists(os.path.join(BASE_DIR, 'al-civil')) else BASE_DIR
sys.path.insert(0, ALCIVIL_DIR)

# Siapkan isolated database di temp file
temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
temp_db_path = temp_db.name
temp_db.close()
os.environ['DB_PATH'] = temp_db_path
if 'ALCIVIL_ADMIN_PASSWORD' in os.environ:
    del os.environ['ALCIVIL_ADMIN_PASSWORD']

import database
import app as alcivil_app

class AlCivilAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_PATH = temp_db_path
        database.init_db()
        alcivil_app.app.config['TESTING'] = True
        cls.client = alcivil_app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)
        except Exception:
            pass

    def get_csrf(self):
        with self.client.session_transaction() as sess:
            token = sess.get('csrf_token')
            if not token:
                token = 'test-csrf-token'
                sess['csrf_token'] = token
            return token

    def login_as(self, username, password):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['csrf_token'] = 'login-csrf-token'
        res = self.client.post('/login', data={
            'username': username,
            'password': password,
            'csrf_token': 'login-csrf-token'
        }, follow_redirects=True)
        return res

    def test_01_unauthenticated_redirect(self):
        """Request ke dashboard tanpa login harus dialihkan ke /login"""
        with self.client.session_transaction() as sess:
            sess.clear()
        res = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_02_login_page_renders(self):
        """Halaman login harus dirender dengan status 200 dan form login"""
        with self.client.session_transaction() as sess:
            sess.clear()
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Masuk ke Sistem', res.data)
        self.assertIn(b'usernameInput', res.data)

    def test_03_login_failed_and_success(self):
        """Login dengan password salah harus gagal, dengan admin123 harus sukses"""
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['csrf_token'] = 'test-token-123'

        res_fail = self.client.post('/login', data={
            'username': 'admin',
            'password': 'wrongpassword',
            'csrf_token': 'test-token-123'
        }, follow_redirects=True)
        self.assertEqual(res_fail.status_code, 401)
        self.assertIn('Username atau password salah', res_fail.data.decode('utf-8'))

        with self.client.session_transaction() as sess:
            sess.clear()
            sess['csrf_token'] = 'test-token-123'

        res_ok = self.client.post('/login', data={
            'username': 'admin',
            'password': 'admin123',
            'csrf_token': 'test-token-123'
        }, follow_redirects=False)
        self.assertEqual(res_ok.status_code, 302)
        self.assertIn('/account', res_ok.headers.get('Location', ''))

    def test_04_change_password(self):
        """Ganti password default admin menjadi password baru"""
        self.login_as('admin', 'admin123')
        csrf = self.get_csrf()

        res = self.client.post('/account/password', data={
            'current_password': 'admin123',
            'new_password': 'NewSecurePassword2026!',
            'confirm_password': 'NewSecurePassword2026!',
            'csrf_token': csrf
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/dashboard', res.headers.get('Location', ''))

        res_dash = self.client.get('/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'AL-CIVIL', res_dash.data)

    def test_05_csrf_protection_blocks_invalid_post(self):
        """POST tanpa CSRF token yang valid harus ditolak"""
        self.login_as('admin', 'NewSecurePassword2026!')
        res = self.client.post('/project/save', data={
            'code': 'PRJ-TEST',
            'name': 'Proyek Uji Coba CSRF'
        })
        self.assertEqual(res.status_code, 302)
        res_followed = self.client.get('/dashboard')
        self.assertIn('Sesi keamanan tidak valid', res_followed.data.decode('utf-8'))

    def test_06_create_user_and_role_access(self):
        """Admin membuat user operator dan verifikasi pembatasan role operator"""
        self.login_as('admin', 'NewSecurePassword2026!')
        csrf = self.get_csrf()

        # Buat operator
        res = self.client.post('/users/create', data={
            'username': 'operator_lapangan',
            'display_name': 'Operator Logistik 1',
            'role': 'operator',
            'password': 'OperatorPass123!',
            'csrf_token': csrf
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Akun berhasil dibuat', res.data.decode('utf-8'))

        # Login sebagai operator
        self.login_as('operator_lapangan', 'OperatorPass123!')

        # Ganti sandi awal operator
        csrf_op = self.get_csrf()
        self.client.post('/account/password', data={
            'current_password': 'OperatorPass123!',
            'new_password': 'PermanentOpPass2026!',
            'confirm_password': 'PermanentOpPass2026!',
            'csrf_token': csrf_op
        }, follow_redirects=False)

        # Operator mencoba akses /backup (harus 403 Forbidden)
        res_backup = self.client.get('/backup')
        self.assertEqual(res_backup.status_code, 403)

        # Operator mencoba akses /users (harus 403 Forbidden)
        res_users = self.client.get('/users')
        self.assertEqual(res_users.status_code, 403)

        # Tapi operator BISA akses transaksi cepat dan master material
        res_trans = self.client.get('/transaksi-cepat')
        self.assertEqual(res_trans.status_code, 200)
        res_inv = self.client.get('/inventory')
        self.assertEqual(res_inv.status_code, 200)

    def test_07_api_transaction_create(self):
        """Buat transaksi keluar (OUT) melalui /api/transaction/create"""
        self.login_as('admin', 'NewSecurePassword2026!')
        csrf = self.get_csrf()

        conn = database.get_db()
        mat = conn.execute("SELECT id, stock FROM materials WHERE is_active = 1 LIMIT 1").fetchone()
        mat_id = mat['id']
        old_stock = mat['stock']
        prj = conn.execute("SELECT id, name FROM projects LIMIT 1").fetchone()
        prj_id = prj['id']
        conn.close()

        payload = {
            'type': 'OUT',
            'project_id': prj_id,
            'vehicle_number': 'B 1234 CD',
            'driver_name': 'Pak Slamet',
            'items': [
                {'material_id': mat_id, 'qty': 2, 'unit_price': 10000}
            ]
        }

        res = self.client.post('/api/transaction/create',
                               json=payload,
                               headers={'X-CSRF-Token': csrf})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

        conn = database.get_db()
        new_mat = conn.execute("SELECT stock FROM materials WHERE id = ?", (mat_id,)).fetchone()
        conn.close()
        self.assertEqual(new_mat['stock'], old_stock - 2)

    def test_08_material_soft_delete_and_restore(self):
        """Material yang memiliki riwayat transaksi harus diarsipkan (soft-delete), bukan error FK"""
        self.login_as('admin', 'NewSecurePassword2026!')
        csrf = self.get_csrf()

        conn = database.get_db()
        used_mat = conn.execute("SELECT material_id FROM transaction_items LIMIT 1").fetchone()
        mat_id = used_mat['material_id']
        conn.close()

        res_del = self.client.post(f'/material/delete/{mat_id}', data={'csrf_token': csrf}, follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn('diarsipkan karena sudah dipakai', res_del.data.decode('utf-8'))

        conn = database.get_db()
        m_row = conn.execute("SELECT is_active, archived_at FROM materials WHERE id = ?", (mat_id,)).fetchone()
        self.assertEqual(m_row['is_active'], 0)
        self.assertIsNotNone(m_row['archived_at'])
        conn.close()

        csrf = self.get_csrf()
        res_restore = self.client.post(f'/material/restore/{mat_id}', data={'csrf_token': csrf}, follow_redirects=True)
        self.assertEqual(res_restore.status_code, 200)
        self.assertIn('berhasil dipulihkan', res_restore.data.decode('utf-8'))

        conn = database.get_db()
        m_restored = conn.execute("SELECT is_active, archived_at FROM materials WHERE id = ?", (mat_id,)).fetchone()
        self.assertEqual(m_restored['is_active'], 1)
        self.assertIsNone(m_restored['archived_at'])
        conn.close()

    def test_09_stock_opname_adjustment(self):
        """Penyesuaian stok fisik (Stock Opname)"""
        self.login_as('admin', 'NewSecurePassword2026!')
        csrf = self.get_csrf()

        conn = database.get_db()
        mat = conn.execute("SELECT id, stock FROM materials WHERE is_active = 1 LIMIT 1").fetchone()
        mat_id = mat['id']
        conn.close()

        res = self.client.post('/stock-opname/save', data={
            'material_id': mat_id,
            'new_stock': 999,
            'reason': 'Hasil audit fisik lapangan kuartal 4',
            'adjusted_by': 'Auditor Sipil',
            'csrf_token': csrf
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn('berhasil disesuaikan', res.data.decode('utf-8'))

        conn = database.get_db()
        updated = conn.execute("SELECT stock FROM materials WHERE id = ?", (mat_id,)).fetchone()
        conn.close()
        self.assertEqual(updated['stock'], 999)

    def test_10_csv_exports(self):
        """Download laporan CSV material dan transaksi"""
        self.login_as('admin', 'NewSecurePassword2026!')
        res_mat = self.client.get('/export/materials.csv')
        self.assertEqual(res_mat.status_code, 200)
        self.assertEqual(res_mat.content_type, 'text/csv; charset=utf-8')
        self.assertIn('SKU', res_mat.data.decode('utf-8'))

        res_tx = self.client.get('/export/transactions.csv')
        self.assertEqual(res_tx.status_code, 200)
        self.assertEqual(res_tx.content_type, 'text/csv; charset=utf-8')
        self.assertIn('No Transaksi', res_tx.data.decode('utf-8'))

    def test_11_slip_view(self):
        """Melihat surat jalan resmi printable slip"""
        self.login_as('admin', 'NewSecurePassword2026!')
        conn = database.get_db()
        tx = conn.execute("SELECT id FROM transactions WHERE type = 'OUT' LIMIT 1").fetchone()
        conn.close()

        res = self.client.get(f'/slip/{tx["id"]}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'SURAT JALAN', res.data)

    def test_12_project_and_supplier_crud(self):
        """Tambah dan perbarui Proyek serta Vendor"""
        self.login_as('admin', 'NewSecurePassword2026!')
        csrf = self.get_csrf()

        # Tambah proyek
        res_p = self.client.post('/project/save', data={
            'code': 'PRJ-NEW-01',
            'name': 'Pembangunan Flyover Simpang Raya',
            'client': 'Kementerian PUPR',
            'location': 'Ruas Jalan Tol Seksi 2',
            'contact_person': 'Ir. Hendra',
            'csrf_token': csrf
        }, follow_redirects=True)
        self.assertEqual(res_p.status_code, 200)
        self.assertIn('berhasil didaftarkan', res_p.data.decode('utf-8'))

        # Tambah vendor
        csrf = self.get_csrf()
        res_s = self.client.post('/supplier/save', data={
            'code': 'SUP-NEW-01',
            'name': 'PT Beton Jaya Mandiri',
            'category': 'Semen & Beton',
            'phone': '08123456789',
            'address': 'Kawasan Industri Cikarang',
            'csrf_token': csrf
        }, follow_redirects=True)
        self.assertEqual(res_s.status_code, 200)
        self.assertIn('berhasil didaftarkan', res_s.data.decode('utf-8'))

    def test_13_transactions_page(self):
        """Membuka halaman /transaksi (Surat Jalan & Transaksi) dengan pagination dan filter"""
        self.login_as('admin', 'NewSecurePassword2026!')
        res = self.client.get('/transaksi')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Surat Jalan', res.data.decode('utf-8'))

        # Filter type OUT
        res_filter = self.client.get('/transaksi?type=OUT')
        self.assertEqual(res_filter.status_code, 200)

        # Search
        res_search = self.client.get('/transaksi?search=Pak')
        self.assertEqual(res_search.status_code, 200)

# ==========================================================
# TESTS: BACKUP, EXPORT, RESTORE & MIGRASI DATA
# ==========================================================
class BackupRestoreTests(unittest.TestCase):
    """Tes backup/restore dengan database & folder backups/ terisolasi.

    Kelas ini memakai DB sementara sendiri sehingga saga mutasi data tidak
    memengaruhi tes aplikasi di atasnya maupun data produksi ``alcivil.db``.
    """

    ADMIN_PASSWORD = 'BackupTestPass2026!'

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix='alcivil-backup-test-')
        cls._orig_db_path = database.DB_PATH
        cls._orig_backup_dir = database.BACKUP_DIR

        database.DB_PATH = os.path.join(cls.tmpdir, 'alcivil_test.db')
        database.BACKUP_DIR = os.path.join(cls.tmpdir, 'backups')
        os.makedirs(database.BACKUP_DIR, exist_ok=True)
        database.init_db()

        admin = database.get_user_by_username('admin')
        database.set_user_password(admin['id'], cls.ADMIN_PASSWORD,
                                   must_change_password=0)

        alcivil_app.app.config['TESTING'] = True
        cls.client = alcivil_app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._orig_db_path
        database.BACKUP_DIR = cls._orig_backup_dir
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ------------------------- helpers -------------------------

    def login(self, username='admin', password=None):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['csrf_token'] = 'test-csrf-token'
        return self.client.post('/login', data={
            'username': username,
            'password': password or self.ADMIN_PASSWORD,
            'csrf_token': 'test-csrf-token',
        }, follow_redirects=True)

    def csrf(self):
        with self.client.session_transaction() as sess:
            return sess.get('csrf_token') or 'test-csrf-token'

    def count(self, table, path=None):
        conn = sqlite3.connect(path or database.DB_PATH)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()

    def stock_of(self, sku, path=None):
        conn = sqlite3.connect(path or database.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT stock FROM materials WHERE sku = ?", (sku,)
            ).fetchone()
            return row['stock'] if row else None
        finally:
            conn.close()

    def mutate(self):
        """Ubah data supaya terbukti restore benar-benar mengembalikan keadaan."""
        conn = database.get_db()
        try:
            conn.execute(
                "UPDATE materials SET stock = stock + 77 WHERE sku = 'BES-001'"
            )
            conn.execute(
                "INSERT INTO materials "
                "(sku, name, category, unit, stock, min_stock, unit_price) "
                "VALUES ('TST-MUT-01', 'Material Uji Mutasi', 'Besi & Baja', "
                "'Batang', 5, 1, 1000)"
            )
            conn.commit()
        finally:
            conn.close()

    def assert_fk_clean(self):
        conn = database.get_db()
        try:
            self.assertEqual(
                conn.execute("PRAGMA foreign_key_check").fetchall(), []
            )
        finally:
            conn.close()

    # --------------------------- tes ---------------------------

    def test_01_sqlite_snapshot_valid_dan_konsisten(self):
        filename, path = database.backup_to_sqlite()
        self.assertTrue(filename.startswith('alcivil_backup_'))
        self.assertTrue(filename.endswith('.db'))
        self.assertTrue(os.path.isfile(path))

        ok, msg = database.validate_sqlite_backup(path)
        self.assertTrue(ok, msg)
        for table in ['materials', 'projects', 'suppliers', 'transactions',
                      'transaction_items', 'stock_adjustments']:
            self.assertEqual(self.count(table), self.count(table, path), table)

    def test_02_export_json_lengkap_dan_tanpa_kredensial(self):
        payload = database.backup_to_json()
        self.assertEqual(payload['format'], 'alcivil_json_backup')
        self.assertEqual(payload['app'], 'AL-CIVIL WMS')
        self.assertIn('exported_at', payload)

        for table in ['materials', 'projects', 'suppliers', 'transactions',
                      'transaction_items', 'stock_adjustments']:
            self.assertIn(table, payload['data'])
            self.assertEqual(payload['summary'][table],
                             len(payload['data'][table]), table)

        # Tabel users (hash password) tidak boleh ikut terekspor.
        self.assertNotIn('users', payload['data'])
        self.assertNotIn('password_hash', json.dumps(payload))

    def test_03_restore_json_replace_mengembalikan_data(self):
        payload = database.backup_to_json()
        original_stock = self.stock_of('BES-001')
        self.mutate()

        ok, msg = database.restore_from_json(payload, mode='replace')
        self.assertTrue(ok, msg)
        self.assertEqual(self.stock_of('BES-001'), original_stock)
        self.assertIsNone(self.stock_of('TST-MUT-01'))
        for table, expected in payload['summary'].items():
            self.assertEqual(self.count(table), expected, table)
        self.assert_fk_clean()

    def test_04_restore_sqlite_dan_snapshot_pengaman(self):
        _, snapshot_path = database.backup_to_sqlite()
        original_stock = self.stock_of('BES-001')
        self.mutate()

        ok, msg = database.restore_from_sqlite(snapshot_path)
        self.assertTrue(ok, msg)
        self.assertEqual(self.stock_of('BES-001'), original_stock)
        self.assertIsNone(self.stock_of('TST-MUT-01'))

        safety = [f for f in os.listdir(database.BACKUP_DIR)
                  if f.startswith('pre_restore_')
                  and not f.startswith('pre_restore_json_')
                  and f.endswith('.db')]
        self.assertTrue(safety, "snapshot pengaman pra-restore tidak dibuat")
        safety_path = os.path.join(database.BACKUP_DIR, sorted(safety)[-1])
        valid, vmsg = database.validate_sqlite_backup(safety_path)
        self.assertTrue(valid, vmsg)
        # Snapshot pengaman diambil sebelum restore, jadi masih memuat mutasi.
        self.assertIsNotNone(self.stock_of('TST-MUT-01', safety_path))

    def test_05_file_sqlite_tidak_valid_ditolak(self):
        empty = os.path.join(self.tmpdir, 'empty.db')
        open(empty, 'wb').close()

        text = os.path.join(self.tmpdir, 'text.db')
        with open(text, 'wb') as f:
            f.write(b'ini bukan database sqlite')

        missing = os.path.join(self.tmpdir, 'missing.db')
        conn = sqlite3.connect(missing)
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.commit()
        conn.close()

        trigger = os.path.join(self.tmpdir, 'trigger.db')
        conn = sqlite3.connect(trigger)
        conn.executescript("""
            CREATE TABLE materials (id INTEGER PRIMARY KEY, sku TEXT, name TEXT,
                                    category TEXT, unit TEXT, stock INTEGER);
            CREATE TABLE projects (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
            CREATE TABLE suppliers (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
            CREATE TABLE transactions (id INTEGER PRIMARY KEY,
                                       transaction_number TEXT, type TEXT);
            CREATE TABLE transaction_items (id INTEGER PRIMARY KEY,
                                            transaction_id INTEGER,
                                            material_id INTEGER, qty REAL);
            CREATE TRIGGER evil_trigger AFTER INSERT ON materials
            BEGIN SELECT 1; END;
        """)
        conn.commit()
        conn.close()

        cases = [
            (empty, 'kosong'),
            (text, 'bukan database'),
            (missing, 'tabel hilang'),
            (trigger, 'tidak diizinkan'),
        ]
        for path, expected in cases:
            ok, msg = database.validate_sqlite_backup(path)
            self.assertFalse(ok, f"{path} seharusnya ditolak")
            self.assertIn(expected, msg.lower(), msg)

        before = self.count('materials')
        ok, msg = database.restore_from_sqlite(text)
        self.assertFalse(ok)
        self.assertEqual(self.count('materials'), before)
        ok, msg = database.restore_from_sqlite(trigger)
        self.assertFalse(ok)
        self.assertIn('tidak diizinkan', msg.lower())

    def test_06_json_tidak_valid_ditolak_dan_rollback(self):
        ok, msg = database.restore_from_json({'format': 'x'})
        self.assertFalse(ok)
        self.assertIn("root 'data'", msg)

        ok, msg = database.restore_from_json(
            {'data': {'projects': [], 'suppliers': []}}
        )
        self.assertFalse(ok)
        self.assertIn('materials', msg)

        ok, msg = database.restore_from_json({'data': {}}, mode='ngawur')
        self.assertFalse(ok)
        self.assertIn('Mode impor', msg)

        # Referensi yatim harus membatalkan seluruh impor (rollback).
        payload = database.backup_to_json()
        broken = json.loads(json.dumps(payload))
        broken['data']['transactions'].append({
            'id': 999999,
            'transaction_number': 'SJ-99999999-999',
            'type': 'OUT',
            'project_id': 999999,
            'project_name': 'Proyek Hantu',
            'total_items': 0,
            'total_qty': 0,
            'total_amount': 0,
            'status': 'Selesai',
        })
        before = {t: self.count(t) for t in ['materials', 'projects',
                                             'transactions',
                                             'transaction_items']}
        original_stock = self.stock_of('BES-001')
        ok, msg = database.restore_from_json(broken, mode='replace')
        self.assertFalse(ok)
        self.assertIn('tidak konsisten', msg.lower())
        after = {t: self.count(t) for t in before}
        self.assertEqual(after, before)
        self.assertEqual(self.stock_of('BES-001'), original_stock)
        self.assert_fk_clean()

    def test_07_json_merge_idempoten_dan_barcode_bentrok(self):
        payload = database.backup_to_json()
        before = {t: self.count(t) for t in ['materials', 'projects',
                                             'suppliers', 'transactions',
                                             'transaction_items']}

        ok, msg = database.restore_from_json(payload, mode='merge')
        self.assertTrue(ok, msg)
        self.assertEqual({t: self.count(t) for t in before}, before)

        # Impor ulang tidak boleh menggandakan item transaksi.
        ok, msg = database.restore_from_json(payload, mode='merge')
        self.assertTrue(ok, msg)
        self.assertEqual({t: self.count(t) for t in before}, before)
        self.assert_fk_clean()

        # Material baru dengan barcode milik material lain -> disimpan tanpa barcode.
        conn = database.get_db()
        try:
            barcode = conn.execute(
                "SELECT barcode FROM materials WHERE barcode IS NOT NULL LIMIT 1"
            ).fetchone()['barcode']
        finally:
            conn.close()
        merged = json.loads(json.dumps(payload))
        merged['data']['materials'].append({
            'sku': 'TST-MRG-01',
            'barcode': barcode,
            'name': 'Material Merge Uji',
            'category': 'Alat & K3 Sipil',
            'unit': 'Pcs',
            'stock': 1,
            'min_stock': 0,
            'unit_price': 1000,
        })
        ok, msg = database.restore_from_json(merged, mode='merge')
        self.assertTrue(ok, msg)

        conn = database.get_db()
        try:
            row = conn.execute(
                "SELECT barcode FROM materials WHERE sku = 'TST-MRG-01'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNone(row['barcode'])
            conn.execute("DELETE FROM materials WHERE sku = 'TST-MRG-01'")
            conn.commit()
        finally:
            conn.close()

    def test_08_endpoint_backup_admin(self):
        self.login()
        res = self.client.get('/backup')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Backup', res.data.decode('utf-8'))

        res = self.client.post('/backup/create',
                               data={'csrf_token': self.csrf()},
                               follow_redirects=True)
        self.assertIn('Snapshot database berhasil', res.data.decode('utf-8'))
        backups = database.list_local_backups()
        self.assertTrue(backups)

        res = self.client.get('/backup/download/db')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'application/x-sqlite3')
        self.assertTrue(res.data.startswith(b'SQLite format 3\x00'))
        res.close()

        res = self.client.get('/backup/download/json')
        self.assertEqual(res.status_code, 200)
        payload = json.loads(res.data.decode('utf-8'))
        self.assertEqual(payload['format'], 'alcivil_json_backup')
        res.close()

        filename = database.list_local_backups()[0]['filename']
        res = self.client.get(f'/backup/download/file/{filename}')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.startswith(b'SQLite format 3\x00')
                        or res.data.startswith(b'{'))
        res.close()

        # Path traversal & ekstensi asing harus ditolak.
        self.assertIsNone(alcivil_app._safe_backup_path('../../alcivil.db'))
        self.assertIsNone(alcivil_app._safe_backup_path('evil.txt'))
        res = self.client.get('/backup/download/file/tidak_ada.db',
                              follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        res = self.client.post(f'/backup/delete/{filename}',
                               data={'csrf_token': self.csrf()},
                               follow_redirects=True)
        self.assertIn('telah dihapus', res.data.decode('utf-8'))
        self.assertFalse(
            os.path.exists(os.path.join(database.BACKUP_DIR, filename))
        )

    def test_09_endpoint_import_json_dan_db(self):
        self.login()
        payload = database.backup_to_json()
        original_stock = self.stock_of('BES-001')
        self.mutate()

        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'import_mode': 'replace',
                'backup_file': (BytesIO(json.dumps(payload).encode('utf-8')),
                                'backup.json'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('berhasil diimpor', res.data.decode('utf-8'))
        self.assertEqual(self.stock_of('BES-001'), original_stock)
        self.assertIsNone(self.stock_of('TST-MUT-01'))

        _, snapshot_path = database.backup_to_sqlite()
        original_stock_2 = self.stock_of('BES-002')
        self.mutate()
        with open(snapshot_path, 'rb') as f:
            db_bytes = f.read()
        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'import_mode': 'replace',
                'backup_file': (BytesIO(db_bytes), 'backup.db'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('berhasil dipulihkan dari database',
                      res.data.decode('utf-8'))
        self.assertEqual(self.stock_of('BES-002'), original_stock_2)

        # Ekstensi tidak didukung.
        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'backup_file': (BytesIO(b'catatan'), 'catatan.txt'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('Format file tidak didukung', res.data.decode('utf-8'))

        # JSON rusak.
        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'backup_file': (BytesIO(b'{bukan json'), 'rusak.json'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('bukan format JSON', res.data.decode('utf-8'))

        # File .db yang bukan SQLite.
        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'backup_file': (BytesIO(b'bukan database'), 'rusak.db'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('Gagal memulihkan database',
                      res.data.decode('utf-8'))

    def test_10_restore_lokal_dan_batas_role(self):
        self.login()
        _, snapshot_path = database.backup_to_sqlite()
        filename = os.path.basename(snapshot_path)
        original_stock = self.stock_of('SMN-001')
        self.mutate()

        res = self.client.post(f'/backup/restore/{filename}',
                               data={'csrf_token': self.csrf()},
                               follow_redirects=True)
        self.assertIn('Berhasil memulihkan sistem',
                      res.data.decode('utf-8'))
        self.assertEqual(self.stock_of('SMN-001'), original_stock)
        self.assertIsNone(self.stock_of('TST-MUT-01'))

        res = self.client.post('/backup/restore/tidak_ada.db',
                               data={'csrf_token': self.csrf()},
                               follow_redirects=True)
        self.assertIn('tidak ditemukan', res.data.decode('utf-8'))

        # Operator tidak boleh mengakses fitur backup/migrasi.
        if not database.get_user_by_username('operator_backup'):
            database.create_user('operator_backup', 'OperatorBackup2026!',
                                 role='operator',
                                 display_name='Operator Backup')
        self.login('operator_backup', 'OperatorBackup2026!')
        self.assertEqual(self.client.get('/backup').status_code, 403)
        res = self.client.post('/backup/create',
                               data={'csrf_token': self.csrf()})
        self.assertEqual(res.status_code, 403)

    def test_11_import_mendeteksi_isi_file_bukan_namanya(self):
        """Backup valid harus diterima walau ekstensi hilang/tertukar (WebView Android)."""
        self.login()
        payload = database.backup_to_json()
        json_bytes = json.dumps(payload).encode('utf-8')

        _, snapshot_path = database.backup_to_sqlite()
        with open(snapshot_path, 'rb') as f:
            db_bytes = f.read()
        self.assertTrue(db_bytes.startswith(b'SQLite format 3\x00'))

        cases = [
            ('backup_tanpa_ekstensi', json_bytes),
            ('content', db_bytes),
            ('data_tertukar.db', json_bytes),
            ('data_tertukar.json', db_bytes),
        ]
        for name, content in cases:
            with self.subTest(name=name):
                res = self.client.post(
                    '/backup/import',
                    data={
                        'csrf_token': self.csrf(),
                        'import_mode': 'replace',
                        'backup_file': (BytesIO(content), name),
                    },
                    content_type='multipart/form-data',
                    follow_redirects=True,
                )
                html = res.data.decode('utf-8')
                self.assertTrue(
                    'berhasil diimpor' in html
                    or 'berhasil dipulihkan dari database' in html,
                    f"{name} ditolak: {html[:300]}"
                )

        # File kosong dan file sampah tetap harus ditolak dengan pesan jelas.
        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'backup_file': (BytesIO(b''), 'kosong.db'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('kosong (0 byte)', res.data.decode('utf-8'))

        res = self.client.post(
            '/backup/import',
            data={
                'csrf_token': self.csrf(),
                'backup_file': (BytesIO(b'bukan backup'), 'sampah'),
            },
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertIn('Format file tidak didukung',
                      res.data.decode('utf-8'))

    def test_12_unduhan_berisi_halaman_login_ditolak_jelas(self):
        """Regresi: DownloadManager Android tanpa cookie menyimpan halaman login."""
        self.login()
        html_page = (b'<!DOCTYPE html><html><head><title>Login</title></head>'
                     b'<body><form>Masuk ke Sistem</form></body></html>')

        for name in ('AL-CIVIL_Database.db', 'AL-CIVIL_Backup.json'):
            with self.subTest(name=name):
                res = self.client.post(
                    '/backup/import',
                    data={
                        'csrf_token': self.csrf(),
                        'backup_file': (BytesIO(html_page), name),
                    },
                    content_type='multipart/form-data',
                    follow_redirects=True,
                )
                self.assertIn('halaman HTML', res.data.decode('utf-8'))

        # Validator level database juga harus menjelaskan penyebabnya.
        html_path = os.path.join(self.tmpdir, 'login_page.db')
        with open(html_path, 'wb') as f:
            f.write(html_page)
        ok, msg = database.validate_sqlite_backup(html_path)
        self.assertFalse(ok)
        self.assertIn('HTML/login', msg)

        # Tanpa sesi, endpoint unduh memang mengembalikan halaman login (HTML),
        # bukan file SQLite — inilah yang dulu tersimpan oleh DownloadManager.
        with self.client.session_transaction() as sess:
            sess.clear()
        res = self.client.get('/backup/download/db', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Masuk ke Sistem', res.data)
        self.assertFalse(res.data.startswith(b'SQLite format 3\x00'))


if __name__ == '__main__':
    unittest.main()

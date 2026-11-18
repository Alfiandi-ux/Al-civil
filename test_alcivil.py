import os
import sys
import tempfile
import unittest

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

if __name__ == '__main__':
    unittest.main()

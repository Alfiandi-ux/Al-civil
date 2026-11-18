"""
AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
Server Lokal - Modul Utama Aplikasi Flask
"""
import os
import csv
import hmac
import io
import json
import math
import secrets
import sqlite3
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, flash, Response,
    send_from_directory, send_file, session, g, abort
)
import database

# Muat konfigurasi dari file .env bila tersedia (opsional).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_secret_key():
    """Ambil SECRET_KEY dari env, atau simpan kunci acak di file lokal.

    Kunci yang persisten membuat sesi login tidak terputus setiap server
    di-restart, tanpa perlu menulis rahasia ke repositori Git.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_path = os.path.join(BASE_DIR, '.secret_key')
    try:
        if os.path.exists(key_path):
            with open(key_path, 'r', encoding='utf-8') as f:
                key = f.read().strip()
            if key:
                return key
        key = secrets.token_hex(32)
        with open(key_path, 'w', encoding='utf-8') as f:
            f.write(key)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return key
    except Exception:
        return secrets.token_hex(32)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = _load_secret_key()
app.config.update(
    MAX_CONTENT_LENGTH=int(os.environ.get('MAX_UPLOAD_MB', '64')) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SECURE_COOKIES', 'false').lower() in ('1', 'true'),
    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=int(os.environ.get('SESSION_HOURS', '12'))
    ),
    CSRF_ENABLED=os.environ.get('CSRF_ENABLED', 'true').lower() not in ('0', 'false', 'no'),
)

# SQLite hanya mengizinkan satu penulis pada satu waktu. Lock ini membuat
# pembuatan nomor dokumen + insert transaksi berjalan atomik di dalam proses,
# sehingga dua request bersamaan tidak menghasilkan nomor dokumen yang sama.
tx_write_lock = threading.Lock()

# Endpoint yang hanya boleh diakses administrator.
ADMIN_ENDPOINTS = {
    'backup_view', 'backup_create', 'backup_download_db', 'backup_download_json',
    'backup_download_file', 'backup_import', 'backup_restore_local', 'backup_delete_local',
    'users_view', 'user_create', 'user_reset_password', 'user_toggle_active',
}

# Pembatasan percobaan login (in-memory, cukup untuk server lokal).
LOGIN_FAILURES = {}
LOGIN_LOCK = threading.Lock()
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 8

def _client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'local').split(',')[0].strip()

def _login_blocked(ip):
    now = time.time()
    with LOGIN_LOCK:
        attempts = [t for t in LOGIN_FAILURES.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        LOGIN_FAILURES[ip] = attempts
        return len(attempts) >= LOGIN_MAX_ATTEMPTS

def _record_login_failure(ip):
    with LOGIN_LOCK:
        LOGIN_FAILURES.setdefault(ip, []).append(time.time())

def _clear_login_failures(ip):
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(ip, None)

def get_csrf_token():
    """Ambil/buat token CSRF untuk sesi saat ini."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

def _safe_next(target):
    """Hanya izinkan redirect internal (cegah open redirect)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith('/'):
        return None
    return target

def _wants_json():
    return request.path.startswith('/api/') or request.is_json

@app.before_request
def load_logged_in_user():
    g.user = None
    user_id = session.get('user_id')
    if not user_id:
        return
    user = database.get_user_by_id(user_id)
    if not user or not user.get('is_active'):
        session.clear()
        return
    g.user = user

@app.before_request
def security_guard():
    endpoint = request.endpoint
    # Aset statis dan health-check Android tetap dapat diakses tanpa login.
    if endpoint in ('static', 'system_status', 'manifest', 'service_worker'):
        return

    # --- Proteksi CSRF untuk semua request yang mengubah data ---
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if app.config.get('CSRF_ENABLED', True):
            sent = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            expected = session.get('csrf_token', '')
            if not expected or not sent or not hmac.compare_digest(str(sent), str(expected)):
                message = "Sesi keamanan tidak valid atau sudah kedaluwarsa. Muat ulang halaman lalu coba lagi."
                if _wants_json():
                    return jsonify({'success': False, 'message': message}), 400
                flash(message, "danger")
                return redirect(url_for('login') if not g.user else url_for('dashboard'))

    # --- Wajib login ---
    if endpoint == 'login':
        if g.user:
            return redirect(url_for('dashboard'))
        return
    if not g.user:
        if _wants_json():
            return jsonify({'success': False, 'message': 'Silakan login terlebih dahulu.'}), 401
        return redirect(url_for('login', next=request.path if request.method == 'GET' else None))

    # --- Paksa ganti sandi default ---
    if g.user.get('must_change_password') and endpoint not in (
        'account', 'change_password', 'logout', 'static', 'login'
    ):
        if _wants_json():
            return jsonify({
                'success': False,
                'message': 'Ganti password default terlebih dahulu melalui menu Akun.'
            }), 403
        return redirect(url_for('account'))

    # --- Otorisasi role ---
    if endpoint in ADMIN_ENDPOINTS and g.user.get('role') != 'admin':
        abort(403)

# Initialize database on startup
with app.app_context():
    database.init_db()

# Custom template filter for Indonesian currency and date formatting
@app.template_filter('rupiah')
def rupiah_format(value):
    try:
        val = float(value or 0)
        return f"Rp {val:,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "Rp 0"

@app.template_filter('datetime_id')
def datetime_format(value):
    if not value:
        return "-"
    try:
        # SQLite CURRENT_TIMESTAMP menyimpan waktu UTC. Tampilkan dalam zona
        # waktu perangkat (WIB pada Termux Android) agar jam surat jalan benar.
        dt = datetime.fromisoformat(str(value).strip().replace(' ', 'T'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone()
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return str(value)

def parse_money(value, field='Nilai'):
    """Parse uang menjadi Decimal 2 desimal; tolak NaN/Infinity/negatif."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} harus berupa angka yang valid.")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} harus berupa angka 0 atau lebih.")
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def parse_quantity(value, field='Kuantitas', allow_negative=False):
    """Parse kuantitas menjadi Decimal 3 desimal; tolak NaN/Infinity."""
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} harus berupa angka yang valid.")
    if not qty.is_finite():
        raise ValueError(f"{field} tidak valid.")
    if not allow_negative and qty <= 0:
        raise ValueError(f"{field} harus lebih dari 0.")
    if allow_negative and qty < 0:
        raise ValueError(f"{field} tidak boleh negatif.")
    return qty.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

def money_float(value):
    return float(parse_money(value))

@app.context_processor
def inject_global_data():
    # BUG-03 FIX: Gunakan try/finally agar koneksi selalu ditutup meski terjadi error
    critical_count = 0
    conn = None
    try:
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 1 AND stock <= min_stock")
        critical_count = cursor.fetchone()[0]
    except Exception:
        critical_count = 0
    finally:
        if conn is not None:
            conn.close()
    user = g.get('user')
    return {
        'app_name': 'AL-CIVIL',
        'app_tagline': 'Civil & Construction Warehouse System',
        'critical_count': critical_count,
        'current_year': datetime.now().year,
        'csrf_token': get_csrf_token,
        'current_user': user,
        'is_admin': bool(user and user.get('role') == 'admin'),
    }

# ==========================================
# AUTENTIKASI & MANAJEMEN AKUN
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = _safe_next(request.args.get('next') or request.form.get('next'))
    if request.method == 'POST':
        ip = _client_ip()
        if _login_blocked(ip):
            flash("Terlalu banyak percobaan login. Tunggu 5 menit lalu coba lagi.", "danger")
            return render_template('login.html', next_url=next_url), 429

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = database.authenticate(username, password)
        if not user:
            _record_login_failure(ip)
            flash("Username atau password salah.", "danger")
            return render_template('login.html', next_url=next_url), 401

        _clear_login_failures(ip)
        session.clear()
        session['user_id'] = user['id']
        session.permanent = True
        get_csrf_token()
        database.touch_last_login(user['id'])

        if user.get('must_change_password'):
            flash("Demi keamanan, ganti password default Anda terlebih dahulu.", "warning")
            return redirect(url_for('account'))
        return redirect(next_url or url_for('dashboard'))

    return render_template('login.html', next_url=next_url)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash("Anda telah keluar dari sistem.", "success")
    return redirect(url_for('login'))

@app.route('/account')
def account():
    return render_template('account.html')

@app.route('/account/password', methods=['POST'])
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not database.authenticate(g.user['username'], current_password):
        flash("Password saat ini tidak sesuai.", "danger")
        return redirect(url_for('account'))
    if len(new_password) < 8:
        flash("Password baru minimal 8 karakter.", "danger")
        return redirect(url_for('account'))
    if new_password != confirm_password:
        flash("Konfirmasi password baru tidak cocok.", "danger")
        return redirect(url_for('account'))
    if new_password == current_password:
        flash("Password baru harus berbeda dari password saat ini.", "danger")
        return redirect(url_for('account'))

    ok, message = database.set_user_password(g.user['id'], new_password, must_change_password=0)
    if ok:
        flash("Password berhasil diperbarui.", "success")
        return redirect(url_for('dashboard'))
    flash(message, "danger")
    return redirect(url_for('account'))

@app.route('/users')
def users_view():
    return render_template('users.html', users=database.list_users(),
                           default_username=database.DEFAULT_ADMIN_USERNAME)

@app.route('/users/create', methods=['POST'])
def user_create():
    username = request.form.get('username', '').strip()
    display_name = request.form.get('display_name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'operator').strip().lower()

    if not username or not (3 <= len(username) <= 32) or not username.replace('_', '').replace('.', '').replace('-', '').isalnum():
        flash("Username harus 3-32 karakter (huruf, angka, titik, garis bawah, atau strip).", "danger")
        return redirect(url_for('users_view'))
    if len(password) < 8:
        flash("Password minimal 8 karakter.", "danger")
        return redirect(url_for('users_view'))
    if role not in ('admin', 'operator'):
        flash("Role tidak valid.", "danger")
        return redirect(url_for('users_view'))

    ok, message = database.create_user(username, password, role, display_name)
    flash(message, "success" if ok else "danger")
    return redirect(url_for('users_view'))

@app.route('/users/<int:user_id>/password', methods=['POST'])
def user_reset_password(user_id):
    new_password = request.form.get('new_password', '')
    if len(new_password) < 8:
        flash("Password baru minimal 8 karakter.", "danger")
        return redirect(url_for('users_view'))
    ok, message = database.set_user_password(user_id, new_password, must_change_password=1)
    flash(message, "success" if ok else "danger")
    return redirect(url_for('users_view'))

@app.route('/users/<int:user_id>/toggle', methods=['POST'])
def user_toggle_active(user_id):
    if user_id == g.user['id']:
        flash("Anda tidak dapat menonaktifkan akun sendiri.", "danger")
        return redirect(url_for('users_view'))
    activate = request.form.get('action') == 'activate'
    ok, message = database.set_user_active(user_id, activate)
    flash(message, "success" if ok else "danger")
    return redirect(url_for('users_view'))

# ==========================================
# DASHBOARD
# ==========================================
@app.route('/')
@app.route('/dashboard')
def dashboard():
    conn = database.get_db()
    cursor = conn.cursor()

    # KPI 1: Total SKUs (hanya material aktif, arsip tidak dihitung)
    cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 1")
    total_sku = cursor.fetchone()[0]

    # KPI 2: Total Nilai Aset Gudang (Rp)
    cursor.execute("SELECT SUM(stock * unit_price) FROM materials WHERE is_active = 1")
    total_asset_val = cursor.fetchone()[0] or 0

    # KPI 3: Total Transaksi Hari Ini
    # created_at disimpan SQLite dalam UTC, jadi konversi dulu ke waktu lokal
    # agar transaksi dini hari (00:00-07:00 WIB) tidak terhitung di hari sebelumnya.
    cursor.execute(
        "SELECT COUNT(*) FROM transactions "
        "WHERE DATE(created_at, 'localtime') = DATE('now', 'localtime')"
    )
    today_transactions = cursor.fetchone()[0]

    # KPI 4: Stok Kritis / Menipis (<= min_stock)
    cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 1 AND stock <= min_stock")
    total_critical = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM materials WHERE is_active = 1 AND stock <= min_stock ORDER BY (stock / (min_stock + 0.001)) ASC LIMIT 6")
    critical_items = [dict(row) for row in cursor.fetchall()]

    # Recent Transactions
    cursor.execute("""
        SELECT t.*, 
            (SELECT COUNT(*) FROM transaction_items ti WHERE ti.transaction_id = t.id) as item_count
        FROM transactions t
        ORDER BY t.created_at DESC LIMIT 8
    """)
    recent_transactions = [dict(row) for row in cursor.fetchall()]

    # Categories Summary
    cursor.execute("""
        SELECT category, COUNT(*) as item_count, SUM(stock) as total_qty, SUM(stock * unit_price) as category_val
        FROM materials
        WHERE is_active = 1
        GROUP BY category
        ORDER BY category_val DESC
    """)
    categories = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('dashboard.html',
                           total_sku=total_sku,
                           total_asset_val=total_asset_val,
                           today_transactions=today_transactions,
                           total_critical=total_critical,
                           critical_items=critical_items,
                           recent_transactions=recent_transactions,
                           categories=categories)

# ==========================================
# MODE TRANSAKSI CEPAT (QUICK TRANSACTION)
# ==========================================
@app.route('/transaksi-cepat')
def quick_transaction():
    conn = database.get_db()
    cursor = conn.cursor()

    # Projects for dropdown
    cursor.execute("SELECT * FROM projects WHERE status = 'Aktif' ORDER BY name ASC")
    projects = [dict(row) for row in cursor.fetchall()]

    # Suppliers for dropdown
    cursor.execute("SELECT * FROM suppliers ORDER BY name ASC")
    suppliers = [dict(row) for row in cursor.fetchall()]

    # Frequently used materials for instant quick buttons
    cursor.execute("SELECT * FROM materials WHERE is_active = 1 ORDER BY stock DESC LIMIT 12")
    popular_materials = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('quick_transaction.html',
                           projects=projects,
                           suppliers=suppliers,
                           popular_materials=popular_materials)

# ==========================================
# INVENTORY / MASTER BARANG
# ==========================================
@app.route('/inventory')
def inventory():
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip()

    conn = database.get_db()
    cursor = conn.cursor()

    where_clauses = ["1=1"]
    params = []

    # Material yang diarsipkan hanya tampil saat filter "archived" dipilih.
    if status_filter == 'archived':
        where_clauses.append("is_active = 0")
    else:
        where_clauses.append("is_active = 1")

    if search:
        where_clauses.append("(name LIKE ? OR sku LIKE ? OR barcode LIKE ? OR location LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term, term])

    if category:
        where_clauses.append("category = ?")
        params.append(category)

    if status_filter == 'critical':
        where_clauses.append("stock <= min_stock")
    elif status_filter == 'safe':
        where_clauses.append("stock > min_stock")

    where_sql = " AND ".join(where_clauses)

    # Pagination: batasi jumlah baris agar halaman tetap ringan di HP.
    per_page = 100
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    count_query = f"SELECT COUNT(*) FROM materials WHERE {where_sql}"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    total_pages = max(1, math.ceil(total_count / per_page))
    page = min(page, total_pages)

    query = f"SELECT * FROM materials WHERE {where_sql} ORDER BY category ASC, name ASC LIMIT ? OFFSET ?"
    cursor.execute(query, params + [per_page, (page - 1) * per_page])
    materials = [dict(row) for row in cursor.fetchall()]

    # Daftar kategori mengikuti status yang sedang dilihat agar filter tetap relevan
    category_flag = 0 if status_filter == 'archived' else 1
    cursor.execute(
        "SELECT DISTINCT category FROM materials WHERE is_active = ? ORDER BY category ASC",
        (category_flag,)
    )
    categories = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 1")
    active_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM materials WHERE is_active = 0")
    archived_count = cursor.fetchone()[0]

    conn.close()
    return render_template('inventory.html',
                           materials=materials,
                           categories=categories,
                           active_count=active_count,
                           archived_count=archived_count,
                           search=search,
                           current_category=category,
                           status_filter=status_filter,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count)

@app.route('/material/save', methods=['POST'])
def save_material():
    material_id = request.form.get('id')
    sku = request.form.get('sku', '').strip().upper()
    barcode = request.form.get('barcode', '').strip() or None
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    unit = request.form.get('unit', '').strip()
    location = request.form.get('location', '').strip() or 'Gudang Utama'
    specification = request.form.get('specification', '').strip()

    # BUG-09 FIX: Validasi field wajib di sisi server
    if not sku or not name or not category or not unit:
        flash("Gagal: SKU, Nama, Kategori, dan Satuan tidak boleh kosong!", "danger")
        return redirect(url_for('inventory'))

    try:
        stock = float(parse_quantity(request.form.get('stock', 0), 'Stok Awal',
                                     allow_negative=True))
        min_stock = float(parse_quantity(request.form.get('min_stock', 10),
                                         'Batas Stok Minimal', allow_negative=True))
        unit_price = float(parse_money(request.form.get('unit_price', 0),
                                       'Harga Satuan'))
    except (ValueError, TypeError) as e:
        flash(f"Gagal: {e}", "danger")
        return redirect(url_for('inventory'))

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        if material_id:
            # Stok TIDAK boleh diubah dari form master. Semua koreksi stok wajib
            # lewat Stock Opname agar tercatat di audit trail.
            cursor.execute("""
                UPDATE materials
                SET sku = ?, barcode = ?, name = ?, category = ?, unit = ?,
                    min_stock = ?, unit_price = ?, location = ?,
                    specification = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (sku, barcode, name, category, unit, min_stock, unit_price,
                  location, specification, material_id))
            flash(
                f"Material {name} berhasil diperbarui. Perubahan stok hanya "
                "melalui menu Stock Opname.",
                "success"
            )
        else:
            cursor.execute("""
                INSERT INTO materials (sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification))
            flash(f"Material {name} ({sku}) berhasil ditambahkan!", "success")
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Gagal: SKU atau Barcode tersebut sudah dipakai material lain!", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menyimpan material: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('inventory'))

@app.route('/material/delete/<int:material_id>', methods=['POST'])
def delete_material(material_id):
    """Hapus material.

    Material tanpa riwayat dihapus permanen. Material yang sudah punya
    transaksi / audit stok akan diarsipkan (soft delete) agar foreign key
    dan dokumen lama tetap utuh.
    """
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT m.id, m.name, m.sku, m.stock,
                   (SELECT COUNT(*) FROM transaction_items ti WHERE ti.material_id = m.id) AS tx_count,
                   (SELECT COUNT(*) FROM stock_adjustments sa WHERE sa.material_id = m.id) AS adj_count
            FROM materials m
            WHERE m.id = ?
        """, (material_id,))
        mat = cursor.fetchone()

        if not mat:
            conn.rollback()
            flash("Material tidak ditemukan (mungkin sudah dihapus).", "danger")
        elif mat['tx_count'] or mat['adj_count']:
            cursor.execute("""
                UPDATE materials
                SET is_active = 0, archived_at = CURRENT_TIMESTAMP
                WHERE id = ? AND is_active = 1
            """, (material_id,))
            conn.commit()
            msg = (
                f"Material {mat['name']} ({mat['sku']}) diarsipkan karena sudah "
                "dipakai pada riwayat transaksi/audit stok. Data historis tetap aman."
            )
            if mat['stock'] and float(mat['stock']) != 0:
                msg += f" Stok tersisa {mat['stock']:g} — gunakan Stock Opname bila perlu dinolkan."
            flash(msg, "success")
        else:
            cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
            conn.commit()
            flash(f"Material {mat['name']} ({mat['sku']}) berhasil dihapus permanen.", "success")
    except sqlite3.IntegrityError:
        # Fallback: bila constraint tetap terpicu (mis. ada referensi lain),
        # jangan gagalkan user — arsipkan saja.
        conn.rollback()
        try:
            cursor.execute("""
                UPDATE materials
                SET is_active = 0, archived_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (material_id,))
            conn.commit()
            flash(
                "Material tidak dapat dihapus permanen karena masih dirujuk data lain, "
                "sehingga diarsipkan. Riwayat transaksi tetap tersimpan.",
                "success"
            )
        except Exception:
            conn.rollback()
            flash("Material gagal dihapus maupun diarsipkan. Silakan coba lagi.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Tidak dapat menghapus material: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('inventory'))

@app.route('/material/restore/<int:material_id>', methods=['POST'])
def restore_material(material_id):
    """Batalkan arsip material agar kembali muncul di inventaris aktif."""
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE materials
            SET is_active = 1, archived_at = NULL
            WHERE id = ? AND is_active = 0
        """, (material_id,))
        if cursor.rowcount == 0:
            flash("Material tidak ditemukan atau sudah aktif kembali.", "danger")
        else:
            conn.commit()
            flash("Material berhasil dipulihkan ke inventaris aktif.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal memulihkan material: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('inventory', status='archived'))

# ==========================================
# TRANSAKSI & SURAT JALAN
# ==========================================
@app.route('/transaksi')
def transactions():
    filter_type = request.args.get('type', '').strip()
    search = request.args.get('search', '').strip()

    conn = database.get_db()
    cursor = conn.cursor()

    where_clauses = ["1=1"]
    params = []

    if filter_type:
        where_clauses.append("t.type = ?")
        params.append(filter_type)

    if search:
        where_clauses.append("(t.transaction_number LIKE ? OR t.project_name LIKE ? OR t.vehicle_number LIKE ? OR t.driver_name LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s, s])

    where_sql = " AND ".join(where_clauses)

    per_page = 50
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1

    count_query = f"SELECT COUNT(*) FROM transactions t WHERE {where_sql}"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    total_pages = max(1, math.ceil(total_count / per_page))
    page = min(page, total_pages)

    query = f"""
        SELECT t.*, 
               (SELECT COUNT(*) FROM transaction_items ti WHERE ti.transaction_id = t.id) as item_count
        FROM transactions t
        WHERE {where_sql}
        ORDER BY t.created_at DESC LIMIT ? OFFSET ?
    """
    cursor.execute(query, params + [per_page, (page - 1) * per_page])
    tx_list = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('transactions.html', transactions=tx_list,
                           filter_type=filter_type, search=search,
                           page=page, total_pages=total_pages,
                           total_count=total_count)

@app.route('/slip/<int:tx_id>')
def view_slip(tx_id):
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    tx = cursor.fetchone()
    if not tx:
        conn.close()
        flash("Transaksi tidak ditemukan!", "danger")
        return redirect(url_for('transactions'))

    tx_dict = dict(tx)

    cursor.execute("SELECT * FROM transaction_items WHERE transaction_id = ? ORDER BY id ASC", (tx_id,))
    items = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('slip.html', tx=tx_dict, items=items)

# ==========================================
# PROYEK & VENDOR MANAGEMENT
# ==========================================
@app.route('/projects')
def projects():
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    projects_list = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM suppliers ORDER BY created_at DESC")
    suppliers_list = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('projects.html', projects=projects_list, suppliers=suppliers_list)

@app.route('/project/save', methods=['POST'])
def save_project():
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    client = request.form.get('client', '').strip()
    location = request.form.get('location', '').strip()
    contact_person = request.form.get('contact_person', '').strip()

    if not code or not name:
        flash("Gagal: Kode dan Nama proyek wajib diisi!", "danger")
        return redirect(url_for('projects'))

    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO projects (code, name, client, location, contact_person)
            VALUES (?, ?, ?, ?, ?)
        """, (code, name, client, location, contact_person))
        conn.commit()
        flash(f"Proyek '{name}' berhasil didaftarkan!", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f"Gagal: Kode proyek '{code}' sudah digunakan!", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menambahkan proyek: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

@app.route('/project/update', methods=['POST'])
def update_project():
    project_id = request.form.get('id')
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    client = request.form.get('client', '').strip()
    location = request.form.get('location', '').strip()
    contact_person = request.form.get('contact_person', '').strip()

    if not project_id or not code or not name:
        flash("Gagal: Kode dan Nama proyek wajib diisi!", "danger")
        return redirect(url_for('projects'))

    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE projects SET code=?, name=?, client=?, location=?, contact_person=?
            WHERE id=?
        """, (code, name, client, location, contact_person, project_id))
        if cursor.rowcount == 0:
            conn.rollback()
            flash("Proyek tidak ditemukan (mungkin sudah dihapus).", "danger")
        else:
            conn.commit()
            flash(f"Proyek '{name}' berhasil diperbarui!", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f"Gagal: Kode proyek '{code}' sudah digunakan proyek lain!", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal memperbarui proyek: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

@app.route('/project/delete/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        flash("Proyek berhasil dihapus.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menghapus proyek: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

@app.route('/supplier/update', methods=['POST'])
def update_supplier():
    supplier_id = request.form.get('id')
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not supplier_id or not code or not name:
        flash("Gagal: Kode dan Nama supplier wajib diisi!", "danger")
        return redirect(url_for('projects'))

    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE suppliers SET code=?, name=?, category=?, phone=?, address=?
            WHERE id=?
        """, (code, name, category, phone, address, supplier_id))
        if cursor.rowcount == 0:
            conn.rollback()
            flash("Supplier tidak ditemukan (mungkin sudah dihapus).", "danger")
        else:
            conn.commit()
            flash(f"Supplier '{name}' berhasil diperbarui!", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f"Gagal: Kode supplier '{code}' sudah digunakan vendor lain!", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal memperbarui supplier: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

@app.route('/supplier/delete/<int:supplier_id>', methods=['POST'])
def delete_supplier(supplier_id):
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        conn.commit()
        flash("Supplier berhasil dihapus.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menghapus supplier: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

@app.route('/supplier/save', methods=['POST'])
def save_supplier():
    code = request.form.get('code', '').strip().upper()
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not code or not name:
        flash("Gagal: Kode dan Nama supplier wajib diisi!", "danger")
        return redirect(url_for('projects'))

    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO suppliers (code, name, category, phone, address)
            VALUES (?, ?, ?, ?, ?)
        """, (code, name, category, phone, address))
        conn.commit()
        flash(f"Supplier '{name}' berhasil didaftarkan!", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f"Gagal: Kode supplier '{code}' sudah digunakan!", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menambahkan supplier: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('projects'))

# ==========================================
# STOCK OPNAME / AUDIT FISIK
# ==========================================
@app.route('/stock-opname')
def stock_opname():
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM materials WHERE is_active = 1 ORDER BY name ASC")
    materials = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT sa.*, m.name as material_name, m.sku, m.unit
        FROM stock_adjustments sa
        JOIN materials m ON sa.material_id = m.id
        ORDER BY sa.created_at DESC LIMIT 50
    """)
    adjustments = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('stock_opname.html', materials=materials, adjustments=adjustments)

@app.route('/stock-opname/save', methods=['POST'])
def save_stock_opname():
    # BUG: int()/float() langsung pada input form menyebabkan HTTP 500 bila
    # field kosong atau dimanipulasi. Validasi dulu dan beri pesan yang jelas.
    try:
        material_id = int(request.form.get('material_id', '').strip())
    except (TypeError, ValueError):
        flash("Gagal: Pilih material yang akan diaudit terlebih dahulu!", "danger")
        return redirect(url_for('stock_opname'))

    try:
        new_stock_dec = parse_quantity(request.form.get('new_stock', ''),
                                       'Stok fisik', allow_negative=True)
    except (TypeError, ValueError) as e:
        flash(f"Gagal: {e}", "danger")
        return redirect(url_for('stock_opname'))

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash("Gagal: Alasan penyesuaian wajib diisi!", "danger")
        return redirect(url_for('stock_opname'))
    if len(reason) > 500:
        flash("Gagal: Alasan penyesuaian maksimal 500 karakter.", "danger")
        return redirect(url_for('stock_opname'))

    adjusted_by = request.form.get('adjusted_by', '').strip() or 'Auditor Lapangan AL-CIVIL'

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        # Baca stok lama DI DALAM lock supaya dua opname bersamaan tidak
        # menghitung selisih dari nilai stok yang sudah basi.
        with tx_write_lock:
            cursor.execute(
                "SELECT stock, name, sku, unit FROM materials "
                "WHERE id = ? AND is_active = 1",
                (material_id,)
            )
            mat = cursor.fetchone()
            if not mat:
                conn.rollback()
                flash("Material tidak valid atau sudah diarsipkan!", "danger")
                return redirect(url_for('stock_opname'))

            old_stock_dec = Decimal(str(mat['stock']))
            new_stock = float(new_stock_dec)
            old_stock = mat['stock']
            diff_dec = (new_stock_dec - old_stock_dec).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
            diff = float(diff_dec)

            # Update Material Stock
            cursor.execute("""
                UPDATE materials
                SET stock = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_stock, material_id))

            # Insert Audit Log
            cursor.execute("""
                INSERT INTO stock_adjustments (material_id, old_stock, new_stock, difference, reason, adjusted_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (material_id, old_stock, new_stock, diff, reason, adjusted_by))

            # Also create adjustment transaction
            tx_num = database.generate_transaction_number('ADJUST', cursor)
            cursor.execute("""
                INSERT INTO transactions (
                    transaction_number, type, operator_name, total_items, total_qty, notes
                ) VALUES (?, 'ADJUST', ?, 1, ?, ?)
            """, (tx_num, adjusted_by, abs(diff), f"Audit Stok: {reason} (Selisih {diff:+.2f})"))

            tx_id = cursor.lastrowid
            # Simpan SKU & satuan asli agar dokumen penyesuaian tidak kosong.
            cursor.execute("""
                INSERT INTO transaction_items (transaction_id, material_id, sku, material_name, unit, qty, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tx_id, material_id, mat['sku'], mat['name'], mat['unit'], diff, reason))

            conn.commit()

        flash(f"Stok {mat['name']} berhasil disesuaikan dari {old_stock} menjadi {new_stock}!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal memproses penyesuaian: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('stock_opname'))

# ==========================================
# EXPORT DATA (CSV)
# ==========================================
@app.route('/export/materials.csv')
def export_materials():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, barcode, name, category, unit, stock, min_stock, unit_price, (stock * unit_price) as total_val, location, specification FROM materials WHERE is_active = 1 ORDER BY category, name")
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['SKU', 'Barcode', 'Nama Material', 'Kategori', 'Satuan', 'Stok Saat Ini', 'Stok Minimal', 'Harga Satuan (Rp)', 'Total Nilai (Rp)', 'Lokasi Rak/Yard', 'Spesifikasi Teknis'])
    for r in rows:
        cw.writerow(list(r))

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)

    filename = f"AL-CIVIL_Inventaris_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@app.route('/export/transactions.csv')
def export_transactions():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.transaction_number, t.type, t.created_at, t.project_name, t.supplier_name,
               t.vehicle_number, t.driver_name, t.total_items, t.total_qty, t.total_amount, t.notes
        FROM transactions t
        ORDER BY t.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['No Transaksi / SJ', 'Tipe', 'Tanggal', 'Proyek Tujuan', 'Supplier', 'No Kendaraan', 'Nama Mandor', 'Jumlah Item', 'Total Qty', 'Total Nilai (Rp)', 'Catatan'])
    for r in rows:
        cw.writerow(list(r))

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)

    filename = f"AL-CIVIL_Transaksi_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

# ==========================================
# BACKUP & RESTORE DATA (MIGRASI SERVER / TERMUX)
# ==========================================
def _detect_backup_kind(file, ext):
    """Deteksi jenis backup dari isi file, dengan ekstensi sebagai cadangan.

    WebView Android kadang mengirim nama file sementara tanpa ekstensi,
    sehingga isi file harus diperiksa agar backup valid tetap diterima.
    """
    try:
        head = file.stream.read(4096)
        file.stream.seek(0)
    except Exception:
        return None

    head = head.lstrip(b'\xef\xbb\xbf \t\r\n')
    if head.startswith(b'SQLite format 3\x00'):
        return 'db'
    if head.startswith(b'{') or head.startswith(b'['):
        return 'json'
    if head.startswith(b'<'):
        return 'html'

    if ext in ('.db', '.sqlite', '.sqlite3'):
        return 'db'
    if ext == '.json':
        return 'json'
    return None


def _safe_backup_path(filename):
    """Kembalikan path backup hanya jika berada di dalam folder backups/."""
    safe_name = secure_filename(filename)
    if not safe_name or not (safe_name.endswith('.db') or safe_name.endswith('.json')):
        return None
    filepath = os.path.realpath(os.path.join(database.BACKUP_DIR, safe_name))
    if os.path.dirname(filepath) != os.path.realpath(database.BACKUP_DIR):
        return None
    if not os.path.isfile(filepath):
        return None
    return filepath, safe_name

@app.route('/backup')
def backup_view():
    stats = database.get_database_stats()
    backups = database.list_local_backups()
    return render_template('backup.html', stats=stats, backups=backups)

@app.route('/backup/create', methods=['POST'])
def backup_create():
    try:
        with tx_write_lock:
            filename, path = database.backup_to_sqlite()
        flash(f"✅ Snapshot database berhasil dibuat di server: {filename}", "success")
    except Exception as e:
        flash(f"⚠️ Gagal membuat backup: {str(e)}", "danger")
    return redirect(url_for('backup_view'))

@app.route('/backup/download/db')
def backup_download_db():
    try:
        with tx_write_lock:
            filename, filepath = database.backup_to_sqlite()
        download_name = f"AL-CIVIL_Database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        return send_file(
            filepath,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/x-sqlite3"
        )
    except Exception as e:
        flash(f"⚠️ Gagal mengunduh file database: {str(e)}", "danger")
        return redirect(url_for('backup_view'))

@app.route('/backup/download/json')
def backup_download_json():
    try:
        with tx_write_lock:
            payload = database.backup_to_json()
        output = io.BytesIO()
        output.write(json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))
        output.seek(0)
        filename = f"AL-CIVIL_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            output.getvalue(),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )
    except Exception as e:
        flash(f"⚠️ Gagal mengekspor data JSON: {str(e)}", "danger")
        return redirect(url_for('backup_view'))

@app.route('/backup/download/file/<filename>')
def backup_download_file(filename):
    resolved = _safe_backup_path(filename)
    if not resolved:
        flash("⚠️ File backup tidak ditemukan di server.", "danger")
        return redirect(url_for('backup_view'))
    filepath, safe_name = resolved
    mimetype = "application/x-sqlite3" if safe_name.endswith('.db') else "application/json"
    return send_file(
        filepath,
        as_attachment=True,
        download_name=safe_name,
        mimetype=mimetype
    )

@app.route('/backup/import', methods=['POST'])
def backup_import():
    file = request.files.get('backup_file')
    if not file:
        flash("⚠️ Silakan pilih file backup (.db atau .json) yang ingin diimpor.", "danger")
        return redirect(url_for('backup_view'))

    filename = secure_filename(file.filename or '')
    ext = os.path.splitext(filename)[1].lower()

    try:
        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
    except Exception:
        file_size = None
    if file_size == 0:
        app.logger.warning("Impor backup ditolak: file kosong (nama=%r)", filename)
        flash("⚠️ File yang dipilih kosong (0 byte). Pilih ulang file backup.", "danger")
        return redirect(url_for('backup_view'))

    # Deteksi jenis backup dari isi file. Pemilih file Android/WebView kadang
    # memberi nama sementara tanpa ekstensi (mis. "content"), sehingga backup
    # yang sah tidak boleh ditolak hanya karena ekstensinya hilang.
    kind = _detect_backup_kind(file, ext)
    if kind is None:
        app.logger.warning(
            "Impor backup ditolak: nama=%r ekstensi=%r (isi tidak dikenali)",
            filename, ext
        )
        flash(
            "⚠️ Format file tidak didukung! Gunakan file .db atau .json hasil "
            "backup AL-CIVIL (isi file tidak dikenali).",
            "danger"
        )
        return redirect(url_for('backup_view'))

    if kind == 'html':
        app.logger.warning(
            "Impor backup ditolak: nama=%r berisi HTML (kemungkinan halaman login)",
            filename
        )
        flash(
            "⚠️ File yang dipilih berisi halaman HTML/login, bukan data backup. "
            "Unduh ulang backup dari menu Backup (pastikan masih login), lalu "
            "impor file hasil unduhan yang baru.",
            "danger"
        )
        return redirect(url_for('backup_view'))

    import_mode = request.form.get('import_mode', 'replace')
    if import_mode not in ('replace', 'merge'):
        import_mode = 'replace'

    if kind == 'db':
        temp_path = os.path.join(
            database.BACKUP_DIR,
            f"temp_upload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{secrets.token_hex(4)}.db"
        )
        try:
            file.save(temp_path)
            with tx_write_lock:
                success, msg = database.restore_from_sqlite(temp_path)
            if success:
                flash(
                    f"🎉 AL-CIVIL berhasil dipulihkan dari database! {msg} "
                    "Disarankan restart server agar seluruh koneksi memakai database baru.",
                    "success"
                )
            else:
                flash(f"⚠️ Gagal memulihkan database: {msg}", "danger")
        except Exception as e:
            flash(f"⚠️ Terjadi kesalahan saat memproses file: {str(e)}", "danger")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    else:
        try:
            content = file.read().decode('utf-8-sig')
            payload = json.loads(content)
            with tx_write_lock:
                success, msg = database.restore_from_json(payload, mode=import_mode)
            if success:
                flash(f"🎉 Data JSON berhasil diimpor ke sistem! ({import_mode}) {msg}", "success")
            else:
                flash(f"⚠️ Gagal mengimpor JSON: {msg}", "danger")
        except json.JSONDecodeError:
            flash("⚠️ File bukan format JSON yang valid.", "danger")
        except Exception as e:
            flash(f"⚠️ Terjadi kesalahan saat mengimpor JSON: {str(e)}", "danger")

    return redirect(url_for('backup_view'))

@app.route('/backup/restore/<filename>', methods=['POST'])
def backup_restore_local(filename):
    resolved = _safe_backup_path(filename)
    if not resolved:
        flash("⚠️ File backup lokal tidak ditemukan.", "danger")
        return redirect(url_for('backup_view'))
    filepath, safe_name = resolved

    if safe_name.endswith('.db'):
        with tx_write_lock:
            success, msg = database.restore_from_sqlite(filepath)
    elif safe_name.endswith('.json'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            with tx_write_lock:
                success, msg = database.restore_from_json(payload, mode='replace')
        except Exception as e:
            success, msg = False, str(e)
    else:
        success, msg = False, "Tipe file tidak dikenali."

    if success:
        flash(
            f"🎉 Berhasil memulihkan sistem dari backup lokal: {safe_name}. "
            "Disarankan restart server.",
            "success"
        )
    else:
        flash(f"⚠️ Gagal restore: {msg}", "danger")

    return redirect(url_for('backup_view'))

@app.route('/backup/delete/<filename>', methods=['POST'])
def backup_delete_local(filename):
    safe_name = secure_filename(filename)
    success, msg = database.delete_local_backup(safe_name)
    if success:
        flash(f"🗑️ File backup {safe_name} telah dihapus.", "success")
    else:
        flash(f"⚠️ Gagal menghapus file: {msg}", "danger")
    return redirect(url_for('backup_view'))

# ==========================================
# REST API (FOR AJAX & FAST TRANSACTION MODE)
# ==========================================
@app.route('/api/materials/search')
def api_search_materials():
    q = request.args.get('q', '').strip()
    conn = database.get_db()
    cursor = conn.cursor()
    if q:
        term = f"%{q}%"
        cursor.execute("""
            SELECT id, sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification
            FROM materials
            WHERE is_active = 1 AND (name LIKE ? OR sku LIKE ? OR barcode = ?)
            ORDER BY name ASC
            LIMIT 20
        """, (term, term, q))
    else:
        cursor.execute("""
            SELECT id, sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification
            FROM materials
            WHERE is_active = 1
            ORDER BY name ASC
            LIMIT 30
        """)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(results)

@app.route('/api/materials/<int:mat_id>')
def api_get_material(mat_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM materials WHERE id = ?", (mat_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({'error': 'Material tidak ditemukan'}), 404

@app.route('/api/transaction/create', methods=['POST'])
def api_create_transaction():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Payload transaksi tidak valid'}), 400

    tx_type = str(data.get('type', 'OUT')).strip().upper()
    if tx_type not in ('IN', 'OUT'):
        return jsonify({'success': False, 'message': 'Jenis transaksi tidak valid'}), 400

    items = data.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'Daftar barang tidak boleh kosong!'}), 400

    def clean(value, default='', limit=500):
        text = str(value).strip() if value is not None else default
        return text[:limit]

    default_operator = (
        (g.user.get('display_name') or g.user.get('username'))
        if g.user else 'Petugas Gudang AL-CIVIL'
    )
    project_id = data.get('project_id') or None
    project_name = clean(data.get('project_name'), limit=200)
    supplier_id = data.get('supplier_id') or None
    supplier_name = clean(data.get('supplier_name'), limit=200)
    vehicle_number = clean(data.get('vehicle_number'), limit=40).upper()
    driver_name = clean(data.get('driver_name'), limit=100)
    operator_name = clean(data.get('operator_name'), default_operator, limit=100) or default_operator
    notes = clean(data.get('notes'), limit=1000)

    # Penerimaan barang (IN) boleh membawa harga beli aktual per item. Bila
    # klien lama tidak mengirim flag ini, default-nya harga master ikut
    # diperbarui (perilaku yang diharapkan pada mode penerimaan).
    update_price_raw = data.get('update_price', True)
    if isinstance(update_price_raw, str):
        update_price = update_price_raw.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        update_price = bool(update_price_raw)

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        # --- Validasi payload item: qty harus > 0 dan material harus ada ---
        normalized_items = []
        materials_by_id = {}
        requested_qty = {}

        if len(items) > 200:
            raise ValueError("Maksimal 200 baris barang per transaksi.")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Format daftar barang tidak valid.")

            try:
                mat_id = int(item.get('material_id'))
            except (TypeError, ValueError, OverflowError):
                raise ValueError("ID material tidak valid.")

            try:
                qty_dec = parse_quantity(item.get('qty'))
            except (TypeError, ValueError) as e:
                raise ValueError(f"Kuantitas barang tidak valid: {e}")
            qty = float(qty_dec)

            if mat_id not in materials_by_id:
                cursor.execute(
                    "SELECT id, sku, name, unit, stock, unit_price FROM materials WHERE id = ? AND is_active = 1",
                    (mat_id,)
                )
                m = cursor.fetchone()
                if not m:
                    raise ValueError(f"Material ID {mat_id} tidak ditemukan atau sudah diarsipkan.")
                materials_by_id[mat_id] = dict(m)

            mat = materials_by_id[mat_id]
            requested_qty[mat_id] = requested_qty.get(mat_id, 0) + qty

            try:
                master_price_dec = parse_money(mat['unit_price'] or 0, 'Harga master')
                # Untuk OUT, harga selalu dari master agar nilai surat jalan tidak
                # bisa dimanipulasi dari browser. Untuk IN, harga beli aktual dari
                # form penerimaan dipakai dan (opsional) disimpan ke master.
                if tx_type == 'IN' and item.get('unit_price') not in (None, ''):
                    unit_price_dec = parse_money(
                        item.get('unit_price'),
                        f"Harga satuan untuk '{mat['name']}'"
                    )
                else:
                    unit_price_dec = master_price_dec
            except (TypeError, ValueError) as e:
                raise ValueError(str(e))

            line_total_dec = (qty_dec * unit_price_dec).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            unit_price = float(unit_price_dec)

            normalized_items.append({
                'material_id': mat_id,
                'sku': mat['sku'],
                'material_name': mat['name'],
                'unit': mat['unit'],
                'qty': qty,
                'qty_dec': qty_dec,
                'unit_price': unit_price,
                'line_total': float(line_total_dec),
                'notes': clean(item.get('notes'), limit=500)
            })

        # --- Validasi tujuan pengiriman / vendor ---
        if tx_type == 'OUT':
            try:
                project_id = int(project_id)
            except (TypeError, ValueError):
                raise ValueError("Proyek tujuan pengiriman wajib dipilih.")
            cursor.execute("SELECT name FROM projects WHERE id = ?", (project_id,))
            project_row = cursor.fetchone()
            if not project_row:
                raise ValueError("Proyek tujuan tidak ditemukan. Muat ulang halaman lalu coba lagi.")
            # Nama proyek selalu diambil dari database, bukan dari payload browser.
            project_name = project_row['name']
            supplier_id, supplier_name = None, ''

            # Cek stok agregat (bila material yang sama muncul lebih dari sekali)
            for mat_id, qty in requested_qty.items():
                mat = materials_by_id[mat_id]
                if mat['stock'] < qty:
                    raise ValueError(
                        f"Stok untuk '{mat['name']}' tidak mencukupi! "
                        f"Tersedia: {mat['stock']}, Diminta: {qty}"
                    )
        else:
            try:
                supplier_id = int(supplier_id)
            except (TypeError, ValueError):
                raise ValueError("Vendor / supplier penerimaan wajib dipilih.")
            cursor.execute("SELECT name FROM suppliers WHERE id = ?", (supplier_id,))
            supplier_row = cursor.fetchone()
            if not supplier_row:
                raise ValueError("Vendor / supplier tidak ditemukan. Muat ulang halaman lalu coba lagi.")
            supplier_name = supplier_row['name']
            project_id, project_name = None, ''

        total_items_count = len(normalized_items)
        total_qty_dec = sum((i['qty_dec'] for i in normalized_items), Decimal('0'))
        total_amount_dec = sum(
            (Decimal(str(i['line_total'])) for i in normalized_items), Decimal('0')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_qty = float(total_qty_dec.quantize(Decimal('0.001')))
        total_amount = float(total_amount_dec)

        # Kunci proses tulis supaya nomor dokumen + stok selalu konsisten
        # meskipun ada dua request transaksi bersamaan.
        with tx_write_lock:
            tx_number = database.generate_transaction_number(tx_type, cursor)

            # Insert Transaction
            cursor.execute("""
                INSERT INTO transactions (
                    transaction_number, type, project_id, project_name, supplier_id, supplier_name,
                    vehicle_number, driver_name, operator_name, total_items, total_qty, total_amount, notes, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Selesai')
            """, (
                tx_number, tx_type, project_id, project_name, supplier_id, supplier_name,
                vehicle_number, driver_name, operator_name, total_items_count, total_qty, total_amount, notes
            ))
            tx_id = cursor.lastrowid

            # Insert Items & Update Inventory Stock
            for item in normalized_items:
                mat_id = item['material_id']
                qty = item['qty']
                unit_price = item['unit_price']
                line_total = item['line_total']

                cursor.execute("""
                    INSERT INTO transaction_items (
                        transaction_id, material_id, sku, material_name, unit, qty, unit_price, total_price, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx_id, mat_id, item['sku'], item['material_name'], item['unit'],
                    qty, unit_price, line_total, item['notes']
                ))

                # BUG-01 FIX: Atomic stock update — cegah race condition stok negatif
                if tx_type == 'OUT':
                    cursor.execute("""
                        UPDATE materials
                        SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND stock >= ?
                    """, (qty, mat_id, qty))
                    if cursor.rowcount == 0:
                        raise ValueError(
                            f"Stok material ID {mat_id} tidak mencukupi saat diproses. Silakan coba lagi."
                        )
                else:
                    cursor.execute("""
                        UPDATE materials
                        SET stock = stock + ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (qty, mat_id))

            # Penerimaan (IN): perbarui harga master material ke harga beli
            # aktual yang diisi petugas. Bila material yang sama muncul lebih
            # dari sekali, gunakan rata-rata tertimbang kuantitasnya.
            price_updates = []
            if tx_type == 'IN' and update_price:
                received_qty = {}
                received_value = {}
                for item in normalized_items:
                    mid = item['material_id']
                    received_qty[mid] = received_qty.get(mid, Decimal('0')) + item['qty_dec']
                    received_value[mid] = received_value.get(mid, Decimal('0')) + (
                        item['qty_dec'] * Decimal(str(item['unit_price']))
                    )

                for mid, qty in received_qty.items():
                    if qty <= 0:
                        continue
                    new_price_dec = (received_value[mid] / qty).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                    new_price = float(new_price_dec)
                    old_price = float(materials_by_id[mid]['unit_price'] or 0)
                    if abs(new_price - old_price) < 0.005:
                        continue
                    cursor.execute("""
                        UPDATE materials
                        SET unit_price = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (new_price, mid))
                    price_updates.append({
                        'material_id': mid,
                        'name': materials_by_id[mid]['name'],
                        'old_price': old_price,
                        'new_price': new_price
                    })

            conn.commit()

        message = f"Transaksi {tx_number} berhasil diproses!"
        if tx_type == 'IN' and price_updates:
            message += f" Harga master {len(price_updates)} material diperbarui."

        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'transaction_number': tx_number,
            'slip_url': url_for('view_slip', tx_id=tx_id),
            'price_updates': price_updates,
            'message': message
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        conn.close()

# ==========================================
# PWA & MOBILE SYSTEM ROUTES
# ==========================================
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/api/system-status')
def system_status():
    return jsonify({
        'status': 'online',
        'app': 'AL-CIVIL WMS',
        'platform': 'Android / Termux',
        'timestamp': datetime.now().isoformat()
    })

def start_android_server(port=5000):
    """Fungsi pembantu yang dipanggil dari runtime Java Android (Chaquopy)."""
    with app.app_context():
        database.init_db()
    app.run(host='127.0.0.1', port=int(port), debug=False, threaded=True)

if __name__ == '__main__':
    # Optimized for Android/Termux:
    # debug=False disables CPU-heavy file polling; threaded=True handles concurrent requests
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() in ('true', '1')
    print("=" * 60)
    print("  🏗️ AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM")
    print(f"  Server Lokal Aktif pada http://127.0.0.1:{port}")
    print(f"  Mode: {'DEBUG (Pengembangan)' if debug else 'PRODUKSI (Lancar & Hemat Baterai Android)'}")
    print("  Mode Transaksi Cepat & Barcode Siap Digunakan!")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)

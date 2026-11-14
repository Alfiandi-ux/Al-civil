"""
AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
Server Lokal - Modul Utama Aplikasi Flask
"""
import os
import csv
import io
import json
import sqlite3
import threading
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, flash, Response, send_from_directory, send_file
)
import database

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'al-civil-secret-key-super-secure-termux-2026')

# SQLite hanya mengizinkan satu penulis pada satu waktu. Lock ini membuat
# pembuatan nomor dokumen + insert transaksi berjalan atomik di dalam proses,
# sehingga dua request bersamaan tidak menghasilkan nomor dokumen yang sama.
tx_write_lock = threading.Lock()

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

@app.context_processor
def inject_global_data():
    # BUG-03 FIX: Gunakan try/finally agar koneksi selalu ditutup meski terjadi error
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM materials WHERE stock <= min_stock")
        critical_count = cursor.fetchone()[0]
    except Exception:
        critical_count = 0
    finally:
        conn.close()
    return {
        'app_name': 'AL-CIVIL',
        'app_tagline': 'Civil & Construction Warehouse System',
        'critical_count': critical_count,
        'current_year': datetime.now().year
    }

# ==========================================
# DASHBOARD
# ==========================================
@app.route('/')
@app.route('/dashboard')
def dashboard():
    conn = database.get_db()
    cursor = conn.cursor()

    # KPI 1: Total SKUs
    cursor.execute("SELECT COUNT(*) FROM materials")
    total_sku = cursor.fetchone()[0]

    # KPI 2: Total Nilai Aset Gudang (Rp)
    cursor.execute("SELECT SUM(stock * unit_price) FROM materials")
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
    cursor.execute("SELECT COUNT(*) FROM materials WHERE stock <= min_stock")
    total_critical = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM materials WHERE stock <= min_stock ORDER BY (stock / (min_stock + 0.001)) ASC LIMIT 6")
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
    cursor.execute("SELECT * FROM materials ORDER BY stock DESC LIMIT 12")
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

    query = "SELECT * FROM materials WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ? OR location LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    if category:
        query += " AND category = ?"
        params.append(category)

    if status_filter == 'critical':
        query += " AND stock <= min_stock"
    elif status_filter == 'safe':
        query += " AND stock > min_stock"

    query += " ORDER BY category ASC, name ASC"
    cursor.execute(query, params)
    materials = [dict(row) for row in cursor.fetchall()]

    # List of unique categories for filter
    cursor.execute("SELECT DISTINCT category FROM materials ORDER BY category ASC")
    categories = [row[0] for row in cursor.fetchall()]

    conn.close()
    return render_template('inventory.html',
                           materials=materials,
                           categories=categories,
                           search=search,
                           current_category=category,
                           status_filter=status_filter)

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
        stock = float(request.form.get('stock', 0))
        min_stock = float(request.form.get('min_stock', 10))
        unit_price = float(request.form.get('unit_price', 0))
        if stock < 0 or min_stock < 0 or unit_price < 0:
            raise ValueError("Nilai tidak boleh negatif")
    except (ValueError, TypeError):
        flash("Gagal: Stok, Stok Minimal, dan Harga Satuan harus berupa angka positif!", "danger")
        return redirect(url_for('inventory'))

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        if material_id:
            cursor.execute("""
                UPDATE materials
                SET sku = ?, barcode = ?, name = ?, category = ?, unit = ?,
                    stock = ?, min_stock = ?, unit_price = ?, location = ?,
                    specification = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification, material_id))
            flash(f"Material {name} berhasil diperbarui!", "success")
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
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            flash("Material tidak ditemukan (mungkin sudah dihapus).", "danger")
        else:
            conn.commit()
            flash("Material berhasil dihapus dari inventaris.", "success")
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(
            "Material tidak dapat dihapus karena sudah dipakai pada riwayat "
            "transaksi atau audit stok. Nonaktifkan lewat penyesuaian stok bila perlu.",
            "danger"
        )
    except Exception as e:
        conn.rollback()
        flash(f"Tidak dapat menghapus material: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('inventory'))

# ==========================================
# TRANSAKSI & SURAT JALAN
# ==========================================
@app.route('/transaksi')
def transactions():
    filter_type = request.args.get('type', '').strip()
    search = request.args.get('search', '').strip()

    conn = database.get_db()
    cursor = conn.cursor()

    query = """
        SELECT t.*, 
               (SELECT COUNT(*) FROM transaction_items ti WHERE ti.transaction_id = t.id) as item_count
        FROM transactions t
        WHERE 1=1
    """
    params = []

    if filter_type:
        query += " AND t.type = ?"
        params.append(filter_type)

    if search:
        query += " AND (t.transaction_number LIKE ? OR t.project_name LIKE ? OR t.vehicle_number LIKE ? OR t.driver_name LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s, s])

    query += " ORDER BY t.created_at DESC"
    cursor.execute(query, params)
    tx_list = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('transactions.html', transactions=tx_list, filter_type=filter_type, search=search)

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

    cursor.execute("SELECT * FROM materials ORDER BY name ASC")
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
        new_stock = float(request.form.get('new_stock', ''))
    except (TypeError, ValueError):
        flash("Gagal: Hasil perhitungan fisik harus berupa angka!", "danger")
        return redirect(url_for('stock_opname'))

    if new_stock < 0:
        flash("Gagal: Stok fisik tidak boleh bernilai negatif!", "danger")
        return redirect(url_for('stock_opname'))

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash("Gagal: Alasan penyesuaian wajib diisi!", "danger")
        return redirect(url_for('stock_opname'))

    adjusted_by = request.form.get('adjusted_by', '').strip() or 'Auditor Lapangan AL-CIVIL'

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT stock, name, sku, unit FROM materials WHERE id = ?", (material_id,))
        mat = cursor.fetchone()
        if not mat:
            flash("Material tidak valid!", "danger")
            return redirect(url_for('stock_opname'))

        old_stock = mat['stock']
        diff = new_stock - old_stock

        with tx_write_lock:
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
    cursor.execute("SELECT sku, barcode, name, category, unit, stock, min_stock, unit_price, (stock * unit_price) as total_val, location, specification FROM materials ORDER BY category, name")
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
@app.route('/backup')
def backup_view():
    stats = database.get_database_stats()
    backups = database.list_local_backups()
    return render_template('backup.html', stats=stats, backups=backups)

@app.route('/backup/create', methods=['POST'])
def backup_create():
    try:
        filename, path = database.backup_to_sqlite()
        flash(f"✅ Snapshot database berhasil dibuat di server: {filename}", "success")
    except Exception as e:
        flash(f"⚠️ Gagal membuat backup: {str(e)}", "danger")
    return redirect(url_for('backup_view'))

@app.route('/backup/download/db')
def backup_download_db():
    try:
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
    safe_name = secure_filename(filename)
    filepath = os.path.join(database.BACKUP_DIR, safe_name)
    if not os.path.exists(filepath):
        flash("⚠️ File backup tidak ditemukan di server.", "danger")
        return redirect(url_for('backup_view'))
    mimetype = "application/x-sqlite3" if safe_name.endswith('.db') else "application/json"
    return send_file(
        filepath,
        as_attachment=True,
        download_name=safe_name,
        mimetype=mimetype
    )

@app.route('/backup/import', methods=['POST'])
def backup_import():
    if 'backup_file' not in request.files:
        flash("⚠️ Silakan pilih file backup (.db atau .json) yang ingin diimpor.", "danger")
        return redirect(url_for('backup_view'))

    file = request.files['backup_file']
    if not file or file.filename == '':
        flash("⚠️ Tidak ada file yang dipilih.", "danger")
        return redirect(url_for('backup_view'))

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ['.db', '.sqlite', '.sqlite3', '.json']:
        flash("⚠️ Format file tidak didukung! Gunakan file .db atau .json hasil backup AL-CIVIL.", "danger")
        return redirect(url_for('backup_view'))

    import_mode = request.form.get('import_mode', 'replace')

    if ext in ['.db', '.sqlite', '.sqlite3']:
        temp_path = os.path.join(database.BACKUP_DIR, f"temp_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        try:
            file.save(temp_path)
            success, msg = database.restore_from_sqlite(temp_path)
            if success:
                flash(f"🎉 AL-CIVIL berhasil dipulihkan dari database! {msg}", "success")
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
    elif ext == '.json':
        try:
            content = file.read().decode('utf-8')
            payload = json.loads(content)
            success, msg = database.restore_from_json(payload, mode=import_mode)
            if success:
                flash(f"🎉 Data JSON berhasil diimpor ke sistem! ({import_mode})", "success")
            else:
                flash(f"⚠️ Gagal mengimpor JSON: {msg}", "danger")
        except json.JSONDecodeError:
            flash("⚠️ File bukan format JSON yang valid.", "danger")
        except Exception as e:
            flash(f"⚠️ Terjadi kesalahan saat mengimpor JSON: {str(e)}", "danger")

    return redirect(url_for('backup_view'))

@app.route('/backup/restore/<filename>', methods=['POST'])
def backup_restore_local(filename):
    safe_name = secure_filename(filename)
    filepath = os.path.join(database.BACKUP_DIR, safe_name)
    if not os.path.exists(filepath):
        flash("⚠️ File backup lokal tidak ditemukan.", "danger")
        return redirect(url_for('backup_view'))

    if safe_name.endswith('.db'):
        success, msg = database.restore_from_sqlite(filepath)
    elif safe_name.endswith('.json'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            success, msg = database.restore_from_json(payload, mode='replace')
        except Exception as e:
            success, msg = False, str(e)
    else:
        success, msg = False, "Tipe file tidak dikenali."

    if success:
        flash(f"🎉 Berhasil memulihkan sistem dari backup lokal: {safe_name}", "success")
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
            WHERE name LIKE ? OR sku LIKE ? OR barcode = ?
            ORDER BY name ASC
            LIMIT 20
        """, (term, term, q))
    else:
        cursor.execute("""
            SELECT id, sku, barcode, name, category, unit, stock, min_stock, unit_price, location, specification
            FROM materials
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

    def clean(value, default=''):
        return str(value).strip() if value is not None else default

    project_id = data.get('project_id') or None
    project_name = clean(data.get('project_name'))
    supplier_id = data.get('supplier_id') or None
    supplier_name = clean(data.get('supplier_name'))
    vehicle_number = clean(data.get('vehicle_number')).upper()
    driver_name = clean(data.get('driver_name'))
    operator_name = clean(data.get('operator_name'), 'Petugas Gudang AL-CIVIL') or 'Petugas Gudang AL-CIVIL'
    notes = clean(data.get('notes'))

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        # --- Validasi payload item: qty harus > 0 dan material harus ada ---
        normalized_items = []
        materials_by_id = {}
        requested_qty = {}

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Format daftar barang tidak valid.")

            try:
                mat_id = int(item.get('material_id'))
                qty = float(item.get('qty'))
            except (TypeError, ValueError):
                raise ValueError("ID material atau kuantitas barang tidak valid.")

            if qty <= 0:
                raise ValueError("Kuantitas setiap barang harus lebih dari 0.")

            if mat_id not in materials_by_id:
                cursor.execute(
                    "SELECT id, sku, name, unit, stock, unit_price FROM materials WHERE id = ?",
                    (mat_id,)
                )
                m = cursor.fetchone()
                if not m:
                    raise ValueError(f"Material ID {mat_id} tidak ditemukan.")
                materials_by_id[mat_id] = dict(m)

            mat = materials_by_id[mat_id]
            requested_qty[mat_id] = requested_qty.get(mat_id, 0) + qty

            # Gunakan data master (bukan data kiriman browser) agar dokumen
            # selalu memuat SKU/nama/satuan/harga yang benar.
            normalized_items.append({
                'material_id': mat_id,
                'sku': mat['sku'],
                'material_name': mat['name'],
                'unit': mat['unit'],
                'qty': qty,
                'unit_price': float(mat['unit_price'] or 0),
                'notes': clean(item.get('notes'))
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
            project_name = project_name or project_row['name']
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
            supplier_name = supplier_name or supplier_row['name']
            project_id, project_name = None, ''

        total_items_count = len(normalized_items)
        total_qty = sum(i['qty'] for i in normalized_items)
        total_amount = sum(i['qty'] * i['unit_price'] for i in normalized_items)

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
                line_total = qty * unit_price

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

            conn.commit()

        return jsonify({
            'success': True,
            'transaction_id': tx_id,
            'transaction_number': tx_number,
            'slip_url': url_for('view_slip', tx_id=tx_id),
            'message': f"Transaksi {tx_number} berhasil diproses!"
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

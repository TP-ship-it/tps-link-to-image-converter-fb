from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import string
import random
import os
import time
import uuid
import secrets
import urllib.parse
import requests

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
try:
    from PIL import Image  # type: ignore
except ImportError:  # Pillow not installed; cropping will be skipped
    Image = None

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


UPLOAD_DIR = os.path.join(app.root_path, 'static', 'uploads')
DB_PATH = os.path.join(app.root_path, 'database.db')
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES

# basic secret key for session / CSRF; override with environment variable in production
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)


def _generate_csrf_token() -> str:
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.context_processor
def _inject_csrf_token():
    # usage in templates: {{ csrf_token() }}
    return {'csrf_token': _generate_csrf_token}


@app.before_request
def _csrf_protect():
    # allow safe methods without CSRF
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        return

    # for unsafe methods, require token
    token = None
    if request.form:
        token = request.form.get('csrf_token')

    if not token and request.is_json:
        data = request.get_json(silent=True) or {}
        token = data.get('csrf_token')

    if not token:
        token = request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')

    if not token or token != session.get('_csrf_token'):
        return 'Invalid CSRF token', 400


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_e):
    return 'File too large (max 2MB)', 413


@app.errorhandler(404)
def handle_not_found(_e):
    path = request.path or ''
    try:
        decoded = urllib.parse.unquote(path)
    except Exception:
        decoded = path

    has_thai = any('\u0e00' <= ch <= '\u0e7f' for ch in decoded)
    if has_thai or '%e0%b8' in path.lower():
        return redirect(url_for('upload_page'), code=302)

    return 'Not found', 404


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE IF NOT EXISTS links
                 (slug TEXT PRIMARY KEY, dest_url TEXT, img_url TEXT, title TEXT, description TEXT, card_size TEXT)'''
    )

    c.execute("PRAGMA table_info(links)")
    existing_link_cols = {row[1] for row in c.fetchall()}
    if 'description' not in existing_link_cols:
        c.execute("ALTER TABLE links ADD COLUMN description TEXT")
    if 'card_size' not in existing_link_cols:
        c.execute("ALTER TABLE links ADD COLUMN card_size TEXT")
    if 'site_name' not in existing_link_cols:
        c.execute("ALTER TABLE links ADD COLUMN site_name TEXT")
    if 'button_text' not in existing_link_cols:
        c.execute("ALTER TABLE links ADD COLUMN button_text TEXT")
    if 'og_url' not in existing_link_cols:
        c.execute("ALTER TABLE links ADD COLUMN og_url TEXT")
    c.execute(
        '''CREATE TABLE IF NOT EXISTS images
                 (id TEXT PRIMARY KEY,
                  filename TEXT NOT NULL,
                  content_type TEXT,
                  title TEXT,
                  description TEXT,
                  created_at INTEGER NOT NULL,
                  expires_at INTEGER,
                  delete_token TEXT NOT NULL)'''
    )

    c.execute("PRAGMA table_info(images)")
    existing_cols = {row[1] for row in c.fetchall()}
    if 'title' not in existing_cols:
        c.execute("ALTER TABLE images ADD COLUMN title TEXT")
    if 'description' not in existing_cols:
        c.execute("ALTER TABLE images ADD COLUMN description TEXT")

    conn.commit()
    conn.close()


# Ensure database is initialized even when running under gunicorn / production WSGI
try:
    init_db()
except Exception as e:
    # Fail silently here; detailed errors will appear when endpoints try to use the DB
    print(f"WARNING: init_db() at import time failed: {e}")


def generate_slug(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def insert_link_with_unique_slug_v2(dest_url, img_url, title, description, card_size, site_name=None, button_text=None, og_url=None, attempts=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        for _ in range(attempts):
            slug = generate_slug()
            try:
                c.execute(
                    "INSERT INTO links (slug, dest_url, img_url, title, description, card_size, site_name, button_text, og_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (slug, dest_url, img_url, title, description, card_size, site_name, button_text, og_url),
                )
                conn.commit()
                return slug
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError('Could not generate unique slug')
    finally:
        conn.close()


def _is_allowed_image_filename(filename: str) -> bool:
    _, ext = os.path.splitext(filename or '')
    return ext.lower() in ALLOWED_IMAGE_EXTENSIONS


def _save_uploaded_image(file_storage, slug: str) -> str:
    filename = secure_filename(file_storage.filename or '')
    if not filename or not _is_allowed_image_filename(filename):
        raise ValueError('Invalid image file type')

    content_type = getattr(file_storage, 'mimetype', '') or getattr(file_storage, 'content_type', '')
    if not content_type or not content_type.startswith('image/'):
        raise ValueError('Invalid image file type')

    _, ext = os.path.splitext(filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_name = f"{slug}{ext.lower()}"
    save_path = os.path.join(UPLOAD_DIR, saved_name)
    file_storage.save(save_path)
    return url_for('static', filename=f"uploads/{saved_name}", _external=True)


def _cleanup_expired_images():
    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, filename FROM images WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
    rows = c.fetchall()
    for _id, filename in rows:
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename))
        except FileNotFoundError:
            pass
        c.execute("DELETE FROM images WHERE id=?", (_id,))
    conn.commit()
    conn.close()


def _is_image_not_expired(expires_at) -> bool:
    return (expires_at is None) or (expires_at > int(time.time()))


def _save_uploaded_image_for_image_host(file_storage, image_id: str, offset_y=None) -> tuple[str, str, str]:
    filename = secure_filename(file_storage.filename or '')
    if not filename or not _is_allowed_image_filename(filename):
        raise ValueError('Invalid image file type')

    content_type = getattr(file_storage, 'mimetype', '') or getattr(file_storage, 'content_type', '')
    if not content_type or not content_type.startswith('image/'):
        raise ValueError('Invalid image file type')

    _, ext = os.path.splitext(filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_name = f"{image_id}{ext.lower()}"
    save_path = os.path.join(UPLOAD_DIR, saved_name)
    file_storage.save(save_path)

    # ประมวลผลรูปให้เหมาะกับ Facebook card (รองรับรูปสี่เหลี่ยมจัตุรัส)
    if Image is not None:
        try:
            img = Image.open(save_path)
            w, h = img.size
            img_ratio = w / h if h > 0 else 1.0

            # ใช้อัตราส่วนการ์ดประมาณ 1.91:1 (1200x628)
            target_ratio = 1.91
            target_w = 1200
            target_h = 628

            # ถ้ารูปเป็นสี่เหลี่ยมจัตุรัส (1:1) หรือ portrait (h >= w)
            # ให้ resize แล้วเพิ่ม padding สีดำด้านข้าง
            if img_ratio <= 1.0:
                # resize รูปให้สูงเป็น 628 แล้วคำนวณความกว้าง
                new_h = target_h
                new_w = int(w * (new_h / h))
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # สร้าง canvas ใหม่ขนาด 1200x628 พื้นหลังสีดำ
                canvas = Image.new('RGB', (target_w, target_h), (0, 0, 0))
                # วางรูปตรงกลาง
                paste_x = (target_w - new_w) // 2
                canvas.paste(img_resized, (paste_x, 0))
                img = canvas
            else:
                # รูป landscape: ใช้วิธี crop
                target_h_crop = int(w / target_ratio)
                if target_h_crop > h:
                    target_h_crop = h

                # ถ้ามี offset_y ให้เลื่อน crop ตาม offset
                if offset_y is not None:
                    try:
                        oy = int(offset_y)
                        # เลื่อน crop ตาม offset (positive = รูปเลื่อนลงใน preview -> crop ขึ้น)
                        center_y = h / 2 - oy
                        top = int(center_y - target_h_crop / 2)
                        top = max(0, min(h - target_h_crop, top))
                    except:
                        # ถ้า offset_y ไม่ valid ให้ใช้ตรงกลาง
                        top = (h - target_h_crop) // 2
                else:
                    # ไม่มี offset ให้ใช้ตรงกลาง
                    top = (h - target_h_crop) // 2

                bottom = top + target_h_crop
                img = img.crop((0, top, w, bottom))
                # resize ให้เป็น 1200x628
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            img.save(save_path)
        except Exception:
            # ถ้า crop พลาด ให้ใช้รูปเดิมต่อไป
            pass

    direct_url = url_for('static', filename=f"uploads/{saved_name}", _external=True)
    view_url = url_for('image_view', image_id=image_id, _external=True)
    return saved_name, direct_url, view_url


def _create_grid_image(image_files, overlay_text=None, target_size=(1200, 628)):
    """
    สร้าง Grid Image จากหลายรูป
    image_files: list of PIL Image objects
    overlay_text: ข้อความที่จะวางทับ (เช่น "+9")
    target_size: (width, height) ของรูปสุดท้าย
    """
    if Image is None:
        raise ValueError('Pillow (PIL) is required for grid image generation')

    if not image_files or len(image_files) < 2:
        raise ValueError('Need at least 2 images for grid')

    num_images = len(image_files)
    if num_images > 5:
        num_images = 5
        image_files = image_files[:5]

    # กำหนด Grid layout
    if num_images == 2:
        cols, rows = 2, 1
    elif num_images == 3:
        cols, rows = 3, 1  # 3 รูป: แนวนอน
    elif num_images == 4:
        cols, rows = 2, 2  # 4 รูป: 2x2
    else:  # 5 รูป: 3x2 (3 บน, 2 ล่าง)
        cols, rows = 3, 2

    # คำนวณขนาดแต่ละรูปใน Grid
    grid_w, grid_h = target_size
    cell_w = grid_w // cols
    cell_h = grid_h // rows

    # สร้าง canvas ใหม่
    canvas = Image.new('RGB', target_size, (255, 255, 255))

    # วางรูปใน Grid
    for idx, img in enumerate(image_files[:num_images]):
        # Resize รูปให้พอดีกับ cell
        img_resized = img.resize((cell_w, cell_h), Image.Resampling.LANCZOS)

        # คำนวณตำแหน่ง
        if num_images == 5:
            # 5 รูป: 3 บน, 2 ล่าง (จัดตำแหน่งให้สวย)
            if idx < 3:
                # 3 รูปแรก: แถวบน
                col = idx
                row = 0
            else:
                # 2 รูปสุดท้าย: แถวล่าง (วางตรงกลาง)
                col = idx - 3 + 1  # เริ่มที่ column 1
                row = 1
        else:
            col = idx % cols
            row = idx // cols

        x = col * cell_w
        y = row * cell_h

        # วางรูป
        canvas.paste(img_resized, (x, y))

    # ถ้ามี overlay text ให้วางทับ
    if overlay_text:
        try:
            from PIL import ImageDraw, ImageFont  # type: ignore
            draw = ImageDraw.Draw(canvas)

            # พยายามใช้ฟอนต์ใหญ่
            font_size = 120
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                except:
                    font = ImageFont.load_default()

            # วาดพื้นหลังข้อความ (สี่เหลี่ยมสีขาว)
            bbox = draw.textbbox((0, 0), overlay_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # ตำแหน่งมุมขวาล่าง
            padding = 20
            box_x = grid_w - text_w - padding * 2
            box_y = grid_h - text_h - padding * 2

            # วาดพื้นหลัง
            draw.rectangle(
                [box_x - padding, box_y - padding, box_x + text_w + padding, box_y + text_h + padding],
                fill=(255, 255, 255, 230)
            )

            # วาดข้อความ
            draw.text((box_x, box_y), overlay_text, fill=(0, 0, 0), font=font)
        except Exception:
            # ถ้าวาดข้อความพลาด ให้ข้าม
            pass

    return canvas


@app.route('/')
def index():
    return redirect(url_for('upload_page'), code=302)


@app.route('/generator')
def generator_page():
    return render_template('index.html')


@app.route('/compose')
def compose_page():
    img_url = request.args.get('img_url', '')
    title = request.args.get('title', '')
    description = request.args.get('description', '')
    dest_url = request.args.get('dest_url', '')
    card_size = request.args.get('card_size', 'large')
    site_name = request.args.get('site_name', '')
    button_text = request.args.get('button_text', '')
    og_url = request.args.get('og_url', '')
    
    # Debug logging
    print("=" * 50)
    print("DEBUG: compose_page() called")
    print(f"  img_url: {img_url}")
    print(f"  title: {title}")
    print(f"  description: {description}")
    print(f"  dest_url: {dest_url}")
    print(f"  card_size: {card_size}")
    print(f"  site_name: {site_name}")
    print(f"  button_text: {button_text}")
    print(f"  og_url: {og_url}")
    print("=" * 50)
    
    return render_template(
        'compose.html',
        img_url=img_url,
        title=title,
        description=description,
        dest_url=dest_url,
        card_size=card_size,
        site_name=site_name,
        button_text=button_text,
        og_url=og_url,
    )


@app.route('/upload')
def upload_page():
    _cleanup_expired_images()
    return render_template('upload.html')


@app.route('/api/grid', methods=['POST'])
def api_create_grid():
    _cleanup_expired_images()
    files = request.files.getlist('files')
    overlay_text = (request.form.get('overlay_text') or '').strip()

    if not files or len(files) < 2:
        return {'error': 'Need at least 2 images'}, 400

    if len(files) > 5:
        return {'error': 'Maximum 5 images allowed'}, 400

    image_id = uuid.uuid4().hex
    delete_token = secrets.token_urlsafe(24)

    try:
        # โหลดรูปทั้งหมด
        pil_images = []
        for file_storage in files:
            if not getattr(file_storage, 'filename', ''):
                continue

            filename = secure_filename(file_storage.filename or '')
            if not filename or not _is_allowed_image_filename(filename):
                continue

            content_type = getattr(file_storage, 'mimetype', '') or getattr(file_storage, 'content_type', '')
            if not content_type or not content_type.startswith('image/'):
                continue

            # โหลดรูปด้วย Pillow
            if Image is None:
                return {'error': 'Pillow (PIL) is required for grid image generation'}, 500

            img = Image.open(file_storage)
            # แปลงเป็น RGB ถ้าเป็น RGBA
            if img.mode == 'RGBA':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img = rgb_img
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            pil_images.append(img)

        if len(pil_images) < 2:
            return {'error': 'Need at least 2 valid images'}, 400

        # สร้าง Grid Image
        grid_image = _create_grid_image(pil_images, overlay_text=overlay_text if overlay_text else None)

        # บันทึกรูป
        _, ext = os.path.splitext(secure_filename(files[0].filename or ''))
        if not ext:
            ext = '.jpg'
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        saved_name = f"{image_id}{ext.lower()}"
        save_path = os.path.join(UPLOAD_DIR, saved_name)
        grid_image.save(save_path, 'JPEG', quality=95)

        # บันทึกใน DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO images (id, filename, content_type, title, description, created_at, expires_at, delete_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (image_id, saved_name, 'image/jpeg', '', '', int(time.time()), None, delete_token),
        )
        conn.commit()
        conn.close()

        direct_url = url_for('static', filename=f"uploads/{saved_name}", _external=True)
        view_url = url_for('image_view', image_id=image_id, _external=True)
        delete_url = url_for('api_delete_image', image_id=image_id, _external=True)

        return {
            'id': image_id,
            'direct_url': direct_url,
            'view_url': view_url,
            'delete_url': delete_url,
            'delete_token': delete_token,
        }

    except ValueError as e:
        return {'error': str(e)}, 400
    except Exception as e:
        return {'error': f'Grid creation failed: {str(e)}'}, 500


@app.route('/api/upload', methods=['POST'])
def api_upload():
    _cleanup_expired_images()
    file_storage = request.files.get('file')
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return {'error': 'Missing file'}, 400

    title = (request.form.get('title') or '').strip()
    description = (request.form.get('description') or '').strip()

    expiry_minutes_raw = request.form.get('expiry_minutes')
    expires_at = None
    if expiry_minutes_raw:
        try:
            expiry_minutes = int(expiry_minutes_raw)
            if expiry_minutes > 0:
                expires_at = int(time.time()) + (expiry_minutes * 60)
        except ValueError:
            return {'error': 'Invalid expiry_minutes'}, 400

    image_id = uuid.uuid4().hex
    delete_token = secrets.token_urlsafe(24)

    offset_y_raw = request.form.get('offset_y')
    offset_y_val = None
    if offset_y_raw:
        try:
            offset_y_val = int(offset_y_raw)
        except (TypeError, ValueError):
            offset_y_val = None

    try:
        saved_name, direct_url, view_url = _save_uploaded_image_for_image_host(
            file_storage,
            image_id=image_id,
            offset_y=offset_y_val,
        )
    except ValueError as e:
        return {'error': str(e)}, 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO images (id, filename, content_type, title, description, created_at, expires_at, delete_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (image_id, saved_name, file_storage.mimetype, title, description, int(time.time()), expires_at, delete_token),
    )
    conn.commit()
    conn.close()

    delete_url = url_for('api_delete_image', image_id=image_id, _external=True)
    return {
        'id': image_id,
        'direct_url': direct_url,
        'view_url': view_url,
        'delete_url': delete_url,
        'delete_token': delete_token,
        'expires_at': expires_at,
    }


@app.route('/i/<image_id>')
def image_view(image_id):
    _cleanup_expired_images()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, filename, content_type, title, description, created_at, expires_at, delete_token FROM images WHERE id=?", (image_id,))
    row = c.fetchone()
    conn.close()

    if not row or not _is_image_not_expired(row[6]):
        return 'Image not found', 404

    direct_url = url_for('static', filename=f"uploads/{row[1]}", _external=True)
    view_url = url_for('image_view', image_id=image_id, _external=True)
    title = row[3] or ''
    description = row[4] or ''
    return render_template('image.html', direct_url=direct_url, view_url=view_url, title=title, description=description)


@app.route('/api/images/<image_id>/delete', methods=['POST'])
def api_delete_image(image_id):
    _cleanup_expired_images()
    token = request.form.get('delete_token')
    if not token and request.is_json:
        token = (request.get_json(silent=True) or {}).get('delete_token')

    if not token:
        return {'error': 'Missing delete_token'}, 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, delete_token, expires_at FROM images WHERE id=?", (image_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {'error': 'Not found'}, 404

    filename, delete_token, expires_at = row
    if expires_at is not None and expires_at <= int(time.time()):
        c.execute("DELETE FROM images WHERE id=?", (image_id,))
        conn.commit()
        conn.close()
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename))
        except FileNotFoundError:
            pass
        return {'ok': True}

    if token != delete_token:
        conn.close()
        return {'error': 'Invalid delete_token'}, 403

    c.execute("DELETE FROM images WHERE id=?", (image_id,))
    conn.commit()
    conn.close()
    try:
        os.remove(os.path.join(UPLOAD_DIR, filename))
    except FileNotFoundError:
        pass

    return {'ok': True}


@app.route('/create', methods=['POST'])
def create():
    dest_url = request.form.get('dest_url')
    img_url = request.form.get('img_url')
    title = request.form.get('title')
    description = request.form.get('description') or ''
    card_size = request.form.get('card_size') or ''
    site_name = (request.form.get('site_name') or '').strip()
    button_text = (request.form.get('button_text') or '').strip()
    og_url = (request.form.get('og_url') or '').strip() or None  # Optional: สำหรับตั้งค่า og:url เป็น URL ของ Facebook
    img_file = request.files.get('img_file')
    
    # Debug logging
    print("=" * 50)
    print("DEBUG: create() called")
    print(f"  dest_url: {dest_url}")
    print(f"  img_url: {img_url}")
    print(f"  title: {title}")
    print(f"  description: {description}")
    print(f"  card_size: {card_size}")
    print(f"  site_name: {site_name}")
    print(f"  button_text: {button_text}")
    print(f"  og_url: {og_url}")
    print(f"  img_file: {img_file}")
    print("=" * 50)

    if not dest_url or not title:
        return 'Missing required fields', 400

    if (not img_url) and (not img_file or not getattr(img_file, 'filename', '')):
        return 'Missing image (provide image URL or upload a file)', 400

    slug = insert_link_with_unique_slug_v2(
        dest_url=dest_url,
        img_url=img_url or '',
        title=title,
        description=description,
        card_size=card_size,
        site_name=site_name or None,
        button_text=button_text or None,
        og_url=og_url,
    )

    final_img_url = img_url or ''

    if img_file and getattr(img_file, 'filename', ''):
        try:
            saved_url = _save_uploaded_image(img_file, slug=slug)
        except ValueError as e:
            return str(e), 400

        final_img_url = saved_url

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE links SET img_url=? WHERE slug=?", (saved_url, slug))
        conn.commit()
        conn.close()

    full_link = f"{request.host_url}{slug}"
    return render_template(
        'result.html',
        full_link=full_link,
        title=title,
        description=description,
        dest_url=dest_url,
        img_url=final_img_url,
        card_size=card_size,
        site_name=site_name,
        button_text=button_text,
    )


@app.route('/<slug>')
def redirect_handler(slug):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM links WHERE slug=?", (slug,))
    link = c.fetchone()
    conn.close()

    if link:
        user_agent = request.headers.get('User-Agent', '').lower()
        # Meta crawlers (2024+) may use: meta-externalagent / meta-externalfetcher
        # Keep list permissive so social previews always see OG tags.
        is_bot = any(
            bot in user_agent
            for bot in [
                'facebookexternalhit',
                'facebot',
                'meta-externalagent',
                'meta-externalfetcher',
                'twitterbot',
                'linkedinbot',
                'slackbot',
                'whatsapp',
                'telegrambot',
            ]
        )

        if is_bot:
            # แปลง img_url เป็น absolute URL ถ้ายังไม่ใช่
            img_url = link[2] or ''
            if img_url and not img_url.startswith(('http://', 'https://')):
                # ถ้าเป็น relative URL ให้แปลงเป็น absolute URL
                if img_url.startswith('/'):
                    img_url = f"{request.scheme}://{request.host}{img_url}"
                else:
                    img_url = f"{request.host_url.rstrip('/')}/{img_url.lstrip('/')}"
            
            site_name = (link[6] if len(link) > 6 and link[6] else None)
            og_url = (link[8] if len(link) > 8 and link[8] else None)  # og_url สำหรับตั้งค่า og:url
            
            # ถ้ามี og_url ให้ใช้แทน request.base_url (สำหรับหลอก Facebook ให้คิดว่าเป็นลิงก์ของ Facebook)
            display_url = og_url if og_url else request.base_url
            
            # Debug logging
            print("=" * 50)
            print("DEBUG: redirect_handler() - Bot detected")
            print(f"  slug: {slug}")
            print(f"  title: {link[3]}")
            print(f"  description: {link[4]}")
            print(f"  img_url: {img_url}")
            print(f"  url: {request.base_url}")
            print(f"  og_url: {og_url}")
            print(f"  display_url: {display_url}")
            print(f"  dest_url: {link[1]}")
            print(f"  site_name: {site_name}")
            print(f"  card_size: {link[5]}")
            print(f"  button_text: {link[7] if len(link) > 7 else None}")
            print("=" * 50)
            
            return render_template(
                'meta.html',
                title=link[3],
                description=(link[4] or ''),
                img=img_url,
                url=display_url,  # og:url - ถ้ามี og_url ให้ใช้แทน (สำหรับหลอก Facebook)
                dest_url=link[1],  # สำหรับ JavaScript redirect (user จะถูก redirect ไปที่นี่)
                site_name=site_name,  # og:site_name จะแสดงแทนชื่อโดเมน
                card_size=link[5] or 'large',
                button_text=(link[7] if len(link) > 7 and link[7] else None),
            )
        else:
            return redirect(link[1], code=302)

    return 'Link not found', 404


@app.route('/api/create-facebook-post', methods=['POST'])
def create_facebook_post_api():
    """
    API endpoint สำหรับสร้าง Facebook Post พร้อมปุ่ม CTA
    
    ต้องการ parameters:
    - page_id: Facebook Page ID
    - page_access_token: Page Access Token
    - slug: Slug ของลิงก์ที่สร้างไว้แล้ว
    - message: ข้อความโพสต์ (optional)
    - cta_type: ประเภทปุ่ม CTA (LEARN_MORE, SHOP_NOW, SIGN_UP, etc.) (optional, default: LEARN_MORE)
    - published: True/False (optional, default: True)
    """
    try:
        data = request.get_json()
        
        page_id = data.get('page_id')
        page_access_token = data.get('page_access_token')
        slug = data.get('slug')
        message = data.get('message', '')
        cta_type = data.get('cta_type', 'LEARN_MORE')
        published = data.get('published', True)
        
        if not page_id or not page_access_token or not slug:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: page_id, page_access_token, slug'
            }), 400
        
        # ดึงข้อมูลลิงก์จาก database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM links WHERE slug=?", (slug,))
        link = c.fetchone()
        conn.close()
        
        if not link:
            return jsonify({
                'success': False,
                'error': 'Link not found'
            }), 404
        
        # สร้าง URL ของลิงก์
        link_url = f"{request.host_url.rstrip('/')}/{slug}"
        
        # ถ้าไม่มี message ให้ใช้ title
        if not message:
            message = link[3] or 'Check this out!'
        
        # สร้าง Facebook Post พร้อมปุ่ม CTA
        api_version = "v18.0"
        url = f"https://graph.facebook.com/{api_version}/{page_id}/feed"
        
        params = {
            "message": message,
            "link": link_url,
            "call_to_action": {
                "type": cta_type,
                "value": {
                    "link": link_url
                }
            },
            "published": published,
            "access_token": page_access_token
        }
        
        response = requests.post(url, json=params)
        response.raise_for_status()
        result = response.json()
        
        return jsonify({
            'success': True,
            'post_id': result.get('id'),
            'link_url': link_url,
            'data': result
        })
        
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", {}).get("message", error_msg)
            except:
                pass
        
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    init_db()
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=debug, port=port)

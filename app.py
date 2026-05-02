from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, session, redirect, Response
import os, json, uuid, io, sqlite3, time, subprocess, tempfile, shutil, platform
from werkzeug.utils import secure_filename
from functools import wraps

IS_WINDOWS = platform.system() == 'Windows'

app = Flask(__name__)
app.secret_key = 'reel_generator_secret_2024'

UPLOAD_FOLDER    = 'static/uploads'
MUSIC_FOLDER     = 'static/music'
VOICE_FOLDER     = 'static/voice'
TEMPLATES_FOLDER = 'static/templates_store'
ALLOWED_IMAGE    = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_AUDIO    = {'mp3', 'wav', 'ogg', 'm4a'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MUSIC_FOLDER,  exist_ok=True)
os.makedirs(VOICE_FOLDER,  exist_ok=True)

DB_PATH = 'database.db'

# ══════════════════════════════════════════════════════════════════
# SQLite helpers
# ══════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS templates (
        id TEXT PRIMARY KEY, file TEXT, name TEXT,
        thumbnail TEXT, category TEXT, active INTEGER DEFAULT 1,
        html_content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS music (
        id TEXT PRIMARY KEY, name TEXT, url TEXT,
        duration TEXT DEFAULT "—", start REAL DEFAULT 0, end REAL,
        music_data BLOB, mime_type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT, template TEXT,
        images TEXT, text TEXT, music TEXT, created REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)''')
    for k, v in [('app_name','Caryanams'),('admin_username','admin'),('admin_password','admin123')]:
        c.execute('INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)', (k,v))
    c.execute('SELECT COUNT(*) FROM templates')
    if c.fetchone()[0] == 0:
        _seed_templates(c)
    # Migration: add html_content column if it doesn't exist
    try:
        c.execute('ALTER TABLE templates ADD COLUMN html_content TEXT')
        conn.commit()
    except:
        pass
    # Migration: add music_data and mime_type columns if not exist
    for col_sql in [
        'ALTER TABLE music ADD COLUMN music_data BLOB',
        'ALTER TABLE music ADD COLUMN mime_type TEXT'
    ]:
        try:
            c.execute(col_sql)
            conn.commit()
        except:
            pass
    conn.commit(); conn.close()

def _seed_templates(c):
    NAMES = {1:'Auto Velocity',2:'Cinematic Loop',3:'Clickable Fade',4:'Pixel Flash',
             5:'Full Fill Slide',6:'PPT Exit',7:'Dynamic Motion',8:'Wipe Motion',
             9:'Clean Split',10:'Curtain Show',11:'Blinds Effect',12:'Fixed Box',
             13:'Rotate FX',14:'Advanced PPT',15:'Diamond Show',16:'Fixed 15 PPT',
             17:'5 Image Dynamic',18:'7 Image Dynamic',19:'8 Image Push',
             20:'8 Image Cover',21:'9 Image FX'}
    def cat(i):
        if i in [1,7,8,13]: return 'Motion'
        if i in [2,5,9,15]: return 'Cinematic'
        if i in [6,14,16,17,18,19,20,21]: return 'PPT Style'
        return 'Creative'
    for i in range(1,22):
        c.execute('INSERT OR IGNORE INTO templates (id,file,name,thumbnail,category,active) VALUES (?,?,?,?,?,1)',
            (f'tem{i}',f'tem{i}.html',NAMES[i],f'/static/thumbnails/tem{i}.jpg',cat(i)))

def migrate_json_to_sqlite():
    if not os.path.exists('db.json'): return
    try:
        with open('db.json') as f: old = json.load(f)
        conn = get_db(); c = conn.cursor()
        for t in old.get('templates',[]):
            c.execute('INSERT OR IGNORE INTO templates (id,file,name,thumbnail,category,active) VALUES (?,?,?,?,?,?)',
                (t['id'],t['file'],t['name'],t.get('thumbnail',''),t.get('category','Creative'),1 if t.get('active',True) else 0))
        for m in old.get('music',[]):
            c.execute('INSERT OR IGNORE INTO music (id,name,url,duration,start,end) VALUES (?,?,?,?,?,?)',
                (m['id'],m['name'],m['url'],str(m.get('duration','—')),m.get('start',0),m.get('end')))
        for p in old.get('projects',[]):
            c.execute('INSERT OR IGNORE INTO projects (id,name,template,images,text,music,created) VALUES (?,?,?,?,?,?,?)',
                (p['id'],p.get('name','Untitled'),p.get('template'),json.dumps(p.get('images',[])),
                 json.dumps(p.get('text',{})),json.dumps(p.get('music')),p.get('created',time.time())))
        for k,v in old.get('settings',{}).items():
            c.execute('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)',(k,str(v)))
        conn.commit(); conn.close()
        os.rename('db.json','db.json.migrated')
        print('[DB] Migrated db.json → SQLite')
    except Exception as e:
        print(f'[DB] Migration error: {e}')

def get_setting(key, default=''):
    conn = get_db()
    row = conn.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)',(key,str(value)))
    conn.commit(); conn.close()

def _allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in allowed

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'): return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════════
# TTS — gTTS (Google Text-to-Speech) — works on Render, no system deps
# ══════════════════════════════════════════════════════════════════

# gTTS language map (lang code → gTTS tld/lang)
GTTS_LANG_MAP = {
    'hi-IN': ('hi', 'com'),
    'en-IN': ('en', 'co.in'),
    'gu-IN': ('gu', 'com'),
    'mr-IN': ('mr', 'com'),
    'pa-IN': ('pa', 'com'),
    'ta-IN': ('ta', 'com'),
    'te-IN': ('te', 'com'),
    'kn-IN': ('kn', 'com'),
    'bn-IN': ('bn', 'com'),
    'ml-IN': ('ml', 'com'),
    'or-IN': ('or', 'com'),
    'ne-IN': ('ne', 'com'),
    'ur-IN': ('ur', 'com'),
    'en-US': ('en', 'com'),
    'en-GB': ('en', 'co.uk'),
    'fr-FR': ('fr', 'com'),
    'de-DE': ('de', 'com'),
    'es-ES': ('es', 'com'),
    'ar-SA': ('ar', 'com'),
    'ja-JP': ('ja', 'com'),
    'zh-CN': ('zh-CN', 'com'),
}

def _try_gtts(text, lang_code, slow=False):
    """
    Try gTTS (Google TTS). Returns mp3 bytes or None.
    gTTS calls Google Translate TTS API — needs internet on Render (which it has).
    """
    try:
        from gtts import gTTS
        lang, tld = GTTS_LANG_MAP.get(lang_code, ('hi', 'com'))
        tts = gTTS(text=text, lang=lang, tld=tld, slow=slow)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        data = buf.read()
        if len(data) > 500:
            print(f'[TTS] ✅ gTTS success — {len(data)} bytes, lang={lang}, tld={tld}')
            return data
        print('[TTS] gTTS returned empty audio')
        return None
    except Exception as e:
        print(f'[TTS] gTTS failed: {e}')
        return None

def _try_google_translate_tts(text, lang_code, slow=False):
    """
    Direct Google Translate TTS API call (same as browser uses).
    Fallback if gTTS library fails.
    """
    try:
        import urllib.request
        lang_short = GTTS_LANG_MAP.get(lang_code, (lang_code.split('-')[0], 'com'))[0]
        # Split text into chunks (GT TTS max ~200 chars)
        chunks = []
        words = text.split()
        cur = ''
        for w in words:
            if len(cur) + len(w) + 1 > 180:
                if cur: chunks.append(cur.strip())
                cur = w
            else:
                cur = (cur + ' ' + w).strip()
        if cur: chunks.append(cur)
        if not chunks: chunks = [text[:180]]

        all_bytes = b''
        for chunk in chunks:
            import urllib.parse
            url = (
                f'https://translate.googleapis.com/translate_tts'
                f'?ie=UTF-8&q={urllib.parse.quote(chunk)}'
                f'&tl={urllib.parse.quote(lang_short)}'
                f'&total=1&idx=0&textlen={len(chunk)}'
                f'&client=gtx&prev=input'
            )
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Caryanams/1.0)'
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                chunk_bytes = resp.read()
                if len(chunk_bytes) > 100:
                    all_bytes += chunk_bytes

        if len(all_bytes) > 500:
            print(f'[TTS] ✅ Google Translate TTS fallback — {len(all_bytes)} bytes')
            return all_bytes
        return None
    except Exception as e:
        print(f'[TTS] Google Translate TTS fallback failed: {e}')
        return None

@app.route('/api/tts/check', methods=['GET'])
def tts_check():
    """Check if server-side TTS is available."""
    try:
        import gtts
        return jsonify({'server_tts': True, 'engine': 'gTTS'})
    except ImportError:
        return jsonify({'server_tts': True, 'engine': 'google-translate-api'})

@app.route('/api/tts', methods=['POST'])
def generate_tts():
    data      = request.get_json(force=True)
    text      = (data.get('text') or '').strip()
    lang_code = data.get('lang', 'hi-IN')
    slow      = bool(data.get('slow', False))

    if not text:
        return jsonify({'error': 'Text required'}), 400

    print(f'[TTS] Request: lang={lang_code}, slow={slow}, text_len={len(text)}')

    # ── METHOD 1: gTTS library ────────────────────────────────────
    audio_data = _try_gtts(text, lang_code, slow)

    # ── METHOD 2: Direct Google Translate API ────────────────────
    if not audio_data:
        audio_data = _try_google_translate_tts(text, lang_code, slow)

    # ── All methods failed ────────────────────────────────────────
    if not audio_data:
        print('[TTS] All server methods failed — telling browser to use SpeechSynthesis')
        return jsonify({
            'use_browser': True,
            'text': text,
            'lang': lang_code,
            'error': 'Server TTS unavailable — browser fallback'
        }), 202

    # ── Success: return MP3 bytes ─────────────────────────────────
    # Encode translated text safely for header
    try:
        translated_header = text.encode('utf-8').decode('latin-1', errors='replace')
    except Exception:
        translated_header = ''

    return Response(
        audio_data,
        mimetype='audio/mpeg',
        headers={
            'Content-Disposition': 'inline; filename="voice.mp3"',
            'Cache-Control': 'no-cache',
            'Content-Length': str(len(audio_data)),
            'X-Translated-Text': translated_header,
        }
    )

# ══════════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════════

@app.route('/')
def index(): return render_template('index.html')

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if (request.form.get('username') == get_setting('admin_username','admin') and
                request.form.get('password') == get_setting('admin_password','admin123')):
            session['admin_logged_in'] = True
            return redirect('/admin')
        return render_template('admin_login.html', error='Invalid credentials')
    return render_template('admin_login.html', error=None)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None); return redirect('/admin/login')

@app.route('/admin')
@admin_required
def admin(): return render_template('admin.html')

# ══════════════════════════════════════════════════════════════════
# TEMPLATES API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/templates', methods=['GET'])
def get_templates():
    conn = get_db()
    rows = conn.execute('SELECT * FROM templates WHERE active=1').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/templates/add', methods=['POST'])
def add_template():
    data = request.json; tid = f'custom_{uuid.uuid4().hex[:6]}'
    conn = get_db()
    html_content = data.get('html_content','')
    conn.execute('INSERT INTO templates (id,file,name,thumbnail,category,active,html_content) VALUES (?,?,?,?,?,1,?)',
        (tid,data.get('file',''),data.get('name','Custom Template'),data.get('thumbnail',''),data.get('category','Custom'),html_content))
    conn.commit()
    row = conn.execute('SELECT * FROM templates WHERE id=?',(tid,)).fetchone()
    conn.close(); return jsonify({'success':True,'template':dict(row)})

@app.route('/api/templates/<tid>', methods=['GET'])
def get_template_html(tid):
    fpath = os.path.join(TEMPLATES_FOLDER, f'{tid}.html')
    if os.path.exists(fpath):
        return send_from_directory(TEMPLATES_FOLDER, f'{tid}.html')
    conn = get_db()
    row = conn.execute('SELECT html_content FROM templates WHERE id=?', (tid,)).fetchone()
    conn.close()
    if row and row['html_content']:
        return Response(row['html_content'], mimetype='text/html')
    return jsonify({'error':f'Template {tid} not found'}),404

@app.route('/api/templates/<tid>/toggle', methods=['POST'])
def toggle_template(tid):
    conn = get_db()
    conn.execute('UPDATE templates SET active=1-active WHERE id=?',(tid,))
    conn.commit(); conn.close(); return jsonify({'success':True})

@app.route('/api/templates/<tid>', methods=['DELETE'])
def delete_template(tid):
    conn = get_db()
    conn.execute('DELETE FROM templates WHERE id=?',(tid,))
    conn.commit(); conn.close(); return jsonify({'success':True})

# ══════════════════════════════════════════════════════════════════
# UPLOAD API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/upload/images', methods=['POST'])
def upload_images():
    files = request.files.getlist('images')
    sid = request.form.get('session_id', uuid.uuid4().hex)
    sdir = os.path.join(UPLOAD_FOLDER, sid); os.makedirs(sdir, exist_ok=True)
    uploaded = []
    for f in files:
        if f and _allowed_file(f.filename, ALLOWED_IMAGE):
            fn = secure_filename(f.filename); uid = f'{uuid.uuid4().hex[:8]}_{fn}'
            f.save(os.path.join(sdir, uid))
            uploaded.append({'name':fn,'url':f'/static/uploads/{sid}/{uid}'})
    return jsonify({'success':True,'images':uploaded,'session_id':sid})

@app.route('/api/upload/music', methods=['POST'])
def upload_music():
    f = request.files.get('music')
    if not f or not _allowed_file(f.filename, ALLOWED_AUDIO): return jsonify({'error':'Invalid file'}),400
    fn = secure_filename(f.filename)
    uid = f'{uuid.uuid4().hex[:8]}_{fn}'
    file_data = f.read()
    mime = f.mimetype or 'audio/mpeg'
    mid = uuid.uuid4().hex[:8]
    conn = get_db()
    conn.execute('INSERT INTO music (id,name,url,duration,start,end,music_data,mime_type) VALUES (?,?,?,?,?,?,?,?)',
        (mid, fn, f'/api/music/{mid}/file', '—', 0, None, file_data, mime))
    conn.commit()
    conn.close()
    try:
        os.makedirs(MUSIC_FOLDER, exist_ok=True)
        with open(os.path.join(MUSIC_FOLDER, uid), 'wb') as out:
            out.write(file_data)
    except Exception:
        pass
    return jsonify({'success':True,'url':f'/api/music/{mid}/file','name':fn,'id':mid})

@app.route('/api/music/<mid>/file', methods=['GET'])
def serve_music_file(mid):
    conn = get_db()
    row = conn.execute('SELECT music_data, mime_type, name FROM music WHERE id=?', (mid,)).fetchone()
    conn.close()
    if not row or not row['music_data']:
        return jsonify({'error': 'Music file not found'}), 404
    return Response(
        row['music_data'],
        mimetype=row['mime_type'] or 'audio/mpeg',
        headers={
            'Content-Disposition': f'inline; filename="{row["name"]}"',
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'public, max-age=3600'
        }
    )

# ══════════════════════════════════════════════════════════════════
# MUSIC API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/music', methods=['GET'])
def get_music():
    conn = get_db()
    rows = conn.execute('SELECT id, name, url, duration, start, end FROM music').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/music/add', methods=['POST'])
def add_music():
    data = request.json
    url = data.get('url','')
    import re
    m = re.match(r'/api/music/([^/]+)/file', url)
    if m:
        mid = m.group(1)
        conn = get_db()
        conn.execute('UPDATE music SET duration=?, start=?, end=? WHERE id=?',
            (str(data.get('duration','—')), data.get('start',0), data.get('end'), mid))
        conn.commit()
        row = conn.execute('SELECT * FROM music WHERE id=?',(mid,)).fetchone()
        conn.close()
        if row:
            r = dict(row); r.pop('music_data', None)
            return jsonify({'success':True,'music':r})
    mid = uuid.uuid4().hex[:8]
    conn = get_db()
    conn.execute('INSERT INTO music (id,name,url,duration,start,end) VALUES (?,?,?,?,?,?)',
        (mid,data.get('name'),url,str(data.get('duration','—')),data.get('start',0),data.get('end')))
    conn.commit()
    row = conn.execute('SELECT * FROM music WHERE id=?',(mid,)).fetchone()
    conn.close()
    r = dict(row); r.pop('music_data', None)
    return jsonify({'success':True,'music':r})

@app.route('/api/music/<mid>', methods=['DELETE'])
def delete_music(mid):
    conn = get_db(); conn.execute('DELETE FROM music WHERE id=?',(mid,))
    conn.commit(); conn.close(); return jsonify({'success':True})

@app.route('/api/music/<mid>/rename', methods=['POST'])
def rename_music(mid):
    data = request.json; conn = get_db()
    conn.execute('UPDATE music SET name=? WHERE id=?',(data.get('name',''),mid))
    conn.commit(); conn.close(); return jsonify({'success':True})

@app.route('/api/music/<mid>/trim', methods=['POST'])
def trim_music(mid):
    data = request.json; conn = get_db()
    conn.execute('UPDATE music SET start=?,end=? WHERE id=?',(data.get('start',0),data.get('end'),mid))
    conn.commit(); conn.close(); return jsonify({'success':True})

# ══════════════════════════════════════════════════════════════════
# SETTINGS API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/settings', methods=['GET'])
def get_settings_api():
    return jsonify({'app_name':get_setting('app_name','Caryanams'),
                    'admin_username':get_setting('admin_username','admin')})

@app.route('/api/settings', methods=['POST'])
def save_settings_api():
    data = request.json
    if data.get('app_name'):       set_setting('app_name',data['app_name'])
    if data.get('admin_username'): set_setting('admin_username',data['admin_username'])
    if data.get('new_password'):   set_setting('admin_password',data['new_password'])
    return jsonify({'success':True})

# ══════════════════════════════════════════════════════════════════
# PROJECTS API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/project/save', methods=['POST'])
def save_project():
    data = request.json; pid = uuid.uuid4().hex[:10]
    conn = get_db()
    conn.execute('INSERT INTO projects (id,name,template,images,text,music,created) VALUES (?,?,?,?,?,?,?)',
        (pid,data.get('name','Untitled Reel'),data.get('template'),json.dumps(data.get('images',[])),
         json.dumps(data.get('text',{})),json.dumps(data.get('music')),time.time()))
    conn.commit()
    row = conn.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    conn.close()
    p = dict(row); p['images']=json.loads(p['images']); p['text']=json.loads(p['text'])
    p['music']=json.loads(p['music']) if p['music'] else None
    return jsonify({'success':True,'project':p})

@app.route('/api/projects', methods=['GET'])
def list_projects():
    conn = get_db()
    rows = conn.execute('SELECT * FROM projects ORDER BY created DESC').fetchall()
    conn.close()
    result = []
    for r in rows:
        p = dict(r); p['images']=json.loads(p['images']); p['text']=json.loads(p['text'])
        p['music']=json.loads(p['music']) if p['music'] else None
        result.append(p)
    return jsonify(result)

# ══════════════════════════════════════════════════════════════════
# MUSIC MIGRATION
# ══════════════════════════════════════════════════════════════════

@app.route('/api/music/migrate-to-db', methods=['POST'])
def migrate_music_to_db():
    conn = get_db()
    rows = conn.execute("SELECT id, url FROM music WHERE music_data IS NULL").fetchall()
    migrated = 0
    for row in rows:
        url = row['url']
        if not url or url.startswith('/api/music/'):
            continue
        path = url.lstrip('/')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            ext = path.rsplit('.', 1)[-1].lower()
            mime_map = {'mp3':'audio/mpeg','wav':'audio/wav','ogg':'audio/ogg','m4a':'audio/mp4'}
            mime = mime_map.get(ext, 'audio/mpeg')
            new_url = f'/api/music/{row["id"]}/file'
            conn.execute('UPDATE music SET music_data=?, mime_type=?, url=? WHERE id=?',
                (data, mime, new_url, row['id']))
            migrated += 1
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'migrated': migrated})


init_db()
migrate_json_to_sqlite()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

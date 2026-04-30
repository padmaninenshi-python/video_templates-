from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, session, redirect, Response
import os, json, uuid, io, sqlite3, time
from werkzeug.utils import secure_filename
from functools import wraps
from gtts import gTTS

# Try deep-translator first (more reliable), fallback to googletrans
_has_translate = False
_translator_type = None

try:
    from deep_translator import GoogleTranslator as DeepGoogleTranslator
    _has_translate = True
    _translator_type = 'deep_translator'
except ImportError:
    pass

if not _has_translate:
    try:
        from googletrans import Translator
        _translator = Translator()
        _has_translate = True
        _translator_type = 'googletrans'
    except ImportError:
        pass

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
        duration TEXT DEFAULT "—", start REAL DEFAULT 0, end REAL)''')
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
        pass  # Column already exists
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
# TTS — gTTS + Auto Translate
# ══════════════════════════════════════════════════════════════════

# langCode (frontend) → gTTS lang code
GTTS_LANG_MAP = {
    'hi-IN':'hi', 'en-IN':'en', 'gu-IN':'gu', 'mr-IN':'mr', 'pa-IN':'pa',
    'ta-IN':'ta', 'te-IN':'te', 'kn-IN':'kn', 'bn-IN':'bn', 'ml-IN':'ml',
    'or-IN':'or', 'as-IN':'as', 'ne-IN':'ne', 'ur-IN':'ur',
    'en-US':'en',  'en-GB':'en',
    'fr-FR':'fr',  'de-DE':'de', 'es-ES':'es',
    'ar-SA':'ar',  'ja-JP':'ja', 'zh-CN':'zh'
}

@app.route('/api/tts', methods=['POST'])
def generate_tts():
    data       = request.get_json(force=True)
    text       = (data.get('text') or '').strip()
    lang_code  = data.get('lang', 'hi-IN')
    slow       = bool(data.get('slow', False))

    if not text:
        return jsonify({'error': 'Text required'}), 400

    gtts_lang = GTTS_LANG_MAP.get(lang_code, lang_code.split('-')[0])

    # ── Step 1: Auto-translate input text to target language ──────
    # Always translate — user may type in any language (Hindi, English, Gujarati, etc.)
    # We must convert to target language before generating voice
    translated_text = text
    if _has_translate:
        try:
            if _translator_type == 'deep_translator':
                translated_text = DeepGoogleTranslator(source='auto', target=gtts_lang).translate(text)
            elif _translator_type == 'googletrans':
                result = _translator.translate(text, dest=gtts_lang)
                if result and result.text:
                    translated_text = result.text
            print(f'[translate] {text!r} → ({gtts_lang}) {translated_text!r}')
        except Exception as te:
            print(f'[translate] failed: {te}')
            translated_text = text  # fallback — original text
    else:
        print('[translate] No translator available — using original text')

    # ── Step 2: gTTS generate ─────────────────────────────────────
    try:
        tts = gTTS(text=translated_text, lang=gtts_lang, slow=slow)
        fp  = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return Response(
            fp.read(),
            mimetype='audio/mpeg',
            headers={
                'Content-Disposition': 'inline; filename="voice.mp3"',
                'Cache-Control': 'no-cache',
                'X-Translated-Text': translated_text.encode('utf-8').decode('latin-1', errors='replace')
            }
        )
    except Exception as e:
        return jsonify({'error': str(e), 'translated': translated_text}), 500

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
    # First try file on disk
    fpath = os.path.join(TEMPLATES_FOLDER, f'{tid}.html')
    if os.path.exists(fpath):
        return send_from_directory(TEMPLATES_FOLDER, f'{tid}.html')
    # Fallback: check DB html_content (custom templates)
    conn = get_db()
    row = conn.execute('SELECT html_content FROM templates WHERE id=?', (tid,)).fetchone()
    conn.close()
    if row and row['html_content']:
        from flask import Response
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
    fn = secure_filename(f.filename); uid = f'{uuid.uuid4().hex[:8]}_{fn}'
    f.save(os.path.join(MUSIC_FOLDER, uid))
    return jsonify({'success':True,'url':f'/static/music/{uid}','name':fn})

# ══════════════════════════════════════════════════════════════════
# MUSIC API
# ══════════════════════════════════════════════════════════════════

@app.route('/api/music', methods=['GET'])
def get_music():
    conn = get_db(); rows = conn.execute('SELECT * FROM music').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/music/add', methods=['POST'])
def add_music():
    data = request.json; mid = uuid.uuid4().hex[:8]
    conn = get_db()
    conn.execute('INSERT INTO music (id,name,url,duration,start,end) VALUES (?,?,?,?,?,?)',
        (mid,data.get('name'),data.get('url'),str(data.get('duration','—')),data.get('start',0),data.get('end')))
    conn.commit()
    row = conn.execute('SELECT * FROM music WHERE id=?',(mid,)).fetchone()
    conn.close(); return jsonify({'success':True,'music':dict(row)})

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
init_db()
migrate_json_to_sqlite()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

# 🎬 Caryanams — Auto Video Reel Generator

> Create stunning **9:16 product reels** with AI voice, background music, and 21+ animated templates — directly in your browser. No video editing skills required.

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-green)](https://flask.palletsprojects.com)
[![gTTS](https://img.shields.io/badge/gTTS-2.5.4-orange)](https://gtts.readthedocs.io)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎭 21 Animated Templates | Motion, Cinematic, PPT Style, Creative |
| 📸 Multi-Image Upload | Drag & drop photos, auto-injected into templates |
| ✏️ Text & Price Overlay | Title, price, subtitle with custom colors & position |
| 🎵 Music Integration | Built-in tracks + custom upload with trim support |
| 🗣️ AI Voice (TTS) | 20+ Indian & global languages via gTTS + auto-translate |
| 🎙️ Voice Recording | Record, trim, and mix your own voiceover |
| 🎚️ Auto Ducking | Music fades when voice plays, rises after |
| 📤 Export as Video | Canvas-recorded MP4/WebM with voice + music mixed in |
| 🔗 Share to Platforms | WhatsApp, Instagram, YouTube, TikTok & more |
| 🛠️ Admin Panel | Manage templates, music tracks, and app settings |

---

## 🚀 Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/yourusername/caryanams.git
cd caryanams
```

### 2. Create virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python app.py
```

### 5. Open in browser
```
http://localhost:5000
```

---

## 📁 Project Structure

```
caryanams/
├── app.py                        # Flask backend — all API routes
├── requirements.txt              # Python dependencies
├── database.db                   # SQLite database (auto-created)
├── templates/
│   ├── index.html                # Main reel generator UI
│   ├── admin.html                # Admin panel
│   └── admin_login.html          # Admin login page
└── static/
    ├── templates_store/          # 21 animated HTML templates (tem1–tem21)
    │   ├── tem1.html
    │   ├── tem2.html
    │   └── ...
    ├── music/                    # Uploaded music tracks
    ├── uploads/                  # User uploaded images (per session)
    └── voice/                    # Voice folder (TTS served in-memory)
```

---

## 🗣️ Supported Languages (TTS)

| Language | Code | Language | Code |
|---|---|---|---|
| Hindi | `hi` | Tamil | `ta` |
| Gujarati | `gu` | Telugu | `te` |
| Marathi | `mr` | Kannada | `kn` |
| Bengali | `bn` | Malayalam | `ml` |
| Punjabi | `pa` | Odia | `or` |
| Urdu | `ur` | Nepali | `ne` |
| English (IN) | `en` | French | `fr` |
| English (US) | `en` | German | `de` |
| Spanish | `es` | Arabic | `ar` |
| Japanese | `ja` | Chinese | `zh` |

---

## 🛠️ Admin Panel

Visit `/admin` (default credentials: `admin` / `admin123`)

- Add / remove / toggle templates
- Upload and manage background music
- Rename and trim music tracks
- Change app name and admin password

---

## 🔧 How It Works

```
User selects template
        ↓
Upload product images  →  Images injected into animated HTML template
        ↓
Add text & price overlay  →  Canvas renders text on top of template
        ↓
Select music + generate AI voice  →  AudioContext mixes voice + music (with ducking)
        ↓
Export  →  Canvas captureStream() → MediaRecorder → MP4/WebM download
```

---

## 📦 Dependencies

```
flask==3.1.3          # Web framework
gTTS==2.5.4           # Google Text-to-Speech
googletrans==4.0.0rc1 # Auto-translate input text to target language
werkzeug==3.1.8       # Flask utilities & file handling
requests==2.33.1      # HTTP requests (used by gTTS)
httpx==0.13.3         # Async HTTP (used by googletrans)
httpcore==0.9.1       # HTTP core (httpx dependency)
```

---

## ⚠️ Known Issues

- `googletrans==4.0.0rc1` is required — newer versions may break translation
- TTS requires internet connection (Google TTS API)
- Video export uses `MediaRecorder` — works best in Chrome/Edge

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Credits

Built with ❤️ using [Flask](https://flask.palletsprojects.com), [gTTS](https://gtts.readthedocs.io), and [Google Translate](https://pypi.org/project/googletrans/).

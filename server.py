import os
import socket
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import qrcode
from flask import Flask, render_template_string, request, send_from_directory, jsonify

# ── Config ────────────────────────────────────────────────────────────────────
PORT = 5000
UPLOAD_DIR = Path(__file__).parent / "received_files"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB max


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_local_ip():
    """Return the machine's LAN IP (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def safe_filename(filename: str) -> str:
    """Avoid overwrites by appending a counter if a file already exists."""
    dest = UPLOAD_DIR / filename
    if not dest.exists():
        return filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while (UPLOAD_DIR / f"{stem}_{counter}{suffix}").exists():
        counter += 1
    return f"{stem}_{counter}{suffix}"


def print_qr(url: str):
    """Print a scannable QR code in the terminal."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    print("\n" + "═" * 52)
    print("  📡  ShareData Locally — scan to connect")
    print("═" * 52)
    qr.print_ascii(invert=True)
    print(f"  URL : {url}")
    print(f"  Save: {UPLOAD_DIR.resolve()}")
    print("═" * 52 + "\n")

    # Also save QR as PNG next to the script
    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = Path(__file__).parent / "qr_code.png"
    img.save(qr_path)
    print(f"  QR image saved → {qr_path}\n")


# ── HTML template (served to the phone browser) ───────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>ShareData Locally</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f0f13;
    --card: #1a1a24;
    --border: #2e2e42;
    --accent: #6c63ff;
    --accent2: #ff6584;
    --text: #e8e8f0;
    --muted: #888899;
    --success: #4caf82;
    --radius: 14px;
  }
  body.light {
    --bg: #f4f4f8;
    --card: #ffffff;
    --border: #dcdce8;
    --text: #1a1a2e;
    --muted: #6b6b80;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    min-height: 100vh;
    padding: 20px 16px 40px;
    transition: background .25s, color .25s;
  }
  /* ── Header row ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    margin-bottom: 4px;
  }
  h1 {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: .5px;
  }
  /* ── Theme toggle ── */
  #theme-btn {
    position: absolute;
    right: 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 5px 12px;
    font-size: .82rem;
    cursor: pointer;
    color: var(--text);
    transition: background .2s, border-color .2s;
    white-space: nowrap;
  }
  .subtitle {
    text-align: center;
    color: var(--muted);
    font-size: .85rem;
    margin-bottom: 28px;
  }

  /* ── Upload card ── */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 20px;
  }
  .card h2 {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  /* ── Drop zone ── */
  #dropzone {
    border: 2px dashed var(--border);
    border-radius: 10px;
    padding: 36px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color .2s, background .2s;
    position: relative;
  }
  #dropzone.drag-over {
    border-color: var(--accent);
    background: rgba(108,99,255,.07);
  }
  #dropzone input[type=file] {
    position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
  }
  #dropzone .icon { font-size: 2.4rem; margin-bottom: 10px; }
  #dropzone p { color: var(--muted); font-size: .9rem; }
  #dropzone p strong { color: var(--text); }

  /* ── File list ── */
  #file-list { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
  .file-item {
    background: rgba(255,255,255,.04);
    border-radius: 8px;
    padding: 10px 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: .85rem;
  }
  .file-item .fname { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-item .fsize { color: var(--muted); font-size: .78rem; }
  .progress-wrap {
    width: 100%;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin-top: 6px;
    overflow: hidden;
  }
  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    border-radius: 2px;
    width: 0%;
    transition: width .1s;
  }
  .badge {
    font-size: .72rem;
    padding: 2px 8px;
    border-radius: 20px;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge.pending  { background: rgba(108,99,255,.2); color: var(--accent); }
  .badge.uploading{ background: rgba(255,165,0,.2);  color: #ffa500; }
  .badge.done     { background: rgba(76,175,130,.2); color: var(--success); }
  .badge.error    { background: rgba(255,101,132,.2);color: var(--accent2); }

  /* ── Upload button ── */
  #upload-btn {
    width: 100%;
    margin-top: 16px;
    padding: 14px;
    border: none;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), #8b5cf6);
    color: #fff;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    letter-spacing: .3px;
    transition: opacity .2s, transform .1s;
  }
  #upload-btn:disabled { opacity: .5; cursor: default; }
  #upload-btn:active:not(:disabled) { transform: scale(.98); }

  /* ── Received files table ── */
  .file-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: .85rem;
  }
  .file-row:last-child { border-bottom: none; }
  .file-row .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-row .meta { color: var(--muted); font-size: .75rem; white-space: nowrap; }
  .dl-btn {
    text-decoration: none;
    background: rgba(108,99,255,.15);
    color: var(--accent);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: .78rem;
    font-weight: 600;
    white-space: nowrap;
    transition: background .2s;
  }
  .dl-btn:hover { background: rgba(108,99,255,.3); }
  .empty { color: var(--muted); text-align: center; padding: 20px 0; font-size: .88rem; }

  /* ── Toast ── */
  #toast {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: var(--success); color: #fff;
    padding: 10px 22px; border-radius: 24px;
    font-size: .88rem; font-weight: 600;
    opacity: 0; pointer-events: none;
    transition: opacity .3s;
    white-space: nowrap;
    z-index: 999;
  }
  #toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="header">
  <h1>📡 ShareData Locally</h1>
  <button id="theme-btn">☀️ Light</button>
</div>
<p class="subtitle">Send files from your phone to this PC</p>

<!-- Upload card -->
<div class="card">
  <h2>⬆️ Upload Files</h2>
  <div id="dropzone">
    <input type="file" id="file-input" multiple/>
    <div class="icon">📂</div>
    <p><strong>Tap to select</strong> files</p>
    <p>Any type · Up to 2 GB each</p>
  </div>
  <div id="file-list"></div>
  <button id="upload-btn" disabled>Upload</button>
</div>

<!-- Received files card -->
<div class="card">
  <h2>📥 Files on PC</h2>
  <div id="received-list"><p class="empty">Loading…</p></div>
</div>

<div id="toast"></div>

<script>
const dropzone   = document.getElementById('dropzone');
const fileInput  = document.getElementById('file-input');
const fileList   = document.getElementById('file-list');
const uploadBtn  = document.getElementById('upload-btn');
const receivedEl = document.getElementById('received-list');
const toast      = document.getElementById('toast');

// ── Theme toggle ─────────────────────────────────────────────────────────────
const themeBtn = document.getElementById('theme-btn');
const savedTheme = localStorage.getItem('qrdrop-theme') || 'dark';
if (savedTheme === 'light') {
  document.body.classList.add('light');
  themeBtn.textContent = '🌙 Dark';
}
themeBtn.addEventListener('click', () => {
  const isLight = document.body.classList.toggle('light');
  themeBtn.textContent = isLight ? '🌙 Dark' : '☀️ Light';
  localStorage.setItem('qrdrop-theme', isLight ? 'light' : 'dark');
});

let selectedFiles = [];

function showToast(msg, color = '#4caf82') {
  toast.textContent = msg;
  toast.style.background = color;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  if (bytes < 1024*1024*1024) return (bytes/1024/1024).toFixed(1) + ' MB';
  return (bytes/1024/1024/1024).toFixed(2) + ' GB';
}

function renderFileList() {
  fileList.innerHTML = '';
  selectedFiles.forEach((f, i) => {
    const div = document.createElement('div');
    div.className = 'file-item';
    div.id = `fi-${i}`;
    div.innerHTML = `
      <span class="fname">${f.name}</span>
      <span class="fsize">${formatSize(f.size)}</span>
      <span class="badge pending" id="badge-${i}">Queued</span>
      <div class="progress-wrap" id="pw-${i}" style="display:none">
        <div class="progress-bar" id="pb-${i}"></div>
      </div>`;
    fileList.appendChild(div);
  });
  uploadBtn.disabled = selectedFiles.length === 0;
}

// Drag & drop
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  selectedFiles = [...e.dataTransfer.files];
  renderFileList();
});
fileInput.addEventListener('change', () => {
  selectedFiles = [...fileInput.files];
  renderFileList();
});

// Upload one file at a time to show per-file progress
async function uploadFile(file, index) {
  const badge = document.getElementById(`badge-${index}`);
  const pb    = document.getElementById(`pb-${index}`);
  const pw    = document.getElementById(`pw-${index}`);

  badge.className = 'badge uploading';
  badge.textContent = '0%';
  pw.style.display = 'block';

  return new Promise((resolve) => {
    const fd  = new FormData();
    fd.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');

    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable) {
        const pct = Math.round(e.loaded / e.total * 100);
        badge.textContent = pct + '%';
        pb.style.width = pct + '%';
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status === 200) {
        badge.className = 'badge done';
        badge.textContent = 'Done ✓';
        pb.style.width = '100%';
      } else {
        badge.className = 'badge error';
        badge.textContent = 'Error';
      }
      resolve();
    });

    xhr.addEventListener('error', () => {
      badge.className = 'badge error';
      badge.textContent = 'Error';
      resolve();
    });

    xhr.send(fd);
  });
}

uploadBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;
  uploadBtn.disabled = true;

  for (let i = 0; i < selectedFiles.length; i++) {
    await uploadFile(selectedFiles[i], i);
  }

  showToast(`✓ ${selectedFiles.length} file(s) sent to PC!`);
  loadReceived();
  // Reset after short delay
  setTimeout(() => {
    selectedFiles = [];
    fileInput.value = '';
    fileList.innerHTML = '';
    uploadBtn.disabled = true;
  }, 3000);
});

// ── Received files ────────────────────────────────────────────────────────────
async function loadReceived() {
  try {
    const res  = await fetch('/files');
    const data = await res.json();
    if (!data.files.length) {
      receivedEl.innerHTML = '<p class="empty">No files yet</p>';
      return;
    }
    receivedEl.innerHTML = data.files.map(f => `
      <div class="file-row">
        <span class="name">${f.name}</span>
        <span class="meta">${f.size} · ${f.date}</span>
        <a class="dl-btn" href="/download/${encodeURIComponent(f.name)}" download>↓ Get</a>
      </div>`).join('');
  } catch {
    receivedEl.innerHTML = '<p class="empty">Could not load file list</p>';
  }
}

loadReceived();
setInterval(loadReceived, 5000); // auto-refresh every 5 s
</script>
</body>
</html>
"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    filename = safe_filename(f.filename)
    dest = UPLOAD_DIR / filename
    f.save(dest)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  ✓  Received: {filename}  ({dest.stat().st_size / 1024:.1f} KB)  [{timestamp}]")
    return jsonify({"saved": filename}), 200


@app.route("/files")
def list_files():
    files = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            size_bytes = p.stat().st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 ** 2:
                size_str = f"{size_bytes/1024:.1f} KB"
            elif size_bytes < 1024 ** 3:
                size_str = f"{size_bytes/1024**2:.1f} MB"
            else:
                size_str = f"{size_bytes/1024**3:.2f} GB"

            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%b %d, %H:%M")
            files.append({"name": p.name, "size": size_str, "date": mtime})
    return jsonify({"files": files})


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ip  = get_local_ip()
    url = f"http://{ip}:{PORT}"
    print_qr(url)

    # Optionally open browser on PC too
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

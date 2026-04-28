import os
import socket
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import qrcode
import subprocess
import sys
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
  .del-btn {
    background: rgba(255,101,132,.12);
    color: var(--accent2);
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: .78rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background .2s;
  }
  .del-btn:hover { background: rgba(255,101,132,.28); }
  .empty { color: var(--muted); text-align: center; padding: 20px 0; font-size: .88rem; }

  /* ── Sort & filter bar ── */
  .filter-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .filter-bar input {
    flex: 1;
    min-width: 0;
    padding: 7px 11px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    font-size: .85rem;
    outline: none;
    transition: border-color .2s;
  }
  .filter-bar input:focus { border-color: var(--accent); }
  .filter-bar select {
    padding: 7px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    font-size: .82rem;
    outline: none;
    cursor: pointer;
  }

  /* ── Clipboard card ── */
  #clip-input {
    width: 100%;
    min-height: 90px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    font-size: .9rem;
    font-family: inherit;
    resize: vertical;
    outline: none;
    transition: border-color .2s;
  }
  #clip-input:focus { border-color: var(--accent); }
  #clip-btn {
    width: 100%;
    margin-top: 10px;
    padding: 12px;
    border: none;
    border-radius: 10px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: #fff;
    font-size: .95rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .2s, transform .1s;
  }
  #clip-btn:active { transform: scale(.98); }

  /* ── Clipboard history ── */
  .clip-entry {
    background: rgba(255,255,255,.04);
    border-radius: 8px;
    padding: 10px 12px;
    margin-top: 8px;
    font-size: .85rem;
    word-break: break-word;
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .clip-entry .clip-text { flex: 1; white-space: pre-wrap; }
  .clip-entry .clip-time { color: var(--muted); font-size: .72rem; white-space: nowrap; }
  .clip-copy-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted);
    font-size: .75rem;
    padding: 2px 8px;
    cursor: pointer;
    white-space: nowrap;
    transition: color .2s, border-color .2s;
  }
  .clip-copy-btn:hover { color: var(--accent); border-color: var(--accent); }

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

<!-- Clipboard share card -->
<div class="card">
  <h2>📋 Send Text / Link to PC</h2>
  <textarea id="clip-input" placeholder="Paste a URL, phone number, note, or any text…"></textarea>
  <button id="clip-btn">Send to PC Clipboard</button>
  <div id="clip-history"></div>
</div>

<!-- Received files card -->
<div class="card">
  <h2>📥 Files on PC</h2>
  <div class="filter-bar">
    <input type="search" id="search-input" placeholder="Search files…"/>
    <select id="sort-select">
      <option value="date-desc">Newest first</option>
      <option value="date-asc">Oldest first</option>
      <option value="name-asc">Name A–Z</option>
      <option value="name-desc">Name Z–A</option>
      <option value="size-desc">Largest first</option>
      <option value="size-asc">Smallest first</option>
    </select>
  </div>
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

// ── Clipboard share ───────────────────────────────────────────────────────────
const clipInput   = document.getElementById('clip-input');
const clipBtn     = document.getElementById('clip-btn');
const clipHistory = document.getElementById('clip-history');

function renderClipHistory() {
  const items = JSON.parse(localStorage.getItem('qrdrop-clips') || '[]');
  if (!items.length) { clipHistory.innerHTML = ''; return; }
  clipHistory.innerHTML = items.slice(0, 10).map((c, i) => `
    <div class="clip-entry">
      <span class="clip-text">${c.text}</span>
      <span class="clip-time">${c.time}</span>
      <button class="clip-copy-btn" onclick="copyClip(${i})">Copy</button>
    </div>`).join('');
}

function copyClip(index) {
  const items = JSON.parse(localStorage.getItem('qrdrop-clips') || '[]');
  navigator.clipboard.writeText(items[index].text).then(() => showToast('Copied!'));
}

clipBtn.addEventListener('click', async () => {
  const text = clipInput.value.trim();
  if (!text) return;

  try {
    const res = await fetch('/clipboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (res.ok) {
      const now   = new Date();
      const time  = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const items = JSON.parse(localStorage.getItem('qrdrop-clips') || '[]');
      items.unshift({ text, time });
      localStorage.setItem('qrdrop-clips', JSON.stringify(items.slice(0, 20)));
      renderClipHistory();
      clipInput.value = '';
      showToast('✓ Sent to PC clipboard!');
    } else {
      showToast('Failed to send', '#ff6584');
    }
  } catch {
    showToast('Connection error', '#ff6584');
  }
});

renderClipHistory();

// ── Received files ────────────────────────────────────────────────────────────
const searchInput = document.getElementById('search-input');
const sortSelect  = document.getElementById('sort-select');
let allFiles = [];

function renderReceived() {
  const query   = searchInput.value.trim().toLowerCase();
  const sortKey = sortSelect.value;

  let files = allFiles.filter(f => f.name.toLowerCase().includes(query));

  files.sort((a, b) => {
    if (sortKey === 'name-asc')   return a.name.localeCompare(b.name);
    if (sortKey === 'name-desc')  return b.name.localeCompare(a.name);
    if (sortKey === 'size-asc')   return a.size_bytes - b.size_bytes;
    if (sortKey === 'size-desc')  return b.size_bytes - a.size_bytes;
    if (sortKey === 'date-asc')   return a.mtime - b.mtime;
    return b.mtime - a.mtime; // date-desc (default)
  });

  if (!files.length) {
    receivedEl.innerHTML = query
      ? `<p class="empty">No files match "<strong>${query}</strong>"</p>`
      : '<p class="empty">No files yet</p>';
    return;
  }

  receivedEl.innerHTML = files.map(f => `
    <div class="file-row" id="row-${CSS.escape(f.name)}">
      <span class="name">${f.name}</span>
      <span class="meta">${f.size} · ${f.date}</span>
      <a class="dl-btn" href="/download/${encodeURIComponent(f.name)}" download>↓ Get</a>
      <button class="del-btn" onclick="deleteFile(${JSON.stringify(f.name)})">✕</button>
    </div>`).join('');
}

async function loadReceived() {
  try {
    const res  = await fetch('/files');
    const data = await res.json();
    allFiles = data.files;
    renderReceived();
  } catch {
    receivedEl.innerHTML = '<p class="empty">Could not load file list</p>';
  }
}

async function deleteFile(name) {
  if (!confirm(`Delete "${name}" from PC?`)) return;
  try {
    const res = await fetch('/delete/' + encodeURIComponent(name), { method: 'DELETE' });
    if (res.ok) {
      allFiles = allFiles.filter(f => f.name !== name);
      renderReceived();
      showToast('🗑 Deleted: ' + name, '#ff6584');
    } else {
      showToast('Delete failed', '#ff6584');
    }
  } catch {
    showToast('Connection error', '#ff6584');
  }
}

searchInput.addEventListener('input', renderReceived);
sortSelect.addEventListener('change', renderReceived);

loadReceived();
setInterval(loadReceived, 5000);
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

            mtime_ts = p.stat().st_mtime
            mtime = datetime.fromtimestamp(mtime_ts).strftime("%b %d, %H:%M")
            files.append({
                "name": p.name,
                "size": size_str,
                "size_bytes": size_bytes,
                "date": mtime,
                "mtime": mtime_ts,
            })
    return jsonify({"files": files})


@app.route("/clipboard", methods=["POST"])
def clipboard():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "No text provided"}), 400
    text = data["text"]
    try:
        # Windows: pipe text into clip.exe
        proc = subprocess.run(
            ["clip"],
            input=text.encode("utf-16-le"),
            check=True,
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        preview = text[:60] + ("…" if len(text) > 60 else "")
        print(f"  📋 Clipboard: \"{preview}\"  [{timestamp}]")
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    target = (UPLOAD_DIR / filename).resolve()
    if not str(target).startswith(str(UPLOAD_DIR.resolve())):
        return jsonify({"error": "Invalid path"}), 400
    if not target.exists():
        return jsonify({"error": "File not found"}), 404
    target.unlink()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  🗑  Deleted: {filename}  [{timestamp}]")
    return jsonify({"deleted": filename}), 200


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

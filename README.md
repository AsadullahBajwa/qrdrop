# qrdrop

> Scan a QR code on your PC, upload files from your phone instantly over local WiFi. No cables, no apps, no cloud.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/flask-lightweight-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

---

## What it does

Run the server on your Windows PC. A QR code appears in the terminal. Scan it with your Android or iPhone — your phone browser opens a clean upload UI. Select files, hit upload, done. Files land in a `received_files/` folder on your PC instantly over your local WiFi.

No USB cables. No Bluetooth pairing. No third-party apps. No internet required.

---

## Features

- QR code printed in terminal + saved as `qr_code.png`
- Mobile-friendly browser UI (works on Android & iPhone)
- Multi-file upload with per-file progress bars
- Auto-detects your PC's local IP — zero config
- Download files back to your phone from the same UI
- Duplicate-safe filenames (`file_1.jpg`, `file_2.jpg`, …)
- Auto-refreshing file list every 5 seconds
- Supports up to 2 GB per file

---

## Requirements

- Python 3.8+
- PC and phone on the **same WiFi network**

---

## Installation

```bash
git clone https://github.com/AsadullahBajwa/qrdrop.git
cd qrdrop
pip install flask qrcode[pil] Pillow
```

---

## Usage

```bash
python server.py
```

1. A QR code appears in your terminal
2. Open your phone camera and scan it
3. Browser opens on your phone — select files and upload
4. Files are saved to `received_files/` on your PC

---

## Project Structure

```
qrdrop/
├── server.py          # Flask server + QR generation + web UI
├── received_files/    # Uploaded files land here (auto-created)
├── qr_code.png        # QR saved on each run (auto-created)
└── README.md
```

---

## Configuration

At the top of `server.py`:

```python
PORT = 5000                          # change port if needed
app.config["MAX_CONTENT_LENGTH"]     # default 2 GB per file
```

---

## How it works

```
Phone Camera
    │  scan QR
    ▼
Phone Browser  ──── HTTP POST /upload ────▶  Flask Server (PC)
                                                    │
                                             received_files/
```

The server binds to `0.0.0.0` so it accepts connections from any device on the local network. The QR encodes your PC's LAN IP so your phone hits it directly — no routing through the internet.

---

## License

MIT

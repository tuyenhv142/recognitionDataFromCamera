# Live Camera OCR Data Acquisition & Logging System

A real-time data acquisition and logging system for digital LCD displays (radiation survey meters / laboratory measurement devices) streamed over LAN (`http://192.168.1.1:8080/video`). It utilizes AI-powered OCR to extract numeric readings, automatically logs them to daily CSV files, and saves full-frame snapshot proofs.

---

## 🚀 Key Features

1. **Direct & Stable LAN Connection:**
   - Seamless non-blocking MJPEG video streaming over LAN.
   - Decoupled multithreading between video display and OCR processing ensures zero frame lag.
   - Built-in auto-reconnection and network socket timeout protection.

2. **High-Accuracy LCD Digit Recognition (RapidOCR):**
   - Direct recognizer inference with border padding optimized for 7-segment digital displays.
   - Accurately captures all decimal digits (e.g. `0.001`, `0.003`) and ignores baseline zeroes (`0.000`).

3. **Intelligent CSV Logging & Snapshot Proofs:**
   - Records data into daily rotating CSV files: `data/readings_YYYY-MM-DD.csv`.
   - Data columns: `Timestamp`, `Value`, `Confidence`, `Snapshot`, `Status`.
   - Captures high-quality full-frame snapshots in `snapshots/` **only ONCE** when a new non-zero reading appears.
   - Ignores baseline `0.000` readings to prevent file clutter and unnecessary disk writes.

4. **Modern Web Dashboard (`http://localhost:5055`):**
   - Live video stream with real-time green/red target bounding box (Region of Interest - ROI).
   - Interactive sliders to adjust ROI position (X, Y) and dimensions (W, H) live without code edits.
   - Large digital HUD display showing current reading with unit (`µSv/h`), confidence, and time.
   - Live crop preview box to verify LCD framing.
   - Persistent historical table showing today's records (retained across browser reloads).
   - Instant full-screen image lightbox modal and 1-click CSV download.

---

## 🛠️ How to Run

### Method 1: Continuous 24/7 Mode (Recommended for Long Experiments)
- Double-click **`run_24h.bat`**.
- Runs continuously 24/7 with automatic crash recovery (restarts within 3 seconds if disconnected or terminated).
- To make the system **start automatically upon Windows boot/reboot**: Double-click **`install_autostart.bat`**.

### Method 2: Standard Quick Launch
- Double-click **`start.bat`**.
- Automatically launches the server and opens `http://localhost:5055` in your browser.

### Method 3: Command Line (CLI Headless Mode)
```bash
python cli_logger.py
```

---

## 📁 Directory Structure
```text
getDataFromCamera/
├── app.py                  # Flask Web Server & API backend
├── camera_stream.py        # Multi-threaded non-blocking camera capture
├── ocr_reader.py           # LCD 7-segment OCR recognition module
├── data_logger.py          # CSV logger and snapshot manager
├── config.py               # Configuration loader and saver
├── cli_logger.py           # Standalone CLI console runner
├── start.bat               # 1-click Windows quick launch script
├── run_24h.bat             # 24/7 supervisor runner with auto-recovery
├── install_autostart.bat   # Installs autostart shortcut in Windows Startup
├── uninstall_autostart.bat # Removes Windows autostart shortcut
├── templates/
│   └── index.html          # Web dashboard interface (English)
├── data/                   # Directory containing daily CSV files
└── snapshots/              # Directory containing full-frame snapshot images
```

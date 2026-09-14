import os
import sys
import io

# Đảm bảo UTF-8 hoạt động chuẩn trên Windows Console
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import cv2
import time
import base64
import threading
from datetime import datetime
from flask import Flask, render_template, Response, request, jsonify, send_file, send_from_directory

from config import load_settings, save_settings
from camera_stream import CameraManager
from ocr_reader import LCDReader
from data_logger import DataLogger

app = Flask(__name__)

# Khởi tạo các thành phần hệ thống
settings = load_settings()
cam = CameraManager(settings.get("camera_url", "http://192.168.1.1:8080/video"))
ocr = LCDReader()
logger = DataLogger(settings.get("data_dir", "data"), settings.get("snapshot_dir", "snapshots"))

# Trạng thái ứng dụng thời gian thực (Mặc định BẬT ghi tự động để người dùng không cần bấm nút)
app_state = {
    "is_logging": True,
    "current_value": "---",
    "confidence": 0.0,
    "last_read_time": None,
    "latest_crop_bytes": None,
    "lock": threading.Lock()
}

def is_zero_value(val_str):
    """Kiểm tra xem giá trị đọc được có phải là 0 hoặc 0.000 (trạng thái nền) không."""
    if not val_str:
        return True
    try:
        return float(val_str) == 0.0
    except (ValueError, TypeError):
        clean = str(val_str).replace('.', '').replace('0', '').strip()
        return clean == ''

def ocr_worker():
    """Luồng chạy ngầm liên tục theo dõi camera 24/7. Bỏ qua 0.000, chỉ chụp 1 lần khi có số thực xuất hiện."""
    import gc
    last_logged_val = logger.last_logged_value if logger.last_logged_value else "0.000"
    cycle_counter = 0

    while True:
        try:
            roi = settings.get("roi", {"x": 95, "y": 180, "w": 90, "h": 40})
            save_snap = settings.get("save_snapshot", True)

            ret, frame = cam.get_frame()
            if ret and frame is not None:
                # Nhận diện số từ vùng ROI
                val, conf, crop = ocr.read_value(frame, roi)
                
                # Mã hóa ảnh crop nhỏ phục vụ xem trước
                crop_bytes = None
                if crop is not None and crop.size > 0:
                    ret_enc, buf = cv2.imencode('.jpg', crop)
                    if ret_enc:
                        crop_bytes = buf.tobytes()

                with app_state["lock"]:
                    if val is not None:
                        app_state["current_value"] = val
                        app_state["confidence"] = round(conf * 100, 1)
                    app_state["last_read_time"] = datetime.now().strftime("%H:%M:%S")
                    if crop_bytes:
                        app_state["latest_crop_bytes"] = crop_bytes

                # CHỈ CHỤP 1 LẦN KHI SỐ MỚI XUẤT HIỆN VÀ KHÁC 0.000
                if app_state["is_logging"] and val is not None:
                    if logger.last_logged_value:
                        last_logged_val = logger.last_logged_value
                    if not is_zero_value(val) and conf >= 0.40:
                        # Đây là số thực tế > 0 (ví dụ 0.001, 0.002, ...)
                        if val != last_logged_val:
                            logger.log_reading(
                                value=val,
                                confidence=conf,
                                frame=frame,
                                save_snapshot=save_snap
                            )
                            last_logged_val = val
                            print(f"[*] Captured & logged once for new reading (>0): {val}")
                    else:
                        # Nếu giá trị là 0.000: BỎ QUA KHÔNG LƯU, cập nhật mốc để khi có số > 0 sẽ chụp ngay
                        if is_zero_value(val) and last_logged_val != "0.000":
                            last_logged_val = "0.000"

            cycle_counter += 1
            if cycle_counter % 300 == 0:
                gc.collect()  # Giải phóng bộ nhớ RAM định kỳ giúp chạy 24h siêu ổn định

            time.sleep(0.4)

        except Exception as e:
            print(f"Error in OCR Worker thread: {e}")
            time.sleep(1.0)

# Khởi động camera và worker thread
cam.start()
worker_thread = threading.Thread(target=ocr_worker, daemon=True)
worker_thread.start()

def generate_video_feed():
    """Generator sinh luồng MJPEG phát trực tiếp lên trình duyệt."""
    while True:
        roi = settings.get("roi")
        with app_state["lock"]:
            val = app_state["current_value"]
            is_log = app_state["is_logging"]

        annotated = cam.get_annotated_frame(roi=roi, current_value=val, is_logging=is_log)
        ret, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.04)  # ~25 FPS cho web stream

@app.route('/')
def index():
    return render_template('index.html', settings=settings)

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_feed(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/crop_preview')
def crop_preview():
    """Trả về ảnh crop vùng LCD hiện tại."""
    with app_state["lock"]:
        crop_bytes = app_state.get("latest_crop_bytes")
    if crop_bytes:
        return Response(crop_bytes, mimetype='image/jpeg')
    return Response(b'', status=204)

@app.route('/api/status')
def get_status():
    """Cung cấp toàn bộ trạng thái thời gian thực và các bản ghi gần đây cho giao diện."""
    with app_state["lock"]:
        curr_val = app_state["current_value"]
        conf = app_state["confidence"]
        last_t = app_state["last_read_time"]
        is_log = app_state["is_logging"]

    recent = logger.get_recent(limit=30)
    stats = logger.get_stats()

    return jsonify({
        "camera_connected": cam.is_alive(),
        "camera_fps": cam.fps,
        "current_value": curr_val,
        "confidence": conf,
        "last_read_time": last_t,
        "is_logging": is_log,
        "log_mode": settings.get("log_mode", "change"),
        "sampling_interval": settings.get("sampling_interval", 1.0),
        "save_snapshot": settings.get("save_snapshot", True),
        "roi": settings.get("roi", {"x": 95, "y": 180, "w": 90, "h": 40}),
        "stats": stats,
        "recent_records": recent
    })

@app.route('/api/toggle_logging', methods=['POST'])
def toggle_logging():
    data = request.get_json() or {}
    action = data.get("action")
    with app_state["lock"]:
        if action == "start":
            app_state["is_logging"] = True
        elif action == "stop":
            app_state["is_logging"] = False
        else:
            app_state["is_logging"] = not app_state["is_logging"]
        is_log = app_state["is_logging"]

    return jsonify({"success": True, "is_logging": is_log})

@app.route('/api/manual_capture', methods=['POST'])
def manual_capture():
    """Chụp tức thì 1 bản ghi và 1 bức ảnh vào file CSV ngay khi người dùng bấm."""
    ret, frame = cam.get_frame()
    if not ret or frame is None:
        return jsonify({"success": False, "error": "Camera is not responding"}), 400

    roi = settings.get("roi")
    val, conf, _ = ocr.read_value(frame, roi)
    record = logger.log_reading(
        value=val if val is not None else "MANUAL",
        confidence=conf,
        frame=frame,
        save_snapshot=True,
        force=True
    )
    return jsonify({"success": True, "record": record})

@app.route('/api/update_roi', methods=['POST'])
def update_roi():
    data = request.get_json() or {}
    try:
        new_roi = {
            "x": int(data.get("x", 95)),
            "y": int(data.get("y", 180)),
            "w": int(data.get("w", 90)),
            "h": int(data.get("h", 40))
        }
        settings["roi"] = new_roi
        save_settings(settings)
        return jsonify({"success": True, "roi": new_roi})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/update_settings', methods=['POST'])
def update_settings_endpoint():
    data = request.get_json() or {}
    if "camera_url" in data and data["camera_url"] != settings.get("camera_url"):
        settings["camera_url"] = data["camera_url"]
        cam.update_url(data["camera_url"])
        
    if "sampling_interval" in data:
        try:
            settings["sampling_interval"] = max(0.2, float(data["sampling_interval"]))
        except ValueError:
            pass

    if "log_mode" in data and data["log_mode"] in ["change", "interval", "all"]:
        settings["log_mode"] = data["log_mode"]

    if "save_snapshot" in data:
        settings["save_snapshot"] = bool(data["save_snapshot"])

    save_settings(settings)
    return jsonify({"success": True, "settings": settings})

@app.route('/api/download_csv')
def download_csv():
    csv_file = logger.get_csv_filename()
    if os.path.exists(csv_file):
        return send_file(csv_file, as_attachment=True, download_name=os.path.basename(csv_file))
    return jsonify({"error": "No CSV data file recorded yet."}), 404

@app.route('/snapshots/<path:filename>')
def serve_snapshot(filename):
    """Cung cấp ảnh chụp màn hình minh chứng."""
    snap_dir = os.path.abspath(settings.get("snapshot_dir", "snapshots"))
    return send_from_directory(snap_dir, filename)

@app.route('/api/delete_record', methods=['POST'])
def delete_record_endpoint():
    data = request.get_json() or {}
    timestamp = data.get("timestamp")
    snapshot = data.get("snapshot")
    timestamps = list(data.get("timestamps", []))
    snapshots = list(data.get("snapshots", []))
    if timestamp and timestamp not in timestamps:
        timestamps.append(timestamp)
    if snapshot and snapshot not in snapshots:
        snapshots.append(snapshot)

    count = logger.delete_records(timestamps=timestamps, snapshots=snapshots)
    return jsonify({"success": True, "deleted_count": count})

@app.route('/api/clear_all', methods=['POST'])
def clear_all_endpoint():
    success = logger.clear_all()
    return jsonify({"success": success})

if __name__ == '__main__':
    host = settings.get("host", "0.0.0.0")
    port = int(settings.get("port", 5000))
    print(f"=== Starting Camera OCR Data Logger system at http://localhost:{port} ===")
    app.run(host=host, port=port, debug=False, threaded=True)

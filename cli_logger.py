import time
import sys
import io

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
from datetime import datetime
from config import load_settings
from camera_stream import CameraManager
from ocr_reader import LCDReader
from data_logger import DataLogger

def main():
    print("=" * 65)
    print("    CAMERA OCR DATA LOGGER SYSTEM (CLI CONSOLE MODE)")
    print("=" * 65)
    
    settings = load_settings()
    url = settings.get("camera_url", "http://192.168.1.1:8080/video")
    roi = settings.get("roi", {"x": 95, "y": 180, "w": 90, "h": 40})
    interval = float(settings.get("sampling_interval", 1.0))
    save_snap = settings.get("save_snapshot", True)
    mode = settings.get("log_mode", "change")

    print(f"[*] Connecting to camera: {url}")
    print(f"[*] LCD Detection ROI: x={roi['x']}, y={roi['y']}, w={roi['w']}, h={roi['h']}")
    print(f"[*] Sampling interval: {interval}s | Mode: {mode} | Save snapshot: {save_snap}")
    print("[*] Press Ctrl + C to stop the program.\n")

    cam = CameraManager(url)
    cam.start()
    ocr = LCDReader()
    logger = DataLogger(settings.get("data_dir", "data"), settings.get("snapshot_dir", "snapshots"))

    last_val = None
    last_log_time = 0

    try:
        while True:
            ret, frame = cam.get_frame()
            if not ret or frame is None:
                print("[!] Waiting for camera stream...", end="\r")
                time.sleep(1.0)
                continue

            val, conf, _ = ocr.read_value(frame, roi)
            now_t = time.time()
            now_str = datetime.now().strftime("%H:%M:%S")

            if val is not None:
                should_log = False
                if mode == "change":
                    if val != last_val:
                        should_log = True
                elif mode == "interval":
                    if now_t - last_log_time >= interval:
                        should_log = True
                else:
                    should_log = True

                if should_log:
                    rec = logger.log_reading(val, conf, frame=frame, save_snapshot=save_snap)
                    snap_name = rec['snapshot'] if rec else 'none'
                    print(f"[{now_str}] NEW RECORD -> Value: {val} µSv/h | Conf: {conf*100:.1f}% | Image: {snap_name}")
                    last_val = val
                    last_log_time = now_t
                else:
                    print(f"[{now_str}] Monitoring -> Current: {val} (unchanged)", end="\r")
            else:
                print(f"[{now_str}] No digits recognized...", end="\r")

            time.sleep(max(0.2, min(interval, 2.0)))

    except KeyboardInterrupt:
        print("\n[*] Stopping system...")
    finally:
        cam.stop()
        print("[*] Camera stream stopped safely.")

if __name__ == "__main__":
    main()

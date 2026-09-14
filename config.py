import os
import json

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "camera_url": "http://192.168.1.1:8080/video",
    "roi": {
        "x": 95,
        "y": 180,
        "w": 90,
        "h": 40
    },
    "sampling_interval": 2.0,  # Giây giữa các lần đọc OCR
    "log_mode": "both",        # "both" (khi số đổi HOẶC theo chu kỳ giây), "change" (chỉ khi đổi số), "interval" (định kỳ)
    "save_snapshot": True,     # Có chụp ảnh lưu lại không
    "unit": "uSv/h",           # Đơn vị đo hiển thị
    "data_dir": "data",
    "snapshot_dir": "snapshots",
    "port": 5055,
    "host": "0.0.0.0"
}

def load_settings():
    """Tải cài đặt từ settings.json, nếu chưa có thì dùng mặc định."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings = DEFAULT_SETTINGS.copy()
                settings.update(saved)
                return settings
        except Exception as e:
            print(f"Lỗi khi đọc {SETTINGS_FILE}: {e}. Sử dụng cấu hình mặc định.")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Lưu cấu hình mới vào settings.json."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Lỗi khi lưu {SETTINGS_FILE}: {e}")
        return False

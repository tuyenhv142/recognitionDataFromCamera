import os
import sys
import io
import csv
import cv2
import time
from datetime import datetime
from collections import deque
import threading



class DataLogger:
    """Quản lý ghi dữ liệu ra file CSV và lưu ảnh chụp màn hình minh chứng."""
    
    def __init__(self, data_dir="data", snapshot_dir="snapshots"):
        self.data_dir = data_dir
        self.snapshot_dir = snapshot_dir
        self.lock = threading.Lock()
        
        # Đảm bảo thư mục tồn tại
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.snapshot_dir, exist_ok=True)
        
        # Bộ đệm lưu 100 bản ghi gần nhất phục vụ hiển thị trực tiếp trên giao diện web
        self.recent_records = deque(maxlen=100)
        self.total_recorded = 0
        self.last_logged_value = None
        self.last_log_time = 0
        self._last_mtime = 0

        # Tự động nạp toàn bộ lịch sử từ file CSV hiện có
        self._load_from_csv()

    def get_csv_filename(self):
        """Tên file CSV theo ngày hiện tại: readings_YYYY-MM-DD.csv"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.data_dir, f"readings_{today_str}.csv")

    def _sync_if_file_modified(self):
        """Tự động đồng bộ lại bộ nhớ nếu người dùng chỉnh sửa hoặc xóa trực tiếp trong file CSV."""
        csv_path = self.get_csv_filename()
        if os.path.exists(csv_path):
            try:
                mtime = os.path.getmtime(csv_path)
                if mtime != self._last_mtime:
                    self._load_from_csv()
            except Exception:
                pass

    def _load_from_csv(self):
        """Khôi phục toàn bộ lịch sử từ file CSV hiện có để khi reload trang web không bao giờ bị mất."""
        csv_path = self.get_csv_filename()
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            try:
                self._last_mtime = os.path.getmtime(csv_path)
                records = []
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)  # Bỏ qua tiêu đề
                    for row in reader:
                        if len(row) >= 4:
                            records.append({
                                "timestamp": row[0],
                                "value": row[1],
                                "confidence": row[2],
                                "snapshot": row[3],
                                "status": row[4] if len(row) > 4 else "OK"
                            })
                self.total_recorded = len(records)
                self.recent_records.clear()
                if records:
                    self.last_logged_value = records[-1]["value"]
                    for r in records:
                        self.recent_records.appendleft(r)
                else:
                    self.last_logged_value = None
                print(f"[*] Successfully synchronized {len(records)} records from {os.path.basename(csv_path)}")
            except Exception as e:
                print(f"Error reading CSV file: {e}")

    def _ensure_header(self, filepath):
        """Tạo tiêu đề cột nếu file CSV chưa có."""
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            with open(filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])

    def log_reading(self, value, confidence, frame=None, save_snapshot=True, force=False):
        """
        Ghi một bản ghi vào CSV và lưu ảnh chụp màn hình nếu cần.
        Trả về dictionary bản ghi vừa ghi, hoặc None nếu không ghi.
        """
        if value is None:
            return None

        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Lấy đến mili-giây
        time_tag = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]

        snapshot_rel_path = ""
        
        # Lưu ảnh nếu được bật và có frame
        if save_snapshot and frame is not None:
            safe_val = str(value).replace(".", "_").replace("-", "neg")
            snapshot_filename = f"snap_{time_tag}_{safe_val}.jpg"
            snapshot_full_path = os.path.join(self.snapshot_dir, snapshot_filename)
            
            # Lưu ảnh nén JPEG chất lượng cao
            try:
                cv2.imwrite(snapshot_full_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                snapshot_rel_path = snapshot_filename
            except Exception as e:
                print(f"Error saving snapshot: {e}")

        csv_path = self.get_csv_filename()
        conf_percent = f"{confidence * 100:.1f}%" if isinstance(confidence, (float, int)) else str(confidence)
        record = {
            "timestamp": timestamp_str,
            "value": str(value),
            "confidence": conf_percent,
            "snapshot": snapshot_rel_path,
            "status": "OK"
        }

        with self.lock:
            try:
                self._ensure_header(csv_path)
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        record["timestamp"],
                        record["value"],
                        record["confidence"],
                        record["snapshot"],
                        record["status"]
                    ])
                    f.flush()
                    os.fsync(f.fileno())

                self.recent_records.appendleft(record)
                self.total_recorded += 1
                self.last_logged_value = str(value)
                self.last_log_time = time.time()
                try:
                    self._last_mtime = os.path.getmtime(csv_path)
                except Exception:
                    pass
                return record
            except Exception as e:
                print(f"Error writing to CSV file: {e}")
                return None

    def get_recent(self, limit=50):
        with self.lock:
            self._sync_if_file_modified()
            return list(self.recent_records)[:limit]

    def get_stats(self):
        with self.lock:
            self._sync_if_file_modified()
            return {
                "total_recorded": self.total_recorded,
                "last_value": self.last_logged_value,
                "current_csv": os.path.basename(self.get_csv_filename())
            }

    def delete_record(self, timestamp=None, snapshot=None, delete_snapshot_file=True):
        """Xóa một bản ghi cụ thể khỏi file CSV và bộ nhớ đệm."""
        return self.delete_records(
            timestamps=[timestamp] if timestamp else [],
            snapshots=[snapshot] if snapshot else [],
            delete_snapshot_file=delete_snapshot_file
        )

    def delete_records(self, timestamps=None, snapshots=None, delete_snapshot_file=True):
        """Xóa danh sách bản ghi theo timestamp hoặc snapshot, cập nhật lại file CSV và xóa ảnh minh chứng."""
        ts_set = set(timestamps or [])
        sn_set = set(snapshots or [])
        if not ts_set and not sn_set:
            return 0

        with self.lock:
            csv_path = self.get_csv_filename()
            if not os.path.exists(csv_path):
                return 0

            kept_records = []
            deleted_count = 0
            deleted_snaps = []

            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    for row in reader:
                        if not row or len(row) < 4:
                            continue
                        r_time = row[0]
                        r_snap = row[3]
                        if (r_time in ts_set) or (r_snap in sn_set):
                            deleted_count += 1
                            if r_snap:
                                deleted_snaps.append(r_snap)
                        else:
                            kept_records.append(row)

                # Ghi lại file CSV sạch
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])
                    for row in kept_records:
                        writer.writerow(row)
                    f.flush()
                    os.fsync(f.fileno())

                self._last_mtime = os.path.getmtime(csv_path)

                # Cập nhật bộ nhớ đệm deque
                self.recent_records = deque(maxlen=100)
                for row in kept_records:
                    self.recent_records.appendleft({
                        "timestamp": row[0],
                        "value": row[1],
                        "confidence": row[2],
                        "snapshot": row[3],
                        "status": row[4] if len(row) > 4 else "OK"
                    })

                self.total_recorded = len(kept_records)
                self.last_logged_value = kept_records[-1][1] if kept_records else None

                # Xóa file ảnh snapshot trên đĩa
                if delete_snapshot_file:
                    for snap_name in deleted_snaps:
                        snap_full = os.path.join(self.snapshot_dir, snap_name)
                        if os.path.exists(snap_full):
                            try:
                                os.remove(snap_full)
                            except Exception:
                                pass

                return deleted_count
            except Exception as e:
                print(f"Error deleting records: {e}")
                return 0

    def clear_all(self, delete_snapshot_files=True):
        """Xóa toàn bộ dữ liệu trong file CSV ngày hiện tại."""
        with self.lock:
            csv_path = self.get_csv_filename()
            deleted_snaps = [r["snapshot"] for r in self.recent_records if r.get("snapshot")]
            try:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])
                    f.flush()
                    os.fsync(f.fileno())

                self._last_mtime = os.path.getmtime(csv_path)
                self.recent_records.clear()
                self.total_recorded = 0
                self.last_logged_value = None

                if delete_snapshot_files:
                    for snap_name in deleted_snaps:
                        snap_full = os.path.join(self.snapshot_dir, snap_name)
                        if os.path.exists(snap_full):
                            try:
                                os.remove(snap_full)
                            except Exception:
                                pass
                return True
            except Exception as e:
                print(f"Error clearing CSV: {e}")
                return False

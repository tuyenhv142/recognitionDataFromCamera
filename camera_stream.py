import cv2
import time
import threading
import numpy as np

class CameraManager:
    """Quản lý luồng video từ Camera qua mạng LAN với cơ chế đọc đa luồng (non-blocking) và tự động kết nối lại."""
    
    def __init__(self, camera_url):
        self.camera_url = camera_url
        self.cap = None
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self.fps = 0.0
        self.last_frame_time = time.time()
        self.thread = None
        self.reconnect_delay = 3.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self._release_cap()

    def update_url(self, new_url):
        """Thay đổi URL camera trong khi đang chạy."""
        if new_url != self.camera_url:
            self.camera_url = new_url
            self._release_cap()

    def _release_cap(self):
        with self.lock:
            self.connected = False
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    def _capture_loop(self):
        frame_count = 0
        fps_start = time.time()

        while self.running:
            if self.cap is None or not self.cap.isOpened():
                try:
                    self.cap = cv2.VideoCapture(self.camera_url)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    # Thiết lập timeout chống treo kết nối mạng khi chạy 24h
                    try:
                        self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                        self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                    except Exception:
                        pass

                    if self.cap.isOpened():
                        self.connected = True
                    else:
                        self.connected = False
                        time.sleep(self.reconnect_delay)
                        continue
                except Exception as e:
                    self.connected = False
                    time.sleep(self.reconnect_delay)
                    continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.connected = False
                self._release_cap()
                time.sleep(1.0)
                continue

            current_time = time.time()
            frame_count += 1
            if current_time - fps_start >= 1.0:
                self.fps = round(frame_count / (current_time - fps_start), 1)
                frame_count = 0
                fps_start = current_time

            with self.lock:
                self.latest_frame = frame
                self.connected = True
                self.last_frame_time = current_time

            # Nghỉ rất ngắn để nhường CPU
            time.sleep(0.01)

    def get_frame(self):
        """Lấy bản sao frame mới nhất (luôn cập nhật thời gian thực)."""
        with self.lock:
            if self.latest_frame is not None:
                return True, self.latest_frame.copy()
            return False, None

    def is_alive(self):
        return self.connected and (time.time() - self.last_frame_time < 4.0)

    def get_annotated_frame(self, roi=None, current_value=None, is_logging=False):
        """Trả về frame có vẽ khung ROI và thông tin nhận diện cho luồng xem trực tiếp."""
        ret, frame = self.get_frame()
        if not ret or frame is None:
            # Tạo frame màu xám báo hiệu mất kết nối
            blank = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(blank, "Connecting to camera...", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            return blank

        h, w, _ = frame.shape
        display_frame = frame.copy()

        # Vẽ khung ROI nếu có
        if roi:
            rx = max(0, min(roi.get("x", 0), w - 10))
            ry = max(0, min(roi.get("y", 0), h - 10))
            rw = max(10, min(roi.get("w", 50), w - rx))
            rh = max(10, min(roi.get("h", 30), h - ry))

            # Màu xanh neon nổi bật
            box_color = (0, 255, 0) if not is_logging else (0, 0, 255)
            cv2.rectangle(display_frame, (rx, ry), (rx + rw, ry + rh), box_color, 2)
            cv2.putText(display_frame, "LCD ROI", (rx, max(ry - 5, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, box_color, 1)

        # Vẽ trạng thái ghi REC
        if is_logging:
            cv2.circle(display_frame, (18, 18), 6, (0, 0, 255), -1)
            cv2.putText(display_frame, "REC", (30, 23),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # Hiển thị số đo hiện tại góc dưới
        if current_value is not None:
            text = f"Reading: {current_value}"
            cv2.putText(display_frame, text, (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

        return display_frame

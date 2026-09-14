import cv2
import re
import numpy as np
from rapidocr_onnxruntime import RapidOCR

class LCDReader:
    """Module nhận diện số từ màn hình LCD 7 đoạn tối ưu hóa nhận diện toàn dải số (0-9)."""
    
    def __init__(self):
        # Khởi tạo mô hình RapidOCR
        self.engine = RapidOCR()
        self.char_map = str.maketrans({
            'O': '0', 'o': '0', 'D': '0',
            'I': '1', 'l': '1', '|': '1', '!': '1', 'i': '1',
            'Z': '2', 'z': '2',
            'S': '5', 's': '5',
            'B': '8',
            'b': '6',
            'q': '9'
        })

    def crop_roi(self, frame, roi):
        """Cắt vùng quan tâm (ROI) một cách an toàn từ khung hình."""
        if frame is None:
            return None
        h, w, _ = frame.shape
        x = max(0, min(roi.get("x", 0), w - 5))
        y = max(0, min(roi.get("y", 0), h - 5))
        rw = max(5, min(roi.get("w", 50), w - x))
        rh = max(5, min(roi.get("h", 30), h - y))
        
        crop = frame[y:y+rh, x:x+rw]
        return crop

    def trim_bezel_borders(self, crop):
        """Tự động loại bỏ các hàng viền bóng/vỏ nhựa tối màu ở mép trên của khung hình."""
        if crop is None or crop.shape[0] < 20 or crop.shape[1] < 30:
            return crop
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        h, w = gray.shape
        top_cut = 0
        for r in range(min(6, h // 5)):
            if np.mean(gray[r, :]) < 105:
                top_cut = r + 1
            else:
                break
        if top_cut > 0 and h - top_cut >= 15:
            return crop[top_cut:, :]
        return crop

    def validate_7_segment_digits(self, val_str, crop):
        """
        Xác minh vật lý hiển thị 7 đoạn: Phân biệt triệt để giữa số 1 và số 7.
        Trên màn hình LCD 7 đoạn:
        - Số 7 BẮT BUỘC phải bật thanh ngang trên cùng (segment a).
        - Số 1 CHỈ CÓ thanh đứng bên phải (segment b, c), KHÔNG CÓ thanh ngang trên cùng.
        Nếu nhận diện ra '7' nhưng vị trí thanh ngang trên cùng là nền sáng,
        thì chữ số đó chắc chắn là số 1 do nét nghiêng bị OCR nhầm lẫn.
        """
        if not val_str or '7' not in val_str or crop is None or crop.size == 0:
            return val_str
        try:
            h, w = crop.shape[:2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            # Vùng tọa độ ngang của thanh trên cùng (segment a) cho 4 chữ số:
            slot_x_ranges = [
                (int(w * 0.09), int(w * 0.19)),
                (int(w * 0.33), int(w * 0.43)),
                (int(w * 0.56), int(w * 0.66)),
                (int(w * 0.74), int(w * 0.84))
            ]
            y1 = max(0, int(h * 0.12))
            y2 = min(h, int(h * 0.30))
            digits = [c for c in val_str if c.isdigit()]
            if len(digits) != 4:
                if val_str.endswith('7'):
                    box = gray[y1:y2, int(w * 0.74):int(w * 0.84)]
                    if box.size > 0 and (np.min(box) >= 105 or np.mean(box) >= 135):
                        return val_str[:-1] + '1'
                return val_str

            new_digits = list(digits)
            for idx, d in enumerate(digits):
                if d == '7' and idx < len(slot_x_ranges):
                    x1, x2 = slot_x_ranges[idx]
                    box = gray[y1:y2, x1:x2]
                    if box.size > 0:
                        min_pixel = np.min(box)
                        mean_pixel = np.mean(box)
                        # Nếu thanh trên cùng là nền sáng (không có nét hiển thị), đây là số 1
                        if min_pixel >= 105 or mean_pixel >= 135:
                            new_digits[idx] = '1'
            return f"{new_digits[0]}.{''.join(new_digits[1:])}"
        except Exception:
            return val_str

    def clean_text(self, text):
        """Làm sạch chuỗi nhận diện, sửa các ký tự 7 đoạn hay nhầm và định dạng chuẩn X.XXX."""
        if not text:
            return None
        
        clean = text.translate(self.char_map).strip()
        
        # Trường hợp 1: Có sẵn dấu chấm thập phân, ví dụ "0.001", "0.000", "1.234"
        match_dot = re.findall(r'[-+]?\d+\.\d+', clean)
        if match_dot:
            val_str = match_dot[0]
            # Chuẩn hóa nếu thiếu số sau dấu chấm (ví dụ "0.00" thành "0.000" nếu không có số thứ 4)
            parts = val_str.split('.')
            if len(parts) == 2 and len(parts[1]) == 2:
                # Nếu chỉ đọc được 2 chữ số thập phân, giữ nguyên hoặc kiểm tra
                return val_str
            return val_str

        # Trường hợp 2: Đọc được chuỗi 4 chữ số liền nhau (ví dụ "0001", "0000")
        digits_only = re.findall(r'\d', clean)
        if len(digits_only) == 4:
            return digits_only[0] + '.' + "".join(digits_only[1:4])
        elif len(digits_only) > 4:
            return digits_only[0] + '.' + "".join(digits_only[1:4])

        # Trường hợp 3: Tìm số có dạng chuẩn 4 chữ số hoặc có dấu chấm
        matches = re.findall(r'\d+(?:\.\d+)?', clean)
        if matches:
            for m in matches:
                # Nếu chuỗi gồm 4 chữ số liền (ví dụ 0001, 0003), tự chèn dấu chấm
                if len(m) == 4 and '.' not in m:
                    return m[0] + '.' + m[1:]
                # Nếu chuỗi có dấu chấm và ít nhất 2 chữ số thập phân
                if '.' in m and len(m) >= 4:
                    return m

        return None

    def read_value(self, frame, roi):
        """
        Nhận diện số từ khung hình tại vùng ROI chỉ định.
        Sử dụng trực tiếp Text Recognizer trên vùng cắt LCD để không bị bỏ sót chữ số ngoài cùng (như số 1).
        Trả về: (giá trị số hoặc None, độ tin cậy float 0-1, ảnh crop đã tiền xử lý)
        """
        crop = self.crop_roi(frame, roi)
        if crop is None or crop.size == 0:
            return None, 0.0, None

        # Tự động loại bỏ viền vỏ/bóng tối ở mép trên nếu có
        crop = self.trim_bezel_borders(crop)

        candidates = []

        try:
            # Batch nhận diện: 1 ảnh gốc + 1 ảnh có đệm viền 5px
            pad5 = cv2.copyMakeBorder(crop, 5, 5, 5, 5, cv2.BORDER_REPLICATE)
            rec_results, _ = self.engine.text_recognizer([crop, pad5])

            for item in rec_results:
                if item and len(item) >= 2:
                    raw_text, score = str(item[0]), float(item[1])
                    cleaned = self.clean_text(raw_text)
                    if cleaned:
                        # Xác thực vật lý hiển thị 7 đoạn: loại bỏ hoàn toàn nhầm lẫn giữa 1 và 7
                        cleaned = self.validate_7_segment_digits(cleaned, crop)
                        # Ưu tiên kết quả có đủ 4 chữ số dạng X.XXX
                        bonus = 0.15 if ('.' in cleaned and len(cleaned.replace('.', '')) >= 4) else 0.0
                        candidates.append((cleaned, score + bonus, score))

            # Nếu recognizer chưa bắt được, thử chạy qua pipeline đầy đủ làm fallback
            if not candidates:
                pad15 = cv2.copyMakeBorder(crop, 15, 15, 15, 15, cv2.BORDER_REPLICATE)
                full_res, _ = self.engine(pad15)
                if full_res:
                    for item in full_res:
                        raw_text, score = str(item[1]), float(item[2])
                        cleaned = self.clean_text(raw_text)
                        if cleaned:
                            cleaned = self.validate_7_segment_digits(cleaned, crop)
                            candidates.append((cleaned, score, score))

            if candidates:
                # Chọn kết quả có điểm ưu tiên cao nhất
                candidates.sort(key=lambda x: x[1], reverse=True)
                best_val, _, actual_score = candidates[0]
                return best_val, actual_score, crop

            return None, 0.0, crop

        except Exception as e:
            print(f"Error in OCR digit recognition: {e}")
            return None, 0.0, crop

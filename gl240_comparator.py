import os
import sys
import csv
import glob
import datetime
from typing import Dict, Any, List, Optional

# Thêm đường dẫn venv chứa pymysql nếu môi trường hiện tại chưa có sẵn
_extra_site_packages = [
    r"c:\Users\user8\Documents\code\experiment\.venv\Lib\site-packages"
]
for p in _extra_site_packages:
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)

try:
    import pymysql
    import pymysql.cursors
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# Cấu hình CSDL Local GL240
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "admin",
    "database": "gl240",
    "connect_timeout": 3
}

def get_db_connection():
    """Tạo kết nối tới CSDL MySQL local gl240."""
    if not HAS_PYMYSQL:
        return None
    try:
        return pymysql.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"[gl240_comparator] MySQL connection error: {e}")
        return None

def get_available_compare_dates(data_dir: str = "data") -> List[str]:
    """
    Lấy danh sách các ngày khả dụng từ cả CSDL GL240 và các file CSV Camera.
    Sắp xếp giảm dần (ngày mới nhất trước).
    """
    dates_set = set()

    # 1. Quét từ CSDL MySQL gl240
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT DATE_FORMAT(bucket_start, '%Y-%m-%d') AS d_str 
                    FROM neutron_counts 
                    ORDER BY d_str DESC;
                """)
                for row in cur.fetchall():
                    if row and row.get("d_str"):
                        dates_set.add(row["d_str"])
        except Exception as e:
            print(f"[gl240_comparator] Query dates error: {e}")
        finally:
            conn.close()

    # 2. Quét từ các file readings_YYYY-MM-DD.csv
    csv_pattern = os.path.join(data_dir, "readings_*.csv")
    for filepath in glob.glob(csv_pattern):
        basename = os.path.basename(filepath)
        # readings_YYYY-MM-DD.csv
        parts = basename.replace(".csv", "").split("_")
        if len(parts) >= 2:
            d_part = parts[1]
            if len(d_part) == 10 and d_part.count("-") == 2:
                dates_set.add(d_part)

    # Nếu hôm nay chưa có, thêm ngày hôm nay
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    dates_set.add(today_str)

    return sorted(list(dates_set), reverse=True)

def fetch_gl240_records(date_str: str) -> List[Dict[str, Any]]:
    """Truy vấn các bản ghi neutron_counts từ CSDL gl240 cho ngày date_str."""
    conn = get_db_connection()
    if not conn:
        return []

    records = []
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT id, bucket_start, bucket_end, count, temperature_c, dead_time_s, created_at, progress_id 
                FROM neutron_counts 
                WHERE bucket_start >= %s AND bucket_start <= %s 
                ORDER BY bucket_start ASC;
            """
            start_dt = f"{date_str} 00:00:00"
            end_dt = f"{date_str} 23:59:59"
            cur.execute(sql, (start_dt, end_dt))
            raw_rows = cur.fetchall()

            for row in raw_rows:
                b_start = row["bucket_start"]
                b_end = row["bucket_end"]
                duration_s = round((b_end - b_start).total_seconds(), 1) if (b_start and b_end) else 0

                records.append({
                    "id": row["id"],
                    "bucket_start": b_start.strftime("%Y-%m-%d %H:%M:%S") if b_start else "",
                    "bucket_start_dt": b_start,
                    "bucket_end": b_end.strftime("%Y-%m-%d %H:%M:%S") if b_end else "",
                    "bucket_end_dt": b_end,
                    "time_display": b_start.strftime("%H:%M:%S") if b_start else "",
                    "duration_seconds": duration_s,
                    "count": int(row["count"]),
                    "temperature_c": float(row["temperature_c"]) if row.get("temperature_c") is not None else None,
                    "dead_time_s": float(row["dead_time_s"]) if row.get("dead_time_s") is not None else None,
                    "progress_id": row.get("progress_id")
                })
    except Exception as e:
        print(f"[gl240_comparator] Error reading neutron_counts for {date_str}: {e}")
    finally:
        conn.close()

    return records

def fetch_camera_records(date_str: str, data_dir: str = "data") -> List[Dict[str, Any]]:
    """Đọc các bản ghi nhận diện từ file readings_YYYY-MM-DD.csv."""
    csv_file = os.path.join(data_dir, f"readings_{date_str}.csv")
    if not os.path.exists(csv_file):
        return []

    records = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            idx = 0
            for row in reader:
                if not row or len(row) < 4:
                    continue
                raw_ts = row[0].strip()
                raw_val = row[1].strip()
                raw_conf = row[2].strip()
                raw_snap = row[3].strip()
                raw_status = row[4].strip() if len(row) > 4 else "OK"

                # Parse timestamp
                try:
                    if "." in raw_ts:
                        ts_dt = datetime.datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S.%f")
                    else:
                        ts_dt = datetime.datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                try:
                    val_float = float(raw_val)
                    val_int = int(round(val_float * 1000))
                except (ValueError, TypeError):
                    val_float = 0.0
                    val_int = 0

                records.append({
                    "cam_id": idx,
                    "timestamp": raw_ts,
                    "timestamp_dt": ts_dt,
                    "time_display": ts_dt.strftime("%H:%M:%S"),
                    "value": raw_val,
                    "value_float": val_float,
                    "value_int": val_int,
                    "confidence": raw_conf,
                    "snapshot": raw_snap,
                    "status": raw_status
                })
                idx += 1
    except Exception as e:
        print(f"[gl240_comparator] Error reading CSV camera for {date_str}: {e}")

    return records

def compare_neutron_and_camera(
    date_str: str,
    data_dir: str = "data",
    min_delay: float = 15.0,
    max_delay: float = 95.0
) -> Dict[str, Any]:
    """
    So sánh, đối chiếu và ghép cặp giữa Neutron GL240 và Camera OCR theo ngày.
    
    Quy tắc nghiệp vụ:
    - Thời gian xuất hiện neutron (bucket_start) xảy ra TRƯỚC camera khoảng 30s đến 1m - 1m30s (min_delay đến max_delay).
    - Nếu thời gian camera nằm trong khoảng trễ (dt = t_camera - t_neutron_start) và số lượng neutron trùng khớp (count == value_int),
      đánh dấu trạng thái 'CORRECT'.
    """
    gl_records = fetch_gl240_records(date_str)
    cam_records = fetch_camera_records(date_str, data_dir=data_dir)

    # Chuẩn bị dữ liệu ghép đôi
    gl_matched_map = {}  # gl_id -> cam record
    cam_matched_map = {} # cam_id -> gl record

    # Danh sách độ trễ của các cặp khớp chuẩn
    correct_delays = []

    # Ghép cặp ưu tiên thời gian sớm nhất
    used_cam_ids = set()

    for gl in gl_records:
        gl_id = gl["id"]
        n_start = gl["bucket_start_dt"]
        n_count = gl["count"]
        if not n_start:
            continue

        best_cam = None
        best_dt = None
        best_is_exact = False

        for c in cam_records:
            c_id = c["cam_id"]
            if c_id in used_cam_ids:
                continue

            dt = (c["timestamp_dt"] - n_start).total_seconds()

            # 1. Khớp hoàn hảo: trong khoảng min_delay - max_delay và đúng số lượng count
            if min_delay <= dt <= max_delay and c["value_int"] == n_count:
                best_cam = c
                best_dt = dt
                best_is_exact = True
                break
            # 2. Khớp trong khoảng mở rộng (0s đến max_delay + 30s) và đúng count
            elif 0.0 <= dt <= (max_delay + 30.0) and c["value_int"] == n_count:
                if best_cam is None or abs(dt - 35.0) < abs(best_dt - 35.0):
                    best_cam = c
                    best_dt = dt
                    best_is_exact = True
            # 3. Khớp thời gian nhưng lệch số lượng count
            elif min_delay <= dt <= max_delay and not best_is_exact:
                if best_cam is None:
                    best_cam = c
                    best_dt = dt

        if best_cam:
            c_id = best_cam["cam_id"]
            is_correct = (best_cam["value_int"] == n_count)
            match_status = "CORRECT" if is_correct else "MISMATCH"

            gl_match_info = {
                "status": match_status,
                "is_correct": is_correct,
                "delay_seconds": round(best_dt, 1),
                "cam_id": c_id,
                "cam_time": best_cam["time_display"],
                "cam_timestamp": best_cam["timestamp"],
                "cam_value": best_cam["value"],
                "cam_snapshot": best_cam["snapshot"]
            }
            gl_matched_map[gl_id] = gl_match_info

            cam_match_info = {
                "status": match_status,
                "is_correct": is_correct,
                "delay_seconds": round(best_dt, 1),
                "gl_id": gl_id,
                "gl_time": gl["time_display"],
                "gl_start": gl["bucket_start"],
                "gl_count": n_count
            }
            cam_matched_map[c_id] = cam_match_info

            if is_correct:
                correct_delays.append(best_dt)
                used_cam_ids.add(c_id)
        else:
            gl_matched_map[gl_id] = {
                "status": "NO_CAMERA",
                "is_correct": False,
                "delay_seconds": None,
                "cam_id": None
            }

    # Bổ sung thông tin đối chiếu vào từng bản ghi GL240
    formatted_gl_list = []
    total_gl_counts = 0
    correct_count = 0
    mismatch_count = 0
    no_cam_count = 0

    for gl in gl_records:
        gl_id = gl["id"]
        total_gl_counts += gl["count"]
        m_info = gl_matched_map.get(gl_id, {"status": "NO_CAMERA", "is_correct": False})
        
        if m_info["status"] == "CORRECT":
            correct_count += 1
        elif m_info["status"] == "MISMATCH":
            mismatch_count += 1
        else:
            no_cam_count += 1

        item = {
            "id": gl["id"],
            "bucket_start": gl["bucket_start"],
            "bucket_end": gl["bucket_end"],
            "time_display": gl["time_display"],
            "duration_seconds": gl["duration_seconds"],
            "count": gl["count"],
            "temperature_c": gl["temperature_c"],
            "dead_time_s": gl["dead_time_s"],
            "progress_id": gl["progress_id"],
            "match": m_info
        }
        formatted_gl_list.append(item)

    # Bổ sung thông tin đối chiếu vào từng bản ghi Camera
    formatted_cam_list = []
    unmatched_cam_count = 0

    for c in cam_records:
        c_id = c["cam_id"]
        m_info = cam_matched_map.get(c_id, {"status": "EXTRA_CAMERA", "is_correct": False, "gl_id": None})
        if not m_info.get("is_correct"):
            unmatched_cam_count += 1

        item = {
            "cam_id": c["cam_id"],
            "timestamp": c["timestamp"],
            "time_display": c["time_display"],
            "value": c["value"],
            "value_float": c["value_float"],
            "value_int": c["value_int"],
            "confidence": c["confidence"],
            "snapshot": c["snapshot"],
            "status": c["status"],
            "match": m_info
        }
        formatted_cam_list.append(item)

    # Tính toán chỉ số thống kê
    total_gl = len(formatted_gl_list)
    total_cam = len(formatted_cam_list)
    accuracy_pct = round((correct_count / total_gl * 100), 1) if total_gl > 0 else 0.0
    avg_delay = round(sum(correct_delays) / len(correct_delays), 1) if correct_delays else 0.0

    summary = {
        "date": date_str,
        "total_gl_events": total_gl,
        "total_gl_neutrons": total_gl_counts,
        "total_camera_readings": total_cam,
        "correct_matches": correct_count,
        "mismatched_matches": mismatch_count,
        "no_camera_count": no_cam_count,
        "unmatched_camera_count": unmatched_cam_count,
        "accuracy_percent": accuracy_pct,
        "avg_delay_seconds": avg_delay,
        "min_delay_used": min_delay,
        "max_delay_used": max_delay
    }

    return {
        "success": True,
        "summary": summary,
        "gl_events": formatted_gl_list,
        "camera_readings": formatted_cam_list
    }

import os
import csv
import glob
import re
from datetime import datetime

def is_suspicious_value(val_str, conf_float):
    """
    Phân loại xem một bản ghi có phải là bất thường / nghi vấn không:
    1. Giá trị quá lớn (>= 0.010, ví dụ 8.000, 2.000, 6.000, 0.800, 0.088...)
    2. Định dạng không chuẩn (thiếu dấu chấm, quá nhiều chữ số, ví dụ 000.1, 8.008)
    3. Độ tin cậy thấp (< 60%)
    4. Số 0.007 (dễ nhầm với 0.001 trên màn hình 7 thanh LCD)
    5. Giá trị <= 0
    """
    anomalies = []
    
    if not val_str:
        return True, ["Thiếu giá trị (Empty)"]

    # Làm sạch chuỗi
    clean_val = str(val_str).strip()

    # Kiểm tra số 0.007
    if "7" in clean_val:
        anomalies.append("Nghi vấn 7-segment (chứa số 7)")

    # Kiểm tra định dạng số thực
    try:
        fval = float(clean_val)
        if fval <= 0.0:
            anomalies.append("Giá trị <= 0 (Baseline)")
        elif fval >= 0.010:
            anomalies.append(f"Giá trị bất thường (Spike: {clean_val})")
        elif fval < 0.001:
            anomalies.append(f"Giá trị cực nhỏ: {clean_val}")
    except (ValueError, TypeError):
        anomalies.append(f"Định dạng lỗi: {clean_val}")

    # Kiểm tra format chuẩn (dạng X.XXX hoặc X.XX)
    if not re.match(r'^\d+\.\d{2,3}$', clean_val):
        if "Định dạng lỗi" not in str(anomalies):
            anomalies.append(f"Format lạ: {clean_val}")

    # Kiểm tra độ tin cậy
    if conf_float < 60.0:
        anomalies.append(f"Độ tin cậy thấp ({conf_float:.1f}%)")

    return len(anomalies) > 0, anomalies

def get_available_dates(data_dir="data", snapshot_dir="snapshots"):
    """Liệt kê các ngày có dữ liệu CSV kèm thống kê sơ bộ."""
    files = glob.glob(os.path.join(data_dir, "readings_*.csv"))
    dates_info = []

    # Danh sách ảnh thực tế trên đĩa
    existing_snaps = set(os.listdir(snapshot_dir)) if os.path.exists(snapshot_dir) else set()

    for fp in sorted(files, reverse=True):
        basename = os.path.basename(fp)
        match = re.search(r'readings_(\d{4}-\d{2}-\d{2})\.csv', basename)
        if not match:
            continue
        date_str = match.group(1)

        record_count = 0
        snap_count = 0
        suspicious_count = 0

        try:
            with open(fp, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row or len(row) < 3:
                        continue
                    record_count += 1
                    val = row[1] if len(row) > 1 else ""
                    conf_raw = row[2] if len(row) > 2 else "0"
                    snap = row[3] if len(row) > 3 else ""

                    try:
                        conf_f = float(str(conf_raw).replace("%", "").strip())
                    except ValueError:
                        conf_f = 0.0

                    has_file = snap in existing_snaps if snap else False
                    if has_file:
                        snap_count += 1

                    is_susp, _ = is_suspicious_value(val, conf_f)
                    if is_susp or (snap and not has_file):
                        suspicious_count += 1
        except Exception as e:
            print(f"Error reading {fp}: {e}")

        dates_info.append({
            "date": date_str,
            "filename": basename,
            "total_records": record_count,
            "existing_snapshots": snap_count,
            "suspicious_records": suspicious_count
        })

    return dates_info

def load_date_records(data_dir="data", snapshot_dir="snapshots", date_str=None):
    """Nạp danh sách chi tiết các bản ghi của 1 ngày và gắn cờ phân tích."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    csv_path = os.path.join(data_dir, f"readings_{date_str}.csv")
    if not os.path.exists(csv_path):
        return {"records": [], "stats": {"total": 0, "suspicious": 0, "outliers": 0, "missing_images": 0, "low_conf": 0, "clean": 0}}

    existing_snaps = set(os.listdir(snapshot_dir)) if os.path.exists(snapshot_dir) else set()

    records = []
    stats = {
        "total": 0,
        "suspicious": 0,
        "outliers": 0,
        "missing_images": 0,
        "low_conf": 0,
        "seven_suspects": 0,
        "clean": 0
    }

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if not row or len(row) < 3:
                    continue

                ts = row[0]
                val = row[1]
                conf_raw = row[2]
                snap = row[3] if len(row) > 3 else ""
                status = row[4] if len(row) > 4 else "OK"

                try:
                    conf_f = float(str(conf_raw).replace("%", "").strip())
                except ValueError:
                    conf_f = 0.0

                file_exists = (snap in existing_snaps) if snap else False

                is_susp, anomalies = is_suspicious_value(val, conf_f)
                if snap and not file_exists:
                    anomalies.append("Thiếu file ảnh trên đĩa (Missing JPG)")
                    is_susp = True
                    stats["missing_images"] += 1

                if any("Giá trị bất thường" in a or "Spike" in a for a in anomalies):
                    stats["outliers"] += 1
                if conf_f < 60.0:
                    stats["low_conf"] += 1
                if "7" in str(val):
                    stats["seven_suspects"] += 1

                if is_susp:
                    stats["suspicious"] += 1
                else:
                    stats["clean"] += 1

                stats["total"] += 1

                records.append({
                    "timestamp": ts,
                    "value": val,
                    "confidence": f"{conf_f:.1f}%",
                    "confidence_num": conf_f,
                    "snapshot": snap,
                    "file_exists": file_exists,
                    "status": status,
                    "is_suspicious": is_susp,
                    "anomalies": anomalies
                })
    except Exception as e:
        print(f"Error loading records for {date_str}: {e}")

    # Sắp xếp mới nhất lên đầu
    records.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"records": records, "stats": stats}

def delete_date_records(data_dir="data", snapshot_dir="snapshots", date_str=None, timestamps=None, snapshots=None, delete_files=True):
    """Xóa danh sách bản ghi khỏi CSV của một ngày nhất định và xóa file ảnh."""
    if not date_str:
        return 0

    csv_path = os.path.join(data_dir, f"readings_{date_str}.csv")
    if not os.path.exists(csv_path):
        return 0

    ts_set = set(timestamps or [])
    sn_set = set(snapshots or [])

    if not ts_set and not sn_set:
        return 0

    kept_records = []
    deleted_count = 0
    deleted_snaps = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or len(row) < 4:
                continue
            r_ts = row[0]
            r_snap = row[3]
            if (r_ts in ts_set) or (r_snap in sn_set):
                deleted_count += 1
                if r_snap:
                    deleted_snaps.append(r_snap)
            else:
                kept_records.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])
        for r in kept_records:
            writer.writerow(r)

    if delete_files and os.path.exists(snapshot_dir):
        for s in deleted_snaps:
            full_p = os.path.join(snapshot_dir, s)
            if os.path.exists(full_p):
                try:
                    os.remove(full_p)
                except Exception:
                    pass

    return deleted_count

def update_record_value(data_dir="data", date_str=None, timestamp=None, new_value=None):
    """Sửa giá trị của 1 bản ghi trong file CSV."""
    if not date_str or not timestamp or new_value is None:
        return False

    csv_path = os.path.join(data_dir, f"readings_{date_str}.csv")
    if not os.path.exists(csv_path):
        return False

    updated = False
    all_rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or len(row) < 4:
                continue
            if row[0] == timestamp:
                row[1] = str(new_value).strip()
                updated = True
            all_rows.append(row)

    if updated:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])
            for r in all_rows:
                writer.writerow(r)

    return updated

def sync_csv_with_disk(data_dir="data", snapshot_dir="snapshots", date_str=None):
    """Xóa tất cả các dòng trong CSV mà file ảnh tương ứng không còn tồn tại trên đĩa."""
    if not date_str:
        return 0, 0

    csv_path = os.path.join(data_dir, f"readings_{date_str}.csv")
    if not os.path.exists(csv_path):
        return 0, 0

    existing_snaps = set(os.listdir(snapshot_dir)) if os.path.exists(snapshot_dir) else set()

    kept_rows = []
    removed_count = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or len(row) < 4:
                continue
            snap = row[3]
            if snap in existing_snaps:
                kept_rows.append(row)
            else:
                removed_count += 1

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Value", "Confidence", "Snapshot", "Status"])
        for r in kept_rows:
            writer.writerow(r)

    return removed_count, len(kept_rows)

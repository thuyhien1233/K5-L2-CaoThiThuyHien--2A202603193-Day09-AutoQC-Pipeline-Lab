"""CHECK BỔ SUNG (THƯỞNG +3 ĐIỂM) — Kiểm tra tỉ lệ khung hình bất thường (Extreme Aspect Ratio).

Test: pytest tests/test_aspect_ratio.py -q

Trong bài toán phát hiện vật thể (car, person, truck, bus), box thường có tỉ lệ khung hình (w/h)
nằm trong khoảng hợp lý. Những box quá dẹt ngang (w >> h) hoặc quá mảnh dọc (w << h)
thường do người gán nhãn vô tình kéo trượt chuột, vẽ sót mép, hoặc gán nhầm dải phân cách/cột cờ.

Check này cảnh báo (WARN) với mã lỗi `BOX_ASPECT_RATIO`:
- w_px / h_px > max_ratio: box quá dẹt ngang (mặc định 12.0)
- w_px / h_px < min_ratio: box quá mảnh dọc (mặc định 0.10)
"""
from ..common import WARN, Issue, parse_yolo_line


def run(ds, cfg):
    issues = []
    ar_cfg = cfg.get("aspect_ratio", {})
    max_ratio = ar_cfg.get("max_ratio", 12.0)
    min_ratio = ar_cfg.get("min_ratio", 0.10)

    for lp in ds.label_files():
        stem = lp.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        size = ds.image_size(stem)
        img_w, img_h = size if size else (1, 1)

        for line_no, raw_line in lines:
            try:
                cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except ValueError:
                continue

            if w <= 0 or h <= 0:
                continue

            # Tính tỉ lệ theo pixel thực tế nếu có kích thước ảnh
            w_px = w * img_w
            h_px = h * img_h
            ratio = w_px / h_px

            if ratio > max_ratio:
                issues.append(Issue(
                    check="aspect_ratio",
                    severity=WARN,
                    code="BOX_ASPECT_RATIO",
                    image=stem,
                    line=line_no,
                    message=f"tỉ lệ khung hình quá dẹt ngang (w/h = {ratio:.2f} > {max_ratio})",
                    extra={"aspect_ratio": round(ratio, 2), "direction": "horizontal_flat"}
                ))
            elif ratio < min_ratio:
                issues.append(Issue(
                    check="aspect_ratio",
                    severity=WARN,
                    code="BOX_ASPECT_RATIO",
                    image=stem,
                    line=line_no,
                    message=f"tỉ lệ khung hình quá mảnh dọc (w/h = {ratio:.2f} < {min_ratio})",
                    extra={"aspect_ratio": round(ratio, 2), "direction": "vertical_thin"}
                ))

    return issues

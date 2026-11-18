"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    issues = []
    fmt_cfg = cfg.get("label_format", {})
    overflow_tol = fmt_cfg.get("overflow_tol", 0.002)
    min_box_px = fmt_cfg.get("min_box_px", 12)
    max_box_frac = fmt_cfg.get("max_box_frac", 0.95)
    dup_box_iou = fmt_cfg.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    for lp in ds.label_files():
        stem = lp.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue

        size = ds.image_size(stem)
        valid_boxes = []

        for line_no, raw_line in lines:
            # 1. Parse YOLO line
            try:
                cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
            except ValueError:
                issues.append(
                    Issue("label_format", ERROR, "BAD_FORMAT", stem,
                          f"dòng nhãn sai định dạng: {raw_line}", line=line_no)
                )
                continue

            # 2. Check class ID
            if not (0 <= cls_id < num_classes):
                issues.append(
                    Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                          f"id lớp {cls_id} ngoài dải hợp lệ 0..{num_classes - 1}", line=line_no)
                )
                continue

            # 3. Check box size > 0
            if w <= 0 or h <= 0:
                issues.append(
                    Issue("label_format", ERROR, "BOX_ZERO", stem,
                          f"kích thước box <= 0 (w={w}, h={h})", line=line_no)
                )
                continue

            box = (cx, cy, w, h)

            # 4. Check overflow
            x1 = cx - w / 2.0
            x2 = cx + w / 2.0
            y1 = cy - h / 2.0
            y2 = cy + h / 2.0
            overflow = max(0.0, -x1, -y1, x2 - 1.0, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(
                    Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                          f"box tràn ra ngoài ảnh (mức tràn {overflow:.4f})",
                          line=line_no, extra={"overflow": overflow})
                )

            # 5. Check duplicate box with previous box of SAME class
            for prev_cls, prev_box in valid_boxes:
                if prev_cls == cls_id and iou_xywh(box, prev_box) > dup_box_iou:
                    issues.append(
                        Issue("label_format", ERROR, "DUP_BOX", stem,
                              f"trùng box với dòng trước đó (IoU > {dup_box_iou})",
                              line=line_no)
                    )
                    break

            valid_boxes.append((cls_id, box))

            # 6. Check tiny box (warning)
            if size is not None:
                img_w, img_h = size
                box_w_px = w * img_w
                box_h_px = h * img_h
                short_side_px = min(box_w_px, box_h_px)
                if short_side_px < min_box_px:
                    issues.append(
                        Issue("label_format", WARN, "BOX_TINY", stem,
                              f"box quá nhỏ (cạnh ngắn {short_side_px:.1f}px < {min_box_px}px)",
                              line=line_no)
                    )

            # 7. Check huge box (warning)
            if w * h > max_box_frac:
                issues.append(
                    Issue("label_format", WARN, "BOX_HUGE", stem,
                          f"box quá lớn (diện tích {w * h:.4f} > {max_box_frac})",
                          line=line_no)
                )

    return issues

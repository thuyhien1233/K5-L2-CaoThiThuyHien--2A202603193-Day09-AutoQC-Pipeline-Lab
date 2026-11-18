"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    if preds is None:
        preds = {}

    so_cfg = cfg.get("second_opinion", {})
    conf_th = so_cfg.get("conf", 0.25)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        size = ds.image_size(stem)
        img_w, img_h = size if size else (1, 1)

        raw_preds = preds.get(stem, [])

        # Lọc dự đoán cho phase 1: conf >= conf_th và diện tích px >= min_area_px
        p_filtered = []
        for r in raw_preds:
            p_cls, p_conf, pcx, pcy, pw, ph = r
            area_px = (pw * img_w) * (ph * img_h)
            if p_conf >= conf_th and area_px >= min_area_px:
                p_filtered.append(r)

        # Lấy nhãn hợp lệ kèm số dòng gốc
        label_lines = ds.read_label_lines(stem)
        valid_labels = []
        if label_lines:
            for line_no, raw_line in label_lines:
                try:
                    c, cx, cy, w, h = parse_yolo_line(raw_line)
                    if 0 <= c < len(ds.classes):
                        valid_labels.append((line_no, c, (cx, cy, w, h)))
                except ValueError:
                    continue

        # 1. Dự đoán của model -> so với nhãn
        for r in p_filtered:
            p_cls, p_conf, pcx, pcy, pw, ph = r
            p_box = (pcx, pcy, pw, ph)

            # Tìm candidates có IoU >= iou_missing
            cands = []
            for line_no, l_cls, l_box in valid_labels:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((line_no, l_cls, l_box, iou))

            if not cands:
                # Không có cands -> POSSIBLE_MISSING
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_MISSING", stem,
                    f"model dự đoán lớp {p_cls} (conf={p_conf:.2f}) nhưng không có box nhãn khớp (IoU < {iou_missing})",
                    line=None, extra={"conf": p_conf}
                ))
            else:
                cands_same = [c for c in cands if c[1] == p_cls]
                if cands_same:
                    best_same = max(cands_same, key=lambda c: c[3])
                    best_iou = best_same[3]
                    if best_iou < iou_loose:
                        issues.append(Issue(
                            "second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                            f"box nhãn cùng lớp {p_cls} nhưng IoU {best_iou:.2f} < {iou_loose}",
                            line=None, extra={"conf": p_conf, "iou": best_iou}
                        ))
                    else:
                        # Nhãn đúng lớp đã phủ vật này
                        pass
                else:
                    best_diff = max(cands, key=lambda c: c[3])
                    best_diff_iou = best_diff[3]
                    if best_diff_iou >= iou_match:
                        issues.append(Issue(
                            "second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                            f"model thấy lớp {p_cls} (conf={p_conf:.2f}), nhãn gán lớp {best_diff[1]} (IoU {best_diff_iou:.2f} >= {iou_match})",
                            line=None, extra={"conf": p_conf, "iou": best_diff_iou}
                        ))
                    else:
                        # Trong [iou_missing, iou_match) khác lớp -> mơ hồ, không cờ gì
                        pass

        # 2. Dòng nhãn -> so với mọi dự đoán (conf >= fp_conf, không lọc diện tích)
        fp_preds = [r for r in raw_preds if r[1] >= fp_conf]
        for line_no, l_cls, l_box in valid_labels:
            is_fp = False
            if not fp_preds:
                is_fp = True
            else:
                if all(iou_xywh(l_box, (r[2], r[3], r[4], r[5])) < iou_missing for r in fp_preds):
                    is_fp = True

            if is_fp:
                issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                    f"box nhãn (dòng {line_no}) không khớp dự đoán nào của model (IoU < {iou_missing})",
                    line=line_no, extra={"iou_missing": iou_missing}
                ))

    return issues

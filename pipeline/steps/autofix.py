"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict
from pathlib import Path

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {
    "DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"
}
DROP_LINE_CODES = {
    "BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"
}


def fix(ds, issues, cfg):
    fixes = []
    # Chỉ xử lý các lỗi severity ERROR
    err_issues = [i for i in issues if i.severity == ERROR]
    if not err_issues:
        return fixes

    removed_images = set()

    # 1. Xử lý xoá ảnh (remove_image)
    for i in err_issues:
        if i.code in REMOVE_IMAGE_CODES and i.image not in removed_images:
            img_path = ds.image_path(i.image)
            lbl_path = ds.label_path(i.image)
            if img_path and img_path.exists():
                img_path.unlink()
            if lbl_path and lbl_path.exists():
                lbl_path.unlink()
            removed_images.add(i.image)
            fixes.append({
                "image": i.image,
                "line": "",
                "action": "remove_image",
                "before": "ảnh/nhãn tồn tại",
                "after": "đã xoá khỏi dataset",
            })

    # 2. Xử lý đổi tên lớp trong data.yaml (rename_classes)
    for i in err_issues:
        if i.code == "BAD_CLASS_NAME":
            before_names = ""
            current_data = {}
            if ds.yaml_path.exists():
                try:
                    current_data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                    before_names = str(current_data.get("names", {}))
                except Exception:
                    pass
            current_data["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(current_data, sort_keys=False), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": before_names,
                "after": str(cfg["classes"]),
            })
            break  # Chỉ xử lý 1 lần cho data.yaml

    # 3. Xử lý ảnh thiếu file nhãn (needs_label)
    seen_needs_label = set()
    for i in err_issues:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed_images and i.image not in seen_needs_label:
            seen_needs_label.add(i.image)
            fixes.append({
                "image": i.image,
                "line": "",
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    # 4. Xử lý sửa theo dòng trong từng file nhãn
    # Gom các issue dòng theo từng stem và theo số dòng gốc
    line_issues = defaultdict(lambda: defaultdict(list))
    for i in err_issues:
        if i.line is not None and i.image not in removed_images:
            line_issues[i.image][int(i.line)].append(i)

    for stem, issues_by_line in line_issues.items():
        lbl_path = ds.label_path(stem)
        if not lbl_path.exists():
            continue

        orig_lines = lbl_path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []

        for l_num in range(1, len(orig_lines) + 1):
            raw_line = orig_lines[l_num - 1]
            cur_issues = issues_by_line.get(l_num, [])

            if not cur_issues:
                # Không có lỗi trên dòng này -> giữ nguyên
                new_lines.append(raw_line)
                continue

            codes_on_line = {iss.code for iss in cur_issues}

            # Quy tắc: xoá dòng thắng, chỉ ghi 1 fix drop_line
            if codes_on_line & DROP_LINE_CODES:
                fixes.append({
                    "image": stem,
                    "line": l_num,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "(đã xoá)",
                })
                # Bỏ dòng này
                continue

            if "BOX_OUT_OF_IMAGE" in codes_on_line:
                try:
                    c, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2.0
                    x2 = cx + w / 2.0
                    y1 = cy - h / 2.0
                    y2 = cy + h / 2.0

                    x1_c = max(0.0, min(1.0, x1))
                    x2_c = max(0.0, min(1.0, x2))
                    y1_c = max(0.0, min(1.0, y1))
                    y2_c = max(0.0, min(1.0, y2))

                    new_w = x2_c - x1_c
                    new_h = y2_c - y1_c

                    if new_w <= 0.0 or new_h <= 0.0:
                        # Box nằm hẳn ngoài ảnh -> xoá dòng
                        fixes.append({
                            "image": stem,
                            "line": l_num,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "(đã xoá do ngoài ảnh)",
                        })
                    else:
                        new_cx = (x1_c + x2_c) / 2.0
                        new_cy = (y1_c + y2_c) / 2.0
                        clipped_line = f"{int(c)} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}"
                        new_lines.append(clipped_line)
                        fixes.append({
                            "image": stem,
                            "line": l_num,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": clipped_line,
                        })
                except ValueError:
                    # Nếu không parse được thì drop_line
                    fixes.append({
                        "image": stem,
                        "line": l_num,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "(đã xoá)",
                    })
                continue

            # Các trường hợp khác nếu có
            new_lines.append(raw_line)

        # Ghi lại nội dung file nhãn
        if new_lines:
            content = "\n".join(new_lines) + "\n"
        else:
            content = ""
        lbl_path.write_text(content, encoding="utf-8")

    return fixes

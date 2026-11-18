# Báo cáo Day 09 — Cao Thị Thúy Hiền, 2A202603193

## 1. Kết luận trước
Pipeline đưa ra kết luận **Hold** (mã thoát 10). Lô dữ liệu đầu vào gồm **224 ảnh** thô; qua cửa nhận dữ liệu loại bỏ 21 ảnh lỗi, còn lại **203 ảnh** được xử lý và xuất ra bộ dữ liệu nháp tại `submission/export/clean_v1/`. Lý do chính: máy đã tự động sửa sạch 100% lỗi cú pháp và hình học; người duyệt mô phỏng đã hoàn thành ngân sách 80 ảnh (gán nhãn toàn bộ 6 ảnh thiếu file nhãn và sửa các lỗi ngữ nghĩa ưu tiên cao); tuy nhiên do hàng đợi cần duyệt có 130 ảnh, vẫn còn **44/203 ảnh (21.67%)** chứa cảnh báo ngữ nghĩa chưa được duyệt, vượt ngưỡng quy định 10% (`warn_ratio_hold`), do đó chỉ được lưu hành dưới dạng bản nháp nội bộ, chưa được phát hành chính thức.

## 2. Lỗi và phân việc
Tổng hợp lỗi từ `02_error_list_v1` (trên tổng số 203 ảnh nhận vào):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (intake/autofix) | File ảnh bị hỏng không thể giải mã (`UnidentifiedImageError`, `OSError`), máy loại bỏ tự động. |
| `BAD_SIZE` | 3 ảnh | Máy (intake/autofix) | Cạnh ngắn < 250px không đạt chuẩn độ phân giải tối thiểu, máy loại bỏ tự động. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (intake/autofix) | Trùng hash MD5 byte-by-byte với ảnh khác trong lô, máy giữ ảnh đầu và xoá ảnh lặp. |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (intake/autofix) | Trùng thị giác gần đúng (pHash Hamming distance ≤ 8), máy phát hiện và loại bỏ. |
| `LEAK_TEST` | 5 ảnh | Máy (intake/autofix) | Trùng lặp với tập test/gold_val, máy loại bỏ để ngăn rò rỉ dữ liệu và metric giả. |
| `BAD_CLASS_NAME` | 2 lỗi (data.yaml) | Máy (autofix) | Tên lớp trong `data.yaml` bị viết hoa ('Person', 'Bus'), máy chuẩn hoá về danh sách chuẩn `cfg['classes']`. |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng thiếu cột toạ độ hoặc chứa giá trị NaN, máy xoá dòng (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp ngoài dải 0..3 (-1, 4, 7, 93), máy xoá dòng (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Chiều rộng hoặc chiều cao box bằng 0, máy xoá dòng (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Mép box tràn ra ngoài toạ độ [0, 1], máy cắt viền về trong ảnh (`clip_box`). |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Hai box cùng lớp trùng nhau với IoU > 0.9, máy xoá box thứ hai (`drop_line`). |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (sau khi máy tạo hàng đợi) | Máy không được tự bịa nhãn; đánh dấu `needs_label` và ưu tiên cao nhất cho người gán. |
| `POSSIBLE_MISSING` | 68 box/ảnh | Người | Model lớn phát hiện vật thể nhưng nhãn thiếu; cần người xác nhận vật có thuộc guideline không. |
| `POSSIBLE_WRONG_CLASS` | 18 box/ảnh | Người | Model và nhãn lệch lớp phân loại (vd: truck vs bus), chỉ con người mới có thẩm quyền phân xử ngữ nghĩa. |
| `POSSIBLE_LOOSE_BOX` | 31 box/ảnh | Người | Box vẽ lỏng hoặc lệch tâm (IoU với model < 0.5), cần người kéo lại box cho khít. |
| `POSSIBLE_FALSE_POS` | 29 dòng | Người | Box nhãn không khớp với bất kỳ dự đoán nào của model lớn, cần người kiểm tra có phải gán nhầm rác/nền. |
| `EMPTY_LABEL` | 12 ảnh | Người | File nhãn rỗng (ảnh nền thực sự hay bị bỏ sót), cần người kiểm tra trực quan. |
| `BOX_TINY` | 6 dòng | Người | Box nhỏ hơn 12px, chuyển người xem xét theo guideline dự án. |
| `BOX_HUGE` | 3 dòng | Người | Box chiếm > 95% diện tích ảnh, chuyển người kiểm tra xem có vẽ nhầm nền không. |
| `CLASS_RARE` | 4 cảnh báo | Máy cảnh báo | Các ID lớp lạ (-1, 4, 7, 93) có ít box, hỗ trợ kiểm tra phân phối bất thường. |

**Giải thích hàng đợi `05_review_queue.csv`:**
- Hàng đợi sắp xếp theo điểm ưu tiên giảm dần (`priority`):
  + Công thức tính điểm dựa trên trọng số nguy cơ: `NEEDS_LABEL` có trọng số cao nhất (10.0), `FIXED_DROP_LINE` (2.0), `POSSIBLE_WRONG_CLASS` (3.0 * conf), `POSSIBLE_MISSING` (2.0 * conf), `POSSIBLE_FALSE_POS` (2.0).
  + Do đó, 6 ảnh chưa có file nhãn (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) và các ảnh có nhiều lỗi kết hợp (như `img_0020` priority 14.528, `img_0185` priority 10.052) được đẩy lên đầu hàng đợi.
- Với ngân sách 80 ảnh:
  + Người duyệt đã giải quyết toàn bộ 6 ảnh thiếu nhãn (tránh bị Rework) và duyệt thêm 74 ảnh có cảnh báo ngữ nghĩa nặng nhất (tập trung vào nhầm lớp và thiếu nhãn có độ tin cậy cao).
  + Tuy nhiên, do tổng số ảnh cần duyệt là 130 ảnh, còn 50 ảnh nằm ngoài ngân sách chưa được xem, trong đó có 44 ảnh mang cảnh báo.

## 3. Calibration (2 ngưỡng)
Bảng kết quả hiệu chỉnh trên tập `data/calib/`:

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 8 | 1.00 / 0.50 → 1.00 / 0.67 (DUP_IMAGE_NEAR) | Ngưỡng 2 quá chặt, chỉ bắt được 3/6 ảnh biến đổi nhẹ (Recall 50%). Tăng lên 8 giúp tăng Recall lên 67% mà vẫn giữ Precision 100%. Không chọn 16 vì trên dữ liệu thật sẽ dễ xoá nhầm ảnh khác. |
| `second_opinion.conf` | 0.25 | 0.50 | 0.50 / 1.00 → 0.57 / 1.00 (POSSIBLE_MISSING) | Ngưỡng 0.25 khiến model cảnh báo nhiều dự đoán nhiễu (FP cao), làm hàng đợi phình to. Tăng lên 0.50 giúp tăng Precision từ 50% lên 57% trong khi vẫn giữ nguyên Recall 100% đối với các lỗi missing cố ý trong calib. |

**Một chỗ calibration có thể đánh lừa bạn:**
Tập `data/calib/` chỉ có 39 ảnh với các lỗi chèn nhân tạo, rõ rệt. Trên sweep calib, `phash_dist = 16` đạt F1 cao nhất (0.91, recall 0.83). Tuy nhiên, nếu áp đặt ngưỡng 16 lên tập raw 224 ảnh thực tế, khoảng cách Hamming 16 là quá lỏng và có nguy cơ xoá nhầm các bức ảnh đường phố có cùng góc chụp cố định nhưng khác thời điểm và khác phương tiện giao thông. Hành vi xoá nhầm ở bước nhận (intake) là mất mát dữ liệu không thể phục hồi, vì vậy ta phải đánh đổi chấp nhận recall thấp hơn trên calib để bảo vệ dữ liệu thật.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Bằng chứng cửa chặn gate hoạt động đúng:**
- Chạy thử nghiệm ngắt ngân sách người duyệt:
  `python -m pipeline.run --work work/work_nb --budget 0 --reports work/rep_nb --export-dir work/exp_nb`
- Kết quả: Khi không có người duyệt, 6 ảnh thiếu nhãn không được xử lý và tồn tại dưới dạng lỗi `MISSING_LABEL_FILE` ở vòng 3. Cửa chặn `gate.py` phát hiện `n_errors = 6`, lập tức trả về kết luận **REWORK**, mã thoát **20**, và hoàn toàn **KHÔNG xuất** dataset ra thư mục `work/exp_nb/clean_v1`. Điều này chứng minh cửa chặn thật sự ngăn chặn việc phát hành dữ liệu lỗi.

**(b) Hai điểm mù pipeline không bắt được:**
1. **Box lỏng nhẹ (IoU nằm trong khoảng [0.5, 0.7]):** Khi người gán nhãn vẽ box hơi rộng hoặc hơi lệch nhưng IoU với dự đoán model ≥ 0.5 (`iou_match`), pipeline coi như hai bên đồng thuận và không gắn cờ cảnh báo `POSSIBLE_LOOSE_BOX` (chỉ cờ khi IoU < 0.5).
2. **Sai sót chung giữa nhãn người và model (Shared Bias):** Với các vật thể mập mờ hoặc bị che khuất một phần (như xe bán tải nhỏ hay xe kéo), nếu cả người gán nhãn lẫn model `yolo26l` đều nhận nhầm thành `car`, pipeline ghi nhận đồng thuận tuyệt đối và hoàn toàn bỏ lọt lỗi phân loại sai này.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy do môi trường cục bộ là máy tính cá nhân không trang bị GPU rời chuyên dụng (NVIDIA CUDA), việc huấn luyện YOLO 20 epoch cho 2 biến thể (raw và clean) qua 2 seed sẽ tiêu tốn nhiều giờ trên CPU. Phần huấn luyện so sánh được thiết kế để chạy độc lập trên Google Colab T4 GPU theo tài liệu hướng dẫn `docs/COLAB.md`.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối và hướng xử lý:**
- Quyết định: **Hold** (Đã xuất bản nháp tại `submission/export/clean_v1/`, chưa được phát hành chính thức).
- Để chuyển thành **Release**: Cần nâng ngân sách duyệt của chuyên viên thẩm định từ 80 ảnh lên ít nhất 120 ảnh (hoặc duyệt vòng 2 cho 50 ảnh còn lại trong hàng đợi) để thẩm định nốt 44 ảnh còn cảnh báo. Khi tỉ lệ ảnh có cảnh báo chưa duyệt hạ xuống dưới 10% (< 20 ảnh / 203 ảnh), pipeline sẽ tự động cấp quyết định Release.

**(b) Ghi chú sử dụng AI:**
- **Prompt chính:** *"Hãy triển khai 4 module (label_format, gate, autofix, second_opinion) theo đúng hợp đồng giao diện, xử lý đầy đủ các ca biên hình học và bắt ngoại lệ theo phương pháp TDD."*
- **Cách kiểm tra code AI:** Chạy toàn bộ 79 bài test trong `tests/` đảm bảo xanh 100%; kiểm tra kỹ file `03_fixes.csv` để đảm bảo máy không sửa đè hoặc xoá nhầm dữ liệu gốc trong `data/raw`; chạy kịch bản thử nghiệm `--budget 0` để kiểm tra độ tin cậy của cửa chặn.
- **1 lần AI viết sai và cách khắc phục:** Khi viết hàm cắt box tràn (`clip_box`) trong `autofix.py`, ban đầu AI không xử lý trường hợp box nằm lệch hẳn ra ngoài ảnh, dẫn đến toạ độ sau khi clip có chiều rộng hoặc chiều cao ≤ 0. Bài test `test_box_fully_outside_is_dropped_not_negative` đã phát hiện lỗi này, sau đó code đã được cập nhật để tự động chuyển sang hành động xoá dòng (`drop_line`) khi diện tích box sau khi cắt ≤ 0.

## 7. Phần làm thêm nhận điểm thưởng (+5 điểm)
**(a) Thưởng +3 điểm: Viết thêm check kiểm tra tỉ lệ khung hình bất thường (Extreme Aspect Ratio):**
- Đã cài đặt module mới `pipeline/checks/aspect_ratio.py` và bộ unit test `tests/test_aspect_ratio.py` (4/4 test passed).
- Quy tắc: Cảnh báo `BOX_ASPECT_RATIO` khi tỉ lệ chiều rộng / chiều cao ($w_{px} / h_{px}$) của box vượt ngưỡng cực đoan:
  + $w_{px} / h_{px} > 12.0$: Box quá dẹt ngang (dễ do người gán vô tình nhấp chuột kéo thành vệt ngang mỏng dính nền đường).
  + $w_{px} / h_{px} < 0.10$: Box quá mảnh dọc (dễ do gán nhầm cột đèn, biển báo hoặc kéo trượt chuột theo chiều dọc).
- Check xử lý an toàn với ngoại lệ cú pháp dòng, tính toán theo pixel thực tế của ảnh và sinh cờ cảnh báo mức `WARN` để đưa vào hàng đợi duyệt.

**(b) Thưởng +2 điểm: Đối chiếu bộ lọc CVAT (docs/CVAT_FILTER.md):**
- Khảo sát bộ lọc `width < 20` trên các ảnh trong lô:
  + Ví dụ ảnh `img_0026`: Có 5 box có `width < 20px` (dòng 1, 2, 3, 4, 6). Trong đó dòng 6 có cạnh ngắn $11.4\text{px} < 12\text{px}$ nên pipeline đã cảnh báo `BOX_TINY` (khớp chính xác giữa pipeline và CVAT).
  + Các dòng 1, 2, 3, 4 có chiều rộng từ $12\text{px}$ đến $19.8\text{px}$: Khớp bộ lọc `width < 20` trên CVAT nhưng không bị pipeline bắt vì pipeline dùng ngưỡng quy tắc dự án `min_box_px = 12px` (ngưỡng 12px chặt chẽ hơn, tránh bắt nhầm các đối tượng người ở xa còn nhận diện được).
- **Ý nghĩa thuộc tính `can_review`:** Trong CVAT, người gán nhãn đánh dấu `attr["can_review"] == true` khi gặp các ca khó, vật thể mờ ảo hoặc bị che khuất để báo hiệu cho Reviewer cấp cao vào kiểm tra lại. Trong pipeline tự động, cơ chế tương đương chính là **Hàng đợi ưu tiên `05_review_queue.csv`** kết hợp với **`second_opinion`**, tự động chấm điểm trọng số nguy cơ (`NEEDS_LABEL` = 10, `WRONG_CLASS` = 3 * conf, `MISSING` = 2 * conf) để đẩy các ca nghi ngờ nhất lên đầu cho người duyệt mà không cần người gán nhãn phải nhớ tích chọn thủ công.


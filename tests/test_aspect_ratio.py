from pipeline.checks import aspect_ratio


def test_clean_aspect_ratio(make_ds, cfg):
    # Box thông thường: car tỉ lệ 2:1, person tỉ lệ 1:3 -> hoàn toàn hợp lệ
    ds = make_ds(images={"a": 1}, labels={"a": ["0 0.5 0.5 0.2 0.1", "1 0.5 0.5 0.1 0.3"]}, size=(640, 480))
    assert aspect_ratio.run(ds, cfg) == []


def test_extremely_flat_box_detected(make_ds, cfg):
    # Box quá dẹt ngang: w=0.5 (320px), h=0.01 (4.8px) -> w/h = 66.67 > 12.0
    ds = make_ds(images={"a": 1}, labels={"a": ["0 0.5 0.5 0.5 0.01"]}, size=(640, 480))
    iss = aspect_ratio.run(ds, cfg)
    assert len(iss) == 1
    assert iss[0].code == "BOX_ASPECT_RATIO"
    assert iss[0].severity == "warn"
    assert iss[0].line == 1
    assert iss[0].extra["direction"] == "horizontal_flat"


def test_extremely_thin_vertical_box_detected(make_ds, cfg):
    # Box quá mảnh dọc: w=0.005 (3.2px), h=0.5 (240px) -> w/h = 0.013 < 0.10
    ds = make_ds(images={"a": 1}, labels={"a": ["1 0.5 0.5 0.005 0.5"]}, size=(640, 480))
    iss = aspect_ratio.run(ds, cfg)
    assert len(iss) == 1
    assert iss[0].code == "BOX_ASPECT_RATIO"
    assert iss[0].severity == "warn"
    assert iss[0].line == 1
    assert iss[0].extra["direction"] == "vertical_thin"


def test_bad_lines_do_not_crash(make_ds, cfg):
    # Bắt lỗi cú pháp không được làm chết check
    ds = make_ds(images={"a": 1}, labels={"a": ["garbage", "0 0.5 0.5 0 0.1", "0 0.5 0.5 0.2 0.1"]})
    assert aspect_ratio.run(ds, cfg) == []

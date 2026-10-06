# 3. Kiểm thử giao diện (CLI) & hộp đen

- **File test:** `tests/test_blackbox_cli.py` (TC-01 … TC-08 đạt; TC-09 xfail)
- **Actor chính:** A1 QA Engineer (TC-01 … TC-07), A2 CI/CD Pipeline (TC-08), A3 RAG Developer (TC-09)

## 3.1 Cách tiếp cận hộp đen

CLI được chạy trong **tiến trình con**, đúng như người dùng gõ lệnh. Test **không import hay mock** bất kỳ phần nào bên trong ContextCheck; chỉ quan sát những gì người dùng thấy được:

- **exit code**: 0 là thành công, 1 là có test trượt (`--exit-on-failure`), 2 là sai tham số;
- **stdout / stderr**;
- **file đầu ra** (báo cáo JSON).

```python
def ccheck(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "contextcheck.run_tests", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )
```

`python -m contextcheck.run_tests` gọi đúng hàm `main()` mà lệnh `ccheck` trỏ tới (`[tool.poetry.scripts]`). Cách này không phụ thuộc `PATH` và luôn dùng đúng virtualenv đang chạy test.

Mỗi test có một thư mục làm việc riêng chứa hai kịch bản mẫu (fixture `workdir`):

```python
PASSING_SCENARIO = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: echo works
    request: hello
    asserts:
      - kind: equals
        assertion: hello
"""
FAILING_SCENARIO = PASSING_SCENARIO.replace("assertion: hello", "assertion: something else")

@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    (tmp_path / "pass.yaml").write_text(PASSING_SCENARIO)
    (tmp_path / "fail.yaml").write_text(FAILING_SCENARIO)
    return tmp_path
```

## 3.2 Thiết kế test case

Các case được chọn theo **phân vùng tương đương** của tham số CLI:

| Vùng | Case |
|---|---|
| Lệnh trợ giúp | TC-01 |
| Thiếu tham số bắt buộc | TC-02 |
| Giá trị ngoài miền cho phép | TC-03 |
| Tổ hợp tham số không hợp lệ (ràng buộc chéo trong `validate_args`) | TC-04, TC-05 |
| Đầu vào không tồn tại | TC-06 |
| Luồng thành công: console | TC-07 |
| Luồng đầy đủ cho CI: ghi file, tổng hợp kết quả, exit code khi trượt | TC-08 |

## 3.3 Chi tiết 08 test case

| ID | Actor | Mục tiêu | Lệnh | Kết quả mong đợi | Kết quả thực tế | TT |
|---|---|---|---|---|---|---|
| TC-01 | A1 | Xem hướng dẫn | `ccheck --help` | exit 0; stdout có `--output-type` | Đúng | ✅ |
| TC-02 | A1 | Thiếu tham số bắt buộc | `ccheck --filename pass.yaml` | exit 2; stderr: `the following arguments are required: --output-type` | Đúng | ✅ |
| TC-03 | A1 | Giá trị không hợp lệ | `ccheck --output-type xml --filename pass.yaml` | exit 2; stderr: `invalid choice: 'xml'` | Đúng | ✅ |
| TC-04 | A1 | Ghi file mà không có nguồn | `ccheck --output-type file` | exit 2; stderr: `--filename or --folder is required` | Đúng | ✅ |
| TC-05 | A1 | Ghi file mà thiếu thư mục đích | `ccheck --output-type file --filename pass.yaml` | exit 2; stderr: `--output-folder is required` | Đúng | ✅ |
| TC-06 | A1 | File kịch bản không tồn tại | `ccheck --output-type console --filename missing.yaml` | exit ≠ 0; stderr: `missing.yaml do not exist` | Đúng (thông báo nằm trong traceback Pydantic, chưa gọn) | ✅ |
| TC-07 | A1 | Chạy kịch bản đạt, xuất console | `ccheck --output-type console --filename pass.yaml` | exit 0; stdout có tên step `echo works` | Đúng | ✅ |
| TC-08 | A2 | Luồng CI: 2 kịch bản (1 đạt, 1 trượt), ghi file, tổng hợp | `ccheck --output-type file --filename pass.yaml fail.yaml --output-folder out --exit-on-failure --aggregate-results` | exit 1; có `pass_*.json` (`result: true`) và `fail_*.json` (`result: false`, có khóa `report`) | Đúng | ✅ |

**Kết quả: 8/8 đạt.**

Ví dụ code của một case kiểm tra lỗi (TC-04) và của case CI (TC-08):

```python
def test_tc04_file_output_without_input(workdir):
    result = ccheck("--output-type", "file", cwd=workdir)

    assert result.returncode == 2
    assert "--filename or --folder is required" in result.stderr


def test_tc08_file_output_and_exit_on_failure(workdir):
    result = ccheck(
        "--output-type", "file",
        "--filename", "pass.yaml", "fail.yaml",
        "--output-folder", "out",
        "--exit-on-failure", "--aggregate-results",
        cwd=workdir,
    )

    assert result.returncode == 1
    reports = {p.name.split("_")[0]: json.loads(p.read_text())
               for p in (workdir / "out").iterdir()}
    assert reports["pass"]["result"] is True
    assert reports["fail"]["result"] is False
    assert "report" in reports["fail"]
```

## 3.4 TC-09: CLI `question_answering` (actor A3, ngoài 08 case trên)

| ID | Lệnh | Mong đợi | Thực tế | TT |
|---|---|---|---|---|
| TC-09 | `python -m contextcheck.question_answering --help` | exit 0 | `TypeError: _StoreTrueAction.__init__() got an unexpected keyword argument 'type'` | ❌ C1 |

Nguyên nhân nằm ở `contextcheck/question_answering.py:90`: `--debug` khai báo đồng thời `type=bool` và `action="store_true"`. Ngoài ra `--use-ranker` dùng `type=bool`, nên `--use-ranker False` vẫn ra `True`.

```python
@pytest.mark.xfail(strict=True, reason="`--debug` combines type=bool with action='store_true'")
def test_question_answering_cli_starts(workdir):
    result = subprocess.run(
        [sys.executable, "-m", "contextcheck.question_answering", "--help"],
        capture_output=True, text=True, cwd=workdir, timeout=120,
    )
    assert result.returncode == 0
```

## 3.5 Kết luận

- CLI `ccheck` **bắt lệnh chuẩn**: 08/08 test case đạt. Exit code đúng quy ước (0, 1, 2), nên dùng được trong pipeline CI (actor A2).
- Điểm cần cải thiện về trải nghiệm (A1): lỗi "file không tồn tại" (TC-06) hiện dưới dạng traceback thay vì một dòng thông báo ngắn.
- CLI phụ `question_answering` **không khởi động được** (C1), ảnh hưởng trực tiếp tới actor A3.

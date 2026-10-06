# 6. Danh sách lỗi đã xác nhận

Mỗi lỗi đều có **một test tự động** viết theo hành vi đúng mong muốn và đánh dấu `@pytest.mark.xfail(strict=True)`. Xem toàn bộ bằng lệnh:

```sh
poetry run pytest tests -rx
```

Khi một lỗi được sửa, test tương ứng chuyển thành **XPASS** và làm suite đỏ. Lúc đó người sửa chỉ cần gỡ marker `xfail` là test trở thành test hồi quy bình thường.

## 6.1 Tổng hợp

| ID | Mức độ | Actor bị ảnh hưởng | Mô tả | Test |
|---|---|---|---|---|
| R1 | **Cao** | A2 CI/CD | Lỗi kết nối endpoint làm dừng cả lượt chạy, không có báo cáo nào | RV-12 |
| C1 | **Cao** | A3 RAG Dev | CLI `question_answering` crash ngay khi khởi động | TC-09 |
| E1 | Trung bình | A3 RAG Dev | Tài liệu không có chunk thì crash LDA | E2E-05 |
| R2 | Trung bình | A2 CI/CD | `--exit-on-failure` kèm `--show-time-statistics` thì crash | RV-13 |
| T1 | Trung bình | A4 Integrator | `conn_duration` sai khi nhiều luồng dùng chung endpoint | CC-03 |
| E2 | Thấp | A3 RAG Dev | `cc_api_wrapper` đọc biến môi trường ngay lúc import | E2E-06 |
| R3 | Thấp | A1 QA | File YAML rỗng báo `AttributeError` khó hiểu | RV-06 |
| R4 | Thấp | A1 QA | Biến Jinja sai tên bị render thành chuỗi rỗng mà không báo gì | RV-07 |

**Mức độ:**
- **Cao**: chặn hẳn một luồng sử dụng chính.
- **Trung bình**: crash hoặc sai số liệu trong một tình huống cụ thể.
- **Thấp**: trải nghiệm kém, hoặc có cách tránh dễ dàng.

## 6.2 Chi tiết

### R1: Lỗi endpoint làm dừng cả lượt chạy

- **Vị trí:** `contextcheck/executors/executor.py:67`. `send_request` không nằm trong `try/except`.
- **Tái hiện:** chạy thư mục gồm `a_down.yaml` (endpoint `http://127.0.0.1:9/`) và `b_ok.yaml`.
- **Thực tế:** `requests.ConnectionError` lan ra ngoài, `b_ok.yaml` không được chạy, không file JSON nào được ghi.
- **Mong đợi:** step của `a_down` bị đánh fail kèm thông tin lỗi, `b_ok` vẫn chạy, có đủ 2 báo cáo.
- **Đề xuất:** bắt exception quanh `send_request` trong `Executor._run_step`, đặt `test_step.result = False`, ghi lỗi vào response, rồi tiếp tục.

### C1: CLI `question_answering` không khởi động được

- **Vị trí:** `contextcheck/question_answering.py:90`.
- **Tái hiện:** `python -m contextcheck.question_answering --help`.
- **Thực tế:** `TypeError: _StoreTrueAction.__init__() got an unexpected keyword argument 'type'`.
- **Đề xuất:** bỏ `type=bool` ở `--debug`. Đổi `--use-ranker` sang `action=argparse.BooleanOptionalAction`, vì `type=bool` biến chuỗi `"False"` thành `True`.

### E1: Tài liệu không có chunk làm crash LDA

- **Vị trí:** `contextcheck/generators/generate_questions.py`, `get_topic_lists_from_chunks`.
- **Tái hiện:** `get_document_chunks` trả `[]`.
- **Thực tế:** `ValueError: cannot compute LDA over an empty collection (no terms)`. Mọi tài liệu khác cũng không được xử lý.
- **Đề xuất:** trong `generate()`, bỏ qua (và log) tài liệu không có chunk hoặc không còn từ nào sau khi tiền xử lý.

### R2: Thống kê thời gian sau khi dừng sớm

- **Vị trí:** `contextcheck/interfaces/interface.py:88`.
- **Tái hiện:** `ccheck --output-type console --filename s.yaml --exit-on-failure --show-time-statistics`, trong đó step đầu trượt.
- **Thực tế:** `AttributeError: 'NoneType' object has no attribute 'stats'`.
- **Đề xuất:** chỉ tính thống kê cho step có `step.response is not None`.

### T1: `conn_duration` sai khi dùng chung endpoint giữa các luồng

- **Vị trí:** `contextcheck/connectors/connector.py` (`__enter__`/`__exit__`) và `contextcheck/endpoints/endpoint.py` (`send_request`).
- **Tái hiện:** 50 luồng cùng gọi `send_request` trên một endpoint.
- **Thực tế:** 26–32/50 response có `conn_duration` lệch hơn 20% so với thời gian thật.
- **Đề xuất:** đo thời gian bằng biến cục bộ trong `send_request`, hoặc để `__enter__` trả về một object thống kê mới cho mỗi lần gọi.

### E2: `cc_api_wrapper` đọc biến môi trường lúc import

- **Vị trí:** `contextcheck/generators/cc_api_wrapper.py`: `endpoint_base_url: str = os.environ["ENDPOINT_BASE_URL"]`.
- **Thực tế:** chỉ cần `import` là đã `KeyError` nếu thiếu biến, kể cả khi truyền giá trị trực tiếp vào constructor.
- **Đề xuất:** `Field(default_factory=lambda: os.environ["ENDPOINT_BASE_URL"])`.

### R3: File YAML rỗng

- **Vị trí:** `contextcheck/loaders/yaml.py:26`.
- **Thực tế:** `AttributeError: 'NoneType' object has no attribute 'get'`.
- **Đề xuất:** nếu `yaml.safe_load` trả `None` thì báo `ValueError(f"Scenario file '{file_path}' is empty.")`.

### R4: Biến Jinja không tồn tại bị bỏ qua

- **Vị trí:** `contextcheck/loaders/yaml.py:35`, `Template(yaml_content)`.
- **Thực tế:** `{{ typo_var }}` render thành `''`, nên request rỗng vẫn được gửi đi mà không có cảnh báo nào.
- **Đề xuất:** `jinja2.Template(yaml_content, undefined=jinja2.StrictUndefined)`.

## 6.3 Quan sát khác (không tính là lỗi)

| Quan sát | Ghi chú |
|---|---|
| `--folder` chỉ lấy `*.yaml`, bỏ qua `*.yml` mà không cảnh báo | Ghi lại trong RV-09 |
| YAML `ParserError` không được bọc thành thông báo thân thiện như `ScannerError` | Lỗi gốc của PyYAML vẫn có số dòng |
| TC-06: "file không tồn tại" hiện dưới dạng traceback Pydantic | Nên in một dòng ngắn rồi exit 2 |
| Assertion dạng chuỗi và trường `eval` chạy bằng `eval()` của Python | **Chỉ chạy kịch bản từ nguồn tin cậy** |
| `pyproject.toml` khai báo `python = "^3.11"` nhưng lockfile không cài được trên 3.13 | Cần cập nhật lockfile hoặc giới hạn `<3.13` |
| Repo không có CI (`.github/workflows`) | Nên thêm workflow chạy `pytest` |

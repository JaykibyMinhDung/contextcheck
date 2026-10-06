# Báo cáo review code & kiểm thử ContextCheck

> Bản tóm tắt. Bộ tài liệu chi tiết (actor, cách viết từng test case, danh sách lỗi) xem tại [README.md](README.md).

- **Phiên bản kiểm thử:** `ccheck` 0.1.4 (commit `04aab4f`)
- **Môi trường:** Linux, Python 3.11, cài bằng `poetry install`
- **Lệnh chạy lại toàn bộ:** `poetry run pytest tests`
- **Kết quả tổng:** 47 passed, 3 skipped (cần OpenAI/Ollama thật), 8 xfailed (lỗi đã xác nhận)

Các test mới nằm trong 4 file sau, kèm mock server `tests/mock_rag_server.py`:

| File | Nội dung | Kết quả |
|---|---|---|
| `tests/test_review_yaml_router.py` | Đọc YAML, Test Router, cơ chế fallback | 9 passed, 4 xfailed |
| `tests/test_blackbox_cli.py` | 08 test case hộp đen cho CLI `ccheck` (TC-01 đến TC-08) | 8 passed, 1 xfailed |
| `tests/test_e2e_qa_flow.py` | Luồng Q&A toàn trình, trường hợp Retriever trả danh sách rỗng | 4 passed, 2 xfailed |
| `tests/test_concurrency.py` | Chạy đồng thời 50 request | 2 passed, 1 xfailed |

Test đánh dấu `xfail(strict=True)` mô tả **hành vi đúng mong muốn** cho một lỗi đã tìm thấy. Khi lỗi được sửa, test đó chuyển thành XPASS và làm suite đỏ, nhắc người sửa bỏ marker đi.

---

## 1. Review code & tài liệu: đọc kịch bản YAML và Test Router

### Luồng xử lý

1. `run_tests.main()` đọc tham số CLI (argparse) và kiểm tra các tổ hợp bắt buộc trong `validate_args`.
2. `TestsRouter` (Pydantic) chuẩn hóa đường dẫn, kiểm tra file và thư mục có tồn tại không, tự tạo `--output-folder`, rồi gom kịch bản từ `--filename` và `--folder` (chỉ lấy `*.yaml`).
3. Với mỗi file, `load_yaml_file` đọc YAML, lấy khối `variables`, render bằng Jinja2 rồi parse lại.
4. `TestScenario.model_validate` gộp `default_request` vào từng step và dựng assertion qua factory.
5. `Executor` chạy tuần tự các step. Router chỉ in tóm tắt sau khi **tất cả** kịch bản đã chạy xong.

### Fallback hoạt động đúng (có test chứng minh)

- **Assertion lỗi được cô lập.** Một assertion ném exception (sai tên biến, biểu thức không trả về bool) sẽ được log lại, step bị đánh fail, còn các assertion khác vẫn chạy (`test_failing_assertion_is_isolated_and_remaining_assertions_run`).
- **Regex viết trong nháy kép** cho ra thông báo lỗi dễ hiểu, kèm hướng dẫn sửa.
- **`kind` endpoint sai** hoặc **thiếu khối `config`** bị chặn ngay lúc nạp file bằng `ValidationError`, trước khi gửi bất kỳ request nào.
- **Tham số CLI sai** hoặc **file kịch bản không tồn tại** bị bắt trước khi chạy (TC-02 đến TC-06).
- **Thư mục không có kịch bản nào:** chỉ in cảnh báo rồi thoát, không crash.

### Chỗ thiếu fallback (lỗi đã xác nhận)

| # | Lỗi | Vị trí | Test |
|---|---|---|---|
| R1 | Endpoint không kết nối được thì `ConnectionError` làm **dừng toàn bộ lượt chạy**, các kịch bản phía sau không được chạy và không có báo cáo nào được ghi | `executors/executor.py:67` | `test_unreachable_endpoint_fails_step_and_run_continues` |
| R2 | Dùng `--exit-on-failure` kèm `--show-time-statistics` thì crash `AttributeError`, vì các step bị bỏ qua không có `response` | `interfaces/interface.py:88` | `test_time_statistics_after_early_stop` |
| R3 | File YAML rỗng ném `AttributeError: 'NoneType' object has no attribute 'get'` thay vì một thông báo rõ ràng | `loaders/yaml.py:26` | `test_empty_yaml_file_gives_clear_error` |
| R4 | Biến Jinja gõ sai tên bị render thành chuỗi rỗng **mà không báo gì**, nên request rỗng vẫn được gửi đi | `loaders/yaml.py:35` | `test_undefined_jinja_variable_is_reported` |

Một số ghi chú khác:

- Trong YAML chỉ `ScannerError` được bọc lại thành thông báo thân thiện. `ParserError` (ví dụ thiếu dấu `]`) vẫn hiện lỗi gốc của PyYAML, tuy lỗi gốc đó vẫn có số dòng.
- `--folder` bỏ qua file `.yml` mà không cảnh báo.
- Assertion dạng chuỗi và trường `eval` trong request được chạy bằng `eval()` của Python, nên **chỉ được chạy kịch bản từ nguồn tin cậy**.

**Kết luận mục 1:** logic đọc YAML và định tuyến rõ ràng, chạy đúng. Fallback cho **assertion** và cho **tham số hoặc cấu hình sai** được xây dựng hợp lý. Ngược lại, lỗi ở **tầng endpoint (mạng)** chưa có fallback (R1), và có thêm 3 lỗi nhỏ (R2 đến R4).

---

## 2. Kiểm thử giao diện (CLI) & hộp đen

### 08 test case CLI `ccheck`

CLI được chạy trong subprocess đúng như người dùng gõ lệnh; test chỉ kiểm tra exit code, nội dung stdout/stderr và file đầu ra.

| TC | Kịch bản | Kết quả mong đợi | Kết quả |
|---|---|---|---|
| TC-01 | `--help` | exit 0, hiện hướng dẫn | ✅ Đạt |
| TC-02 | Thiếu `--output-type` | exit 2, báo thiếu tham số | ✅ Đạt |
| TC-03 | `--output-type xml` | exit 2, `invalid choice` | ✅ Đạt |
| TC-04 | `--output-type file`, không có `--filename` hay `--folder` | exit 2, báo thiếu nguồn | ✅ Đạt |
| TC-05 | `--output-type file --filename ...`, không có `--output-folder` | exit 2, báo thiếu thư mục ra | ✅ Đạt |
| TC-06 | `--filename missing.yaml` | exit ≠ 0, báo file không tồn tại | ✅ Đạt (thông báo nằm trong traceback Pydantic, chưa gọn) |
| TC-07 | Chạy kịch bản đạt, xuất ra console | exit 0, có bảng kết quả | ✅ Đạt |
| TC-08 | Hai kịch bản (một đạt, một trượt), `--output-type file --exit-on-failure --aggregate-results` | exit 1, ghi 2 file JSON có `result` và `report` đúng | ✅ Đạt |

**Kết quả: 8/8 đạt. CLI `ccheck` bắt lệnh đúng chuẩn.**

Ngoài 8 case trên còn phát hiện lỗi **C1**: CLI `question_answering` **crash ngay khi khởi động**, vì `--debug` khai báo đồng thời `type=bool` và `action="store_true"` (`question_answering.py:90`). Thêm nữa, `--use-ranker type=bool` khiến giá trị `False` truyền vào vẫn thành `True`.

### Luồng Q&A toàn trình (End-to-End)

Luồng được chạy trên một RAG API giả lập (`tests/mock_rag_server.py`, HTTP thật, có endpoint documents, semantic search và QA). Chỉ LLM viết câu hỏi được thay bằng stub.

1. `QuestionsGenerator` gọi `ContextClueApiWrapper` để lấy tài liệu và chunk, chạy LDA, rồi sinh câu hỏi và ghi ra `questions.yaml`.
2. `AnswerGenerator` gọi `/qa/ask` cho từng câu hỏi và nhận câu trả lời kèm tài liệu nguồn (`debug=True`).
3. Từ cặp hỏi–đáp, test dựng một kịch bản regression YAML (endpoint `cc_prompt_llm`).
4. Chạy CLI `ccheck --output-type file` trên kịch bản đó.

Kết quả: **đạt**. Exit 0, báo cáo JSON có `result: true`, số step bằng số câu hỏi (`test_e2e_qa_flow`). Vì CLI `question_answering` đang hỏng (C1), bước 2 phải gọi trực tiếp `AnswerGenerator`.

### Retriever trả về danh sách rỗng

| Tình huống | Kết quả |
|---|---|
| Semantic search trả `[]` lúc sinh câu hỏi | ✅ Không crash; LLM vẫn được gọi (không có ngữ cảnh) |
| `/qa/ask` trả `collection_retriever_entries: []` lúc sinh câu trả lời (`debug=True`) | ✅ Không crash; `chunks_and_documents == []` |
| Chạy kịch bản regression khi retriever rỗng (RAG trả "I don't know.") | ✅ Không crash; được ghi nhận là **assertion trượt** (`result: false`), exit 0 |
| Tài liệu **không có chunk nào** (`get_document_chunks` trả `[]`) | ❌ **Crash** `ValueError: cannot compute LDA over an empty collection` (lỗi E1) |

Lỗi liên quan **E2**: chỉ cần import `contextcheck.generators.cc_api_wrapper` là đã đọc `os.environ[...]`, nên thiếu biến môi trường thì `KeyError` xảy ra ngay lúc import.

**Kết luận mục 2:** CLI `ccheck` đạt 08/08 test case. Luồng Q&A toàn trình chạy thông. Khi **retriever trả danh sách rỗng**, luồng không crash ở cả ba bước. Riêng trường hợp tài liệu không có chunk vẫn crash (E1).

---

## 3. Mở rộng: kiểm thử đa luồng (Concurrency Safety)

Bản thân ContextCheck **chạy tuần tự** (xem TODO trong `TestsRouter.run_tests`), nên test đo hành vi khi framework bị gọi từ nhiều luồng cùng lúc. Thiết lập: 50 luồng, gửi tới mock server đa luồng, mỗi request có độ trễ ngẫu nhiên 50–200 ms. Một request được coi là deadlock nếu không xong trong 30 giây.

| Kịch bản | Kết quả (3 lần đo) |
|---|---|
| 50 kịch bản chạy đồng thời, mỗi luồng một `Executor` riêng | ✅ 50/50 đạt, không deadlock, 0,34–0,40 s (chạy tuần tự sẽ mất khoảng 6 s), 33–44 request được xử lý song song cùng lúc |
| 50 request đồng thời dùng **chung một endpoint** | ✅ 50/50 nhận đúng response của chính mình (không lẫn), không deadlock, khoảng 0,28 s |
| Thống kê thời gian `conn_duration` khi dùng chung endpoint | ❌ 26–32/50 response ghi **sai** thời gian (lỗi T1) |

Nguyên nhân lỗi **T1**: `ConnectorBase.stats` là trạng thái dùng chung, có thể bị thay đổi. Mỗi luồng ghi đè `conn_start_time` của luồng khác trong `__enter__`, nên `conn_duration` bị sai, kéo theo cả `--show-time-statistics` sai. Bản thân dữ liệu kiểm thử (request/response, kết quả assertion) **không** bị ảnh hưởng.

**Kết luận mục 3:** chạy đồng thời 50 request **không xuất hiện deadlock**, không lẫn dữ liệu request/response, và tài nguyên (kết nối, luồng) được giải phóng hết sau khi chạy. Tuy vậy, framework **không thread-safe ở phần thống kê thời gian** khi nhiều luồng dùng chung một endpoint (T1). Khuyến nghị: mỗi luồng tạo endpoint hoặc `Executor` riêng.

---

## 4. Tổng hợp lỗi

| ID | Mức độ | Mô tả | Đề xuất sửa |
|---|---|---|---|
| R1 | Cao | Lỗi kết nối endpoint làm dừng cả lượt chạy | Bắt exception trong `Executor._run_step`, đánh step là fail rồi chạy tiếp |
| C1 | Cao | CLI `question_answering` crash khi khởi động | Bỏ `type=bool` ở `--debug`, đổi `--use-ranker` sang `BooleanOptionalAction` |
| E1 | Trung bình | Tài liệu không có chunk thì crash LDA | Bỏ qua tài liệu rỗng trong `QuestionsGenerator.generate` |
| R2 | Trung bình | `--exit-on-failure` kèm `--show-time-statistics` thì crash | Chỉ tính thống kê cho các step có `response` |
| T1 | Trung bình | `conn_duration` sai khi nhiều luồng dùng chung endpoint | Đo thời gian bằng biến cục bộ trong `send_request`, không lưu trên connector |
| E2 | Thấp | `cc_api_wrapper` đọc biến môi trường ngay lúc import | Dùng `Field(default_factory=lambda: os.environ[...])` |
| R3 | Thấp | File YAML rỗng báo `AttributeError` | Kiểm tra `None` và báo lỗi rõ ràng |
| R4 | Thấp | Biến Jinja sai tên không được báo | Dùng `jinja2.StrictUndefined` |

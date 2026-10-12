# 7. Hướng dẫn chạy dự án và kiểm thử thủ công

Tài liệu này hướng dẫn **cài và chạy ContextCheck trên máy cá nhân (Windows, PowerShell)**, chạy bộ test tự động, rồi **tự kiểm thử thủ công từng test case**: gõ lệnh, quan sát, đối chiếu với kết quả mong đợi.

Công cụ dùng cho kiểm thử thủ công nằm trong `examples/manual_testing/`:

| Thành phần | Dùng để |
|---|---|
| `mock_server.py` | Giả lập RAG/chatbot API tại `http://127.0.0.1:8765`: trả lời bình thường, chậm (timeout), HTTP 500/429, sai kiểu dữ liệu, retriever rỗng |
| `scenarios/s01 … s21` | Kịch bản YAML mẫu cho từng test case (dòng đầu mỗi file ghi rõ mục đích) |
| `folder_demo/` | 2 kịch bản để chạy theo `--folder` (và tái hiện lỗi trùng tên báo cáo) |
| `scripts/*.py` | Script cho các test case không làm được qua CLI (payload OpenAI, SSTI, tiền xử lý tiếng Việt, 50 request đồng thời) |

> Mọi lệnh và "kết quả đã ghi nhận" trong tài liệu này đều đã được chạy thật, trong môi trường cài bằng `pip` với Python 3.11 trên Linux. Các bước dành riêng cho Windows (TC-42, TC-43) **chưa được chạy trên máy Windows thật**; đó là phần nhóm cần tự xác nhận.

---

## 7.1 Cài đặt (làm một lần)

**Cần có:**
- **Python 3.11** (tải từ python.org, khi cài nhớ tích *Add python.exe to PATH*).
- **Git**.
- Không cần Poetry.
- Không nên dùng Python 3.13: lockfile của dự án không cài được trên phiên bản này.

```powershell
git clone https://github.com/JaykibyMinhDung/contextcheck.git
cd contextcheck
git checkout claude/bold-fermat-5swa7s       # nhánh có bộ test và tài liệu này

py -3.11 -m venv .venv
.venv\Scripts\activate                       # đầu dòng lệnh hiện (.venv)
python -m pip install --upgrade pip
pip install -e . pytest pytest-dotenv lorem
pip install flake8 nbformat nbclient ipykernel   # tùy chọn: cần cho TC-46 và TC-50

$env:PYTHONUTF8 = "1"                        # BẮT BUỘC trên Windows, xem giải thích bên dưới
ccheck --help                                # thấy hướng dẫn sử dụng là cài thành công
```

**Vì sao phải đặt `PYTHONUTF8=1`?** Trên Windows, Python mặc định dùng bảng mã cp1252 (hoặc cp1258 với Windows tiếng Việt). Bảng mã này gây ra 2 lỗi của ContextCheck:
- **Không ghi được emoji:** giao diện console in emoji 🎈💬🧐, nên khi output được chuyển hướng ra file hoặc pipe thì crash `UnicodeEncodeError` (lỗi D-14).
- **Không đọc được tiếng Việt:** file YAML được đọc mà không chỉ định encoding (`contextcheck/loaders/yaml.py:12`), nên kịch bản có chữ **"Đ"** sẽ crash `UnicodeDecodeError`.

`PYTHONUTF8=1` buộc Python dùng UTF-8 và tránh được cả hai lỗi. Lệnh `$env:...` chỉ có hiệu lực trong cửa sổ hiện tại. Muốn đặt vĩnh viễn: `[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")`, rồi mở lại PowerShell.

**Mỗi lần mở cửa sổ PowerShell mới**, cần chạy lại 2 lệnh: `.venv\Scripts\activate` và `$env:PYTHONUTF8 = "1"`.

**Linux / macOS:**

```sh
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e . pytest pytest-dotenv lorem
ccheck --help
```

Đường dẫn dùng `/` thay cho `\`; không cần `PYTHONUTF8`.

---

## 7.2 Chạy dự án lần đầu

Đặt biến cho gọn: `$M = "examples\manual_testing"`.

**Chạy một kịch bản, xuất kết quả ra console:**
```powershell
ccheck --output-type console --filename $M\scenarios\s01_pass.yaml
echo $LASTEXITCODE          # 0 = mọi test đạt
```
Kết quả: in ra request, response, từng assertion, rồi bảng tổng kết có cột **Valid = OK**.

**Xuất kết quả ra file JSON** (cách dùng trong CI):
```powershell
ccheck --output-type file --filename $M\scenarios\s01_pass.yaml --output-folder results --aggregate-results --show-time-statistics
dir results                 # s01_pass_<ngày-giờ>.json
```
Mở file JSON để xem các khóa `steps`, `result`, `report` (điểm trung bình theo metric) và `time_statistics`.

**Chạy thử với OpenAI thật (tùy chọn, tốn phí):**
```powershell
$env:OPENAI_API_KEY = "sk-..."
ccheck --output-type console --filename tests\scenario_openai.yaml
```

---

## 7.3 Chạy bộ test tự động

```powershell
python -m pytest tests                       # toàn bộ (~1 phút)
python -m pytest tests -rx                   # kèm lý do của từng XFAIL (lỗi đã xác nhận)
python -m pytest tests\test_blackbox_cli.py -v   # từng file, liệt kê từng test
python -m pytest tests -k tc34 -s            # một test cụ thể, hiện cả output in ra
```

| Môi trường | Kết quả mong đợi |
|---|---|
| Chỉ cài các gói bắt buộc | `131 passed, 5 skipped, 30 xfailed` |
| Có cài thêm `flake8 nbformat nbclient ipykernel` | `132 passed, 3 skipped, 31 xfailed` |

Cách đọc kết quả:
- **passed**: đạt.
- **xfailed**: lỗi đã xác nhận, đã có trong danh sách lỗi; đây là kết quả bình thường.
- **skipped**: test cần OpenAI/Ollama hoặc gói tùy chọn nên được bỏ qua.
- **FAILED** hoặc **XPASS**: có thay đổi so với lúc ghi báo cáo, cần xem lại.

Trên Windows, số liệu có thể lệch 1–2 test: test TC-43 cần tạo được thư mục chỉ đọc, và nếu không tạo được thì sẽ tự bỏ qua.

---

## 7.4 Kiểm thử thủ công: chuẩn bị

Mở **2 cửa sổ PowerShell**. Trong cả hai cửa sổ: `cd contextcheck`, `.venv\Scripts\activate`, `$env:PYTHONUTF8 = "1"`, `$M = "examples\manual_testing"`.

- **Cửa sổ A: chạy mock server, để nguyên trong suốt quá trình test**
  ```powershell
  python $M\mock_server.py
  ```
  Mở trình duyệt vào http://127.0.0.1:8765/health, thấy `{"status": "ok", ...}` là server đã chạy. Mỗi request gửi tới sẽ hiện một dòng log trong cửa sổ này, nhờ đó đếm được số lần gửi (ví dụ để biết có retry hay không).
- **Cửa sổ B: gõ các lệnh `ccheck` ở các mục bên dưới.**

**Ghi kết quả:** với mỗi test case, ghi lại *mã TC – ngày – người test – kết quả thực tế – Đạt/Không đạt*, kèm ảnh chụp màn hình. Cột "Đã ghi nhận" trong các bảng dưới là kết quả lúc viết tài liệu, dùng để đối chiếu.

---

## 7.5 Phần Đoàn Minh Dũng: YAML, Test Router, CLI, E2E, đa luồng

Mã test case giống tài liệu [02](02_REVIEW_YAML_TEST_ROUTER.md), [03](03_KIEM_THU_CLI_HOP_DEN.md), [04](04_KIEM_THU_E2E_QA.md), [05](05_KIEM_THU_DA_LUONG.md). Riêng các case CLI ghi là `CLI-xx` để khỏi nhầm với TC-xx của Vũ Văn Toàn.

### CLI `ccheck`

| ID | Lệnh | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| CLI-01 | `ccheck --help` | Hiện hướng dẫn, exit 0 | ✅ Đạt |
| CLI-02 | `ccheck --filename $M\scenarios\s01_pass.yaml` | `the following arguments are required: --output-type`, exit 2 | ✅ Đạt |
| CLI-03 | `ccheck --output-type xml --filename $M\scenarios\s01_pass.yaml` | `invalid choice: 'xml'`, exit 2 | ✅ Đạt |
| CLI-04 | `ccheck --output-type file` | `--filename or --folder is required`, exit 2 | ✅ Đạt |
| CLI-05 | `ccheck --output-type file --filename $M\scenarios\s01_pass.yaml` | `--output-folder is required …`, exit 2 | ✅ Đạt |
| CLI-06 | `ccheck --output-type console --filename $M\scenarios\khong_ton_tai.yaml` | Báo `… do not exist. Check --filename argument.` | ✅ Đạt (thông báo nằm trong traceback dài) |
| CLI-07 | `ccheck --output-type console --filename $M\scenarios\s01_pass.yaml` | Bảng tổng kết Valid = OK, exit 0 | ✅ Đạt |
| CLI-08 | `ccheck --output-type file --filename $M\scenarios\s01_pass.yaml $M\scenarios\s02_fail.yaml --output-folder results --exit-on-failure --aggregate-results` | exit 1 (`echo $LASTEXITCODE`); thư mục `results` có 2 file `s01_pass_*.json` và `s02_fail_*.json` | ✅ Đạt |
| CLI-09 | `python -m contextcheck.question_answering --help` | Hiện hướng dẫn | ❌ `TypeError: … unexpected keyword argument 'type'` (lỗi C1) |

### Đọc YAML và Test Router

| ID | Lệnh (`ccheck --output-type console --filename …`) | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| RV-01 | `$M\scenarios\s03_variables.yaml` | `{{ country }}` được thay bằng `Poland`, Valid = OK | ✅ Đạt |
| RV-03 | `$M\scenarios\s05_regex_double_quotes.yaml` | Thông báo dễ hiểu, gợi ý dùng nháy đơn | ✅ `ValueError: Yaml parsing error. It was probably caused by your 'regex' assertion…` |
| RV-04 | `$M\scenarios\s06_unknown_kind.yaml` | Báo kind không hợp lệ, liệt kê các kind đúng | ✅ `Input should be 'openai', 'openai_compatible', …` |
| RV-06 | `$M\scenarios\s07_empty.yaml` | Báo "file rỗng" rõ ràng | ❌ `AttributeError: 'NoneType' object has no attribute 'get'` (lỗi R3) |
| RV-07 | `$M\scenarios\s08_typo_variable.yaml` | Báo biến `contry` không tồn tại | ❌ Không báo gì; request gửi đi là `'What is the capital of ?'` (lỗi R4) |
| RV-09 | `ccheck --output-type file --folder $M\folder_demo --output-folder results_folder` | Chạy cả 2 kịch bản trong thư mục | ✅ Chạy đủ 2 kịch bản (xem thêm TC-45 về file báo cáo) |
| RV-11 | `$M\scenarios\s09_bad_assertions.yaml` | 2 assertion lỗi được ghi log, assertion thứ 3 vẫn chạy, không crash | ✅ Log `Error during assertion` 2 lần, assertion `contains` = True, exit 0 |
| RV-12 | `$M\scenarios\s10_http_500.yaml $M\scenarios\s01_pass.yaml` *(cần mock server)* | Step lỗi bị đánh FAIL, kịch bản `s01` vẫn được chạy | ❌ Crash `HTTPError: 500…`, `s01` không được chạy (lỗi R1) |
| RV-13 | `$M\scenarios\s20_early_stop.yaml --exit-on-failure --show-time-statistics` | Ghi thống kê thời gian cho các step đã chạy | ❌ `AttributeError: 'NoneType' object has no attribute 'stats'` (lỗi R2) |

### Luồng Q&A toàn trình (E2E)

Hai bước sinh câu hỏi và sinh câu trả lời cần LLM thật, nên được kiểm thử bằng test tự động với LLM giả lập: `python -m pytest tests\test_e2e_qa_flow.py -v`. Bước regression (bước 3) kiểm thử thủ công được:

| ID | Thao tác | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| E2E-01 (bước 3) | Cửa sổ A chạy server bình thường; cửa sổ B: `ccheck --output-type console --filename $M\scenarios\s17_rag_regression.yaml` | 2 step đều OK | ✅ Đạt |
| E2E-04 | Cửa sổ A: Ctrl+C, rồi chạy `python $M\mock_server.py --empty-retriever`; cửa sổ B chạy lại lệnh trên | Không crash; 2 step FAIL; response là `I don't know.`; exit 0 | ✅ Đạt (lỗi hồi quy được phát hiện, không crash) |

Sau bước E2E-04, nhớ chạy lại server ở chế độ thường (bỏ `--empty-retriever`).

### Đa luồng: 50 request đồng thời

```powershell
python $M\scripts\concurrency_50.py          # cần mock server
```
Đã ghi nhận:
```
CC-01 independent executors: 50/50 passed, 0 hung, 0.32 s (serial would take ~10 s)
CC-02 shared endpoint      : 50/50 responses matched their request, 0 hung
CC-03 shared endpoint      : 16/50 responses report a wrong conn_duration
```
- CC-01 và CC-02 đạt: không deadlock, không lẫn dữ liệu giữa các luồng.
- CC-03 không đạt (lỗi T1): số response sai thời gian thay đổi theo mỗi lần chạy (từ 16 đến 32/50).

---

## 7.6 Phần Vũ Văn Toàn: Connectors, Endpoints (TC-01 – TC-10)

Các case có đánh dấu *(server)* cần mock server đang chạy ở cửa sổ A.

| TC | Lệnh | Kết quả mong đợi (theo kế hoạch) | Đã ghi nhận |
|---|---|---|---|
| TC-01 *(server)* | `ccheck --output-type console --filename $M\scenarios\s11_timeout.yaml`, rồi chờ khoảng 30 giây | Retry và ghi log lỗi timeout; tôn trọng `timeout: 5` trong YAML | ❌ Sau **30 s** (không phải 5 s) thì crash `ReadTimeoutError … (read timeout=30)`; không retry (lỗi D-01) |
| TC-02 *(server)* | `ccheck --output-type console --filename $M\scenarios\s10_http_500.yaml` | Bắt lỗi, không crash | ❌ Crash `HTTPError: 500 Server Error`; cửa sổ A chỉ có 1 dòng `POST /status/500` (lỗi D-02) |
| TC-03 | `python $M\scripts\openai_payload.py` (không gửi gì tới OpenAI) | Payload đúng chuẩn; `temperature` được gửi đi | ❌ Với 0.7 thì payload có `'temperature': 0.7`; với **0.0 thì payload không có `temperature`** (lỗi D-03) |
| TC-04 | `ccheck --output-type console --filename $M\scenarios\s01_pass.yaml` | Echo trả lại đúng request | ✅ Đạt |
| TC-05 *(server)* | `ccheck --output-type console --filename $M\scenarios\s13_tg_without_headers.yaml` | Chạy được với cấu hình tối thiểu | ❌ `AttributeError: 'EndpointConfig' object has no attribute 'additional_headers'` (lỗi D-04) |
| TC-06 *(server)* | `ccheck --output-type console --filename $M\scenarios\s12_rate_limit.yaml` | Chờ rồi gửi lại khi bị HTTP 429 | ❌ Crash `429 Client Error: Too Many Requests`; cửa sổ A chỉ có 1 request (lỗi D-05). Lưu ý: hệ thống không có Telegram |
| TC-07 *(server)* | `ccheck --output-type console --filename $M\scenarios\s14_markdown_unicode.yaml` | Markdown, tiếng Việt và emoji giữ nguyên | ✅ Valid = OK (N/A phần render Markdown, vì ContextCheck không render) |
| TC-08 | `ccheck --output-type console --filename $M\scenarios\s04_broken_bracket.yaml`, rồi chạy với `s05_regex_double_quotes.yaml` | Báo lỗi YAML có số dòng | ✅ `ParserError … line 2, column 8` và `ValueError: Yaml parsing error…` |
| TC-09 | `ccheck --output-type console --filename $M\scenarios\s21_missing_request.yaml` | Chặn step thiếu trường bắt buộc | ✅ `ValidationError … steps.0.request Field required` |
| TC-10 *(server)* | `ccheck --output-type console --filename $M\scenarios\s19_wrong_type.yaml` | Phát hiện response sai kiểu | ✅ `ValidationError … message Input should be a valid string` (lưu ý: chương trình dừng ngay ở đây) |

---

## 7.7 Phần Lê Phú Tuấn: Generators (TC-11 – TC-20)

Hai CLI `questions_generator` và `question_answering` cần khóa OpenAI và một RAG thật (CLI `question_answering` còn hỏng, xem CLI-09). Vì vậy phần lớn test case của Tuấn kiểm tra bằng script hoặc chạy đúng test tự động tương ứng.

| TC | Lệnh | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| TC-17 | `python $M\scripts\vietnamese_preprocess.py` (lần đầu cần internet để tải stopword NLTK) | Làm sạch ký tự đặc biệt | ✅ Câu tiếng Anh ra `['capital', 'poland', 'warsaw', 'naive', 'cafe']`. ⚠ Câu tiếng Việt 16 từ chỉ còn `['viet', 'thanh', 'nghin', 'lich']` |
| TC-19 | `python $M\scripts\jinja_ssti.py` | Câu hỏi được giữ nguyên khi nạp lại | ❌ `What is {{ 7*7 }}?` thành **`What is 49?`**: nội dung bị chạy như template Jinja2 (lỗi bảo mật D-10) |
| TC-18 | `python -m pytest tests\test_sqa_generators.py -k tc18 -s` | 1000 chunk xử lý xong dưới 10 phút | ✅ `[TC-18] chunks=1000 questions=1000 answers=1000 generate≈10.7s answer≈2.4s` |
| TC-11, 12, 13, 14, 15, 16, 20 | `python -m pytest tests\test_sqa_generators.py -v -rx` | Xem kết quả mong đợi của từng TC trong file Excel | 3 Đạt / 5 Không đạt / 2 N/A, khớp với báo cáo |

---

## 7.8 Phần Đào Xuân Dũng: Metrics (TC-31 – TC-40)

| TC | Lệnh | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| TC-31, 32, 49 | `ccheck --output-type console --filename $M\scenarios\s15_metrics.yaml --aggregate-results`, rồi xem cột **Valid** của bảng tổng kết (5 dòng, tên step ghi rõ kỳ vọng) | FAIL – OK – OK – FAIL – OK | Thực tế **FAIL – FAIL – OK – OK – FAIL**. Dòng 2: `equals` không bỏ ký tự xuống dòng (lỗi D-11). Dòng 4: `contains-all` với chuỗi so từng ký tự (lỗi D-12). Dòng 5: ví dụ regex trong docs không khớp email ở giữa câu (TC-49) |
| TC-33 | `ccheck --output-type console --filename $M\scenarios\s18_unknown_llm_metric.yaml` | Báo metric không tồn tại | ✅ `Input should be 'hallucination', 'qa-reference', 'model-grading-qa', 'summarization' or 'human-vs-ai'` (N/A: không có metric coherence) |
| TC-34 | `python -m pytest tests\test_sqa_metrics.py -k tc34 -s` | Khớp ground truth trên 80% | ❌ In ra `accuracy` ≈ 0,79 với icontains; 0,875 với icontains-any + từ đồng nghĩa; 0,42 với equals |
| TC-36 | Bảng "Mean score" cuối output của lệnh TC-31 ở trên | Có trọng số | N/A: chỉ là trung bình không trọng số theo từng metric |
| TC-37, 38 | Đọc `contextcheck\assertions\llm_eval_prompts.py`; chạy `python -m pytest tests\test_sqa_metrics.py -k "tc37 or tc38" -v -rx` | Prompt không thiên kiến; nhãn đọc ổn định | ❌ Nhãn `factual.` (có dấu chấm) bị coi là lỗi (lỗi D-13) |
| TC-39 | `python -m pytest tests\test_deterministric_metrics.py` | 100% đạt | ✅ `8 passed` |
| TC-40 | `python -m pytest tests\test_llm_metrics.py -rs` | 100% đạt | N/A: `1 skipped (need --openai option to run)`. Khi có khóa API: thêm `--openai` |

---

## 7.9 Phần Nguyễn Thạc Hưng: Giao diện, báo cáo, tài liệu (TC-41 – TC-50)

| TC | Thao tác | Kết quả mong đợi | Đã ghi nhận |
|---|---|---|---|
| TC-41 | `$env:COLUMNS = 40`; `ccheck --output-type console --filename $M\scenarios\s01_pass.yaml --aggregate-results --show-time-statistics`; `Remove-Item Env:COLUMNS`. Có thể thay bằng cách thu nhỏ cửa sổ trước khi chạy | Không vỡ khung | ✅ Không dòng nào rộng quá 40 cột; ⚠ nội dung bị cắt bằng `…` |
| TC-42 (**Windows thật**) | Mở cửa sổ PowerShell mới, **không** đặt `PYTHONUTF8`, activate venv. (a) `ccheck --output-type console --filename $M\scenarios\s01_pass.yaml > out.txt`. (b) `ccheck --output-type console --filename $M\scenarios\s14_markdown_unicode.yaml` | Chạy được như trên Linux | Đã giả lập trên Linux: (a) ❌ `UnicodeEncodeError … '\U0001f388'` (lỗi D-14). (b) Dự kiến ❌ `UnicodeDecodeError … 0x90` vì chữ "Đ". **Cần nhóm xác nhận trên Windows thật.** Nếu Windows đã bật "Beta: Use Unicode UTF-8…" thì có thể không lỗi |
| TC-43 | Windows: `New-Item -ItemType Directory ro_out`; `icacls ro_out /deny "$($env:USERNAME):(OI)(CI)W"`; `ccheck --output-type file --filename $M\scenarios\s01_pass.yaml --output-folder ro_out`. Dọn dẹp: `icacls ro_out /remove:d $env:USERNAME`; `Remove-Item ro_out`. Linux/macOS: `mkdir ro_out && chmod 555 ro_out` (không chạy bằng root) | Báo lỗi quyền ghi rõ ràng | ❌ (Linux) traceback `PermissionError: [Errno 13] Permission denied`, mất kết quả (lỗi D-15). Lệnh `icacls` chưa được thử trên Windows |
| TC-44 | `ccheck --output-type console --filename $M\scenarios\s16_json.yaml` | JSON hỏng bị chấm FAIL | ✅ Step 2 FAIL, log `Error message: Expecting ',' delimiter: line 1 column 38` |
| TC-45 | `ccheck --output-type file --folder $M\folder_demo --output-folder results_dup`, rồi `dir results_dup` | 2 kịch bản ra 2 file báo cáo | ❌ Chỉ còn **1 file** `smoke_<giờ>.json`: `smoke.v1` và `smoke.v2` ghi đè nhau (lỗi D-16) |
| TC-46 | `python -m flake8 contextcheck --count` | 0 vi phạm | ❌ `36` (24 E501, 11 W291, 1 E722) |
| TC-47 | `cd tests; python -m pytest --markers \| Select-String "openai\|ollama"; cd ..` | Có marker `openai` và `ollama` | ✅ Đạt |
| TC-48 | Làm lại mục 7.1 và 7.2 trong một thư mục mới, hoặc `pip install ccheck` trong venv sạch rồi `ccheck --help` | Làm theo README là chạy được | ✅ Đạt (ccheck 0.1.4 từ PyPI) |
| TC-49 | Dòng 5 của s15 (TC-31 ở trên); đọc `docs\docs\user_guide\llm_based_metrics.md` mục *Implementing metrics* rồi so với `contextcheck\assertions\assertions.py` | Tài liệu khớp code | ❌ Ví dụ regex không khớp; docs nói tự lấy reference nhưng code không làm vậy |
| TC-50 | Mở `examples\ex1.ipynb` bằng VS Code hoặc Jupyter và chạy lần lượt; hoặc `python -m pytest tests\test_sqa_interfaces_docs.py -k tc50 -v` | Chạy hết notebook | N/A: dừng ở cell 7 (`executor.run_all()`) vì thiếu `OPENAI_API_KEY`; 6/45 cell chạy được |

---

## 7.10 Xử lý sự cố thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `ccheck : The term 'ccheck' is not recognized…` | Chưa activate venv: chạy `.venv\Scripts\activate` |
| `…activate.ps1 cannot be loaded because running scripts is disabled` | Chạy một lần `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `UnicodeEncodeError` / `UnicodeDecodeError` | Chưa đặt `$env:PYTHONUTF8 = "1"` (trừ khi đang cố ý làm TC-42) |
| `ConnectionError … 127.0.0.1:8765` / `Connection refused` | Mock server chưa chạy ở cửa sổ A |
| `OSError: [WinError 10048]` khi bật mock server | Cổng 8765 đang bận: chạy `python $M\mock_server.py --port 8770` và sửa cổng trong các file YAML |
| `pip install` báo lỗi build `scipy` | Đang dùng Python 3.13; tạo lại venv bằng `py -3.11` |
| `vietnamese_preprocess.py` treo ở bước tải dữ liệu | Script cần internet để tải stopword NLTK lần đầu |
| Muốn xem tài liệu dạng web | `pip install mkdocs "mkdocstrings[python]" pymdown-extensions`, rồi `cd docs`, `mkdocs serve`, mở http://localhost:8000 |

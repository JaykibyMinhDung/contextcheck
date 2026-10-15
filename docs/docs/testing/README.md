# Bộ tài liệu kiểm thử ContextCheck

Thư mục này ghi lại toàn bộ công việc review code và kiểm thử ContextCheck (`ccheck` 0.1.4, commit gốc `04aab4f`): **đã kiểm tra gì, test case nào được viết bằng code ra sao, và mỗi test case phục vụ vai trò (actor) nào**.

## Mục lục

| # | Tài liệu | Nội dung |
|---|---|---|
| 0 | [BAO_CAO_KIEM_THU.md](BAO_CAO_KIEM_THU.md) | Báo cáo tóm tắt kết quả: số liệu, kết luận từng hạng mục |
| 1 | [01_PHAM_VI_VA_ACTOR.md](01_PHAM_VI_VA_ACTOR.md) | Phạm vi, danh sách actor, ma trận actor × test, môi trường, quy ước |
| 2 | [02_REVIEW_YAML_TEST_ROUTER.md](02_REVIEW_YAML_TEST_ROUTER.md) | Review logic đọc YAML, Test Router, fallback (RV-01 … RV-13) |
| 3 | [03_KIEM_THU_CLI_HOP_DEN.md](03_KIEM_THU_CLI_HOP_DEN.md) | 08 test case hộp đen cho CLI `ccheck` (TC-01 … TC-08, kèm TC-09) |
| 4 | [04_KIEM_THU_E2E_QA.md](04_KIEM_THU_E2E_QA.md) | Luồng Q&A toàn trình, Retriever trả danh sách rỗng (E2E-01 … E2E-06) |
| 5 | [05_KIEM_THU_DA_LUONG.md](05_KIEM_THU_DA_LUONG.md) | Kiểm thử đa luồng với 50 request (CC-01 … CC-03) |
| 6 | [06_DANH_SACH_LOI.md](06_DANH_SACH_LOI.md) | 8 lỗi đã xác nhận: cách tái hiện, mức độ, actor bị ảnh hưởng, đề xuất sửa |
| 7 | [07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md](07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md) | Cài và chạy dự án trên Windows; kiểm thử thủ công từng test case với mock server và kịch bản mẫu |

## Kết quả tổng

Bảng dưới là phần của Đoàn Minh Dũng. Từ khi có thêm bộ test của 4 thành viên còn lại (`tests/test_sqa_*.py`, xem sheet "3. Test Cases" trong file Excel của nhóm), toàn bộ suite cho kết quả:

```
python -m pytest tests
131 passed, 5 skipped, 30 xfailed    # chỉ cài các gói bắt buộc
132 passed, 3 skipped, 31 xfailed    # có thêm flake8, nbformat, nbclient, ipykernel
```

Hướng dẫn cài đặt trên Windows và kiểm thử thủ công từng bước: [07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md](07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md).

| Nhóm | File test | Số test | Đạt | Lỗi xác nhận (xfail) |
|---|---|---|---|---|
| Review YAML & Router | `tests/test_review_yaml_router.py` | 13 | 9 | 4 |
| CLI hộp đen | `tests/test_blackbox_cli.py` | 9 | 8 | 1 |
| E2E Q&A | `tests/test_e2e_qa_flow.py` | 6 | 4 | 2 |
| Đa luồng | `tests/test_concurrency.py` | 3 | 2 | 1 |
| **Tổng test mới** | | **31** | **23** | **8** |
| Test có sẵn của dự án | các file `tests/test_*.py` khác | 27 | 24 | 3 bỏ qua (cần OpenAI/Ollama) |

## Chạy lại

```sh
poetry env use python3.11      # trên Python 3.13, lockfile (scipy 1.13.1) không cài được
poetry install
poetry run pytest tests                              # toàn bộ
poetry run pytest tests/test_blackbox_cli.py -v      # từng nhóm
poetry run pytest tests -rx                          # hiện lý do của các xfail
```

Các test **không cần mạng hay khóa API**: RAG API được giả lập bằng `tests/mock_rag_server.py`, còn LLM sinh câu hỏi được thay bằng stub.

## Các file đã thêm vào repo

```
docs/docs/testing/                  ← bộ tài liệu này (hiển thị trong MkDocs)
tests/mock_rag_server.py            ← RAG API giả lập (HTTP thật, đa luồng)
tests/test_review_yaml_router.py    ← RV-01 … RV-13
tests/test_blackbox_cli.py          ← TC-01 … TC-09
tests/test_e2e_qa_flow.py           ← E2E-01 … E2E-06
tests/test_concurrency.py           ← CC-01 … CC-03
tests/test_sqa_*.py, sqa_http_stub.py ← TC-01 … TC-20, TC-31 … TC-50 của 4 thành viên còn lại
examples/manual_testing/            ← mock server, kịch bản mẫu, script cho kiểm thử thủ công
```

Không có file mã nguồn nào trong `contextcheck/` bị sửa: đây là đợt **kiểm thử và review**, chưa sửa lỗi.

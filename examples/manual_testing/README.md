# Bộ công cụ kiểm thử thủ công

Hướng dẫn từng bước: [docs/docs/testing/07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md](../../docs/docs/testing/07_HUONG_DAN_CHAY_VA_KIEM_THU_THU_CONG.md).

- `mock_server.py` – RAG/chatbot API giả lập tại `http://127.0.0.1:8765` (chỉ dùng thư viện chuẩn).
- `scenarios/` – kịch bản YAML mẫu `s01` … `s21`; dòng đầu mỗi file ghi mục đích.
- `folder_demo/` – 2 kịch bản để chạy theo `--folder`.
- `scripts/` – script cho các test case không làm được qua CLI.

Không chạy cả thư mục `scenarios/` bằng `--folder`: một số kịch bản được viết cố ý sai để kiểm thử xử lý lỗi.

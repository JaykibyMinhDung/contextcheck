# 5. Kiểm thử đa luồng (Concurrency Safety)

- **File test:** `tests/test_concurrency.py` (2 đạt, 1 xfail), dùng `tests/mock_rag_server.py`
- **Actor chính:** A4 Library Integrator. Gián tiếp: A2 CI/CD (chạy song song nhiều job)

## 5.1 Bối cảnh

Bản thân ContextCheck **chạy tuần tự**: `TestsRouter.run_tests` lặp qua từng file, có ghi chú `TODO: Potential place to increase performance by running several scenarios at once`. Vì vậy hạng mục này kiểm tra **tình huống ContextCheck bị gọi từ nhiều luồng cùng lúc**, như khi actor A4 nhúng `Executor` vào code của mình và chạy song song cho nhanh. Ba câu hỏi cần trả lời:

1. Có **deadlock** hoặc treo không?
2. Response có bị **lẫn giữa các luồng** không?
3. Tài nguyên (kết nối, luồng) có được **giải phóng hết** không, và dữ liệu đo đạc có còn **đúng** không?

## 5.2 Thiết kế

| Thông số | Giá trị |
|---|---|
| Số request đồng thời | **50** (`N_REQUESTS`) |
| Số luồng client | 50 (`ThreadPoolExecutor(max_workers=50)`) |
| Server | Mock RAG server đa luồng, `request_queue_size = 128` |
| Độ trễ mỗi request | ngẫu nhiên 50–200 ms (`DELAY`) |
| Ngưỡng coi là deadlock | request chưa xong sau **30 giây** (`DEADLOCK_TIMEOUT`) |
| Endpoint | `cc_ss` (HTTP POST) tới route `/echo`, route này trả lại đúng nội dung nhận được |

Request được gửi vào route `/echo` với nội dung riêng cho từng luồng (`request-0` … `request-49`). Nhờ đó, nếu response bị lẫn giữa các luồng thì test phát hiện được ngay.

### Phát hiện deadlock

```python
def run_concurrently(fn) -> tuple[list, float]:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N_REQUESTS) as pool:
        futures = [pool.submit(fn, i) for i in range(N_REQUESTS)]
        done, not_done = wait(futures, timeout=DEADLOCK_TIMEOUT)
        assert not not_done, f"{len(not_done)} requests did not finish: possible deadlock"
    return [f.result() for f in futures], time.perf_counter() - start
```

### Đo mức song song và giải phóng tài nguyên

Mock server đếm số request đang xử lý, có khóa `threading.Lock`:

```python
with state.lock:
    state.requests += 1
    state.active += 1
    state.max_active = max(state.max_active, state.active)
try:
    ...xử lý request...
finally:
    with state.lock:
        state.active -= 1
```

- `max_active > 1` chứng minh các request **thực sự chạy chồng lên nhau**, không phải bị tuần tự hóa ngầm.
- `active` trở về 0 sau khi chạy chứng minh mọi kết nối **đã được giải phóng**. Test chờ tối đa 2 giây, vì server giảm bộ đếm ngay sau khi gửi response:

```python
def all_released(state, timeout: float = 2.0) -> bool:
    deadline = time.perf_counter() + timeout
    while state.active and time.perf_counter() < deadline:
        time.sleep(0.01)
    return state.active == 0
```

## 5.3 Chi tiết test case

| ID | Test | Kịch bản | Kiểm tra | Kết quả |
|---|---|---|---|---|
| CC-01 | `test_50_concurrent_scenarios_with_independent_executors` | 50 luồng, **mỗi luồng một `TestScenario` + `Executor` riêng**, mỗi kịch bản 1 step với assertion `equals` | Không deadlock; 50/50 kịch bản đạt; server nhận đúng 50 request; `max_active > 1`; giải phóng hết; tổng thời gian nhỏ hơn thời gian tuần tự tốt nhất (50 × 50 ms) | ✅ |
| CC-02 | `test_50_concurrent_requests_on_a_shared_endpoint` | 50 luồng **dùng chung một endpoint** | Không deadlock; response thứ *i* đúng bằng `request-i`; `max_active > 1`; giải phóng hết | ✅ |
| CC-03 | `test_connection_time_stats_on_a_shared_endpoint` | Như CC-02, so `response.stats.conn_duration` với thời gian đo thật ở client | Mọi `conn_duration` lệch không quá 20% | ❌ T1 |

### Code CC-01

```python
def test_50_concurrent_scenarios_with_independent_executors(rag):
    base_url, state = rag

    def run_scenario(i: int) -> bool:
        scenario = TestScenario.model_validate({
            "config": {"endpoint_under_test": {"kind": "cc_ss", "url": f"{base_url}/echo"}},
            "steps": [{
                "name": f"step-{i}",
                "request": f"request-{i}",
                "asserts": [{"kind": "equals", "assertion": f"request-{i}"}],
            }],
        })
        return Executor(scenario).run_all()

    results, elapsed = run_concurrently(run_scenario)

    assert all(results)
    assert state.requests == N_REQUESTS
    assert state.max_active > 1                    # thực sự song song
    assert all_released(state)                     # giải phóng hết kết nối
    assert elapsed < N_REQUESTS * DELAY[0]         # nhanh hơn chạy tuần tự
```

## 5.4 Số liệu đo (3 lần chạy)

| Lần | CC-01: đạt / thời gian / song song tối đa | CC-02: đúng / thời gian | CC-03: `conn_duration` sai |
|---|---|---|---|
| 1 | 50/50 · 0,35 s · 40 | 50/50 · 0,28 s | 29/50 |
| 2 | 50/50 · 0,34 s · 44 | 50/50 · 0,29 s | 32/50 |
| 3 | 50/50 · 0,40 s · 33 | 50/50 · 0,28 s | 26/50 |

Để so sánh, chạy tuần tự 50 request với độ trễ trung bình 125 ms sẽ mất khoảng **6 giây**.

## 5.5 Phân tích lỗi T1

`EndpointBase.send_request` đo thời gian bằng chính object connector **dùng chung**:

```python
with self.connector as c:            # __enter__: self.stats.conn_start_time = now
    response_dict = c.send(...)
...                                  # __exit__: conn_duration = end - conn_start_time
response.stats = response.stats.model_copy(update=c.stats.model_dump())
```

Khi 50 luồng dùng chung một endpoint, luồng B ghi đè `conn_start_time` của luồng A trước khi A kết thúc. Kết quả là `conn_duration` của A bị tính sai, và các số liệu `--show-time-statistics` sai theo.

Phạm vi ảnh hưởng: **chỉ số liệu thời gian**. Request, response và kết quả assertion vẫn đúng (CC-02).

## 5.6 Kết luận

- Chạy đồng thời 50 request **không xuất hiện deadlock**. Hệ thống **cấp phát và giải phóng tài nguyên tốt**: mọi kết nối được đóng, có tới 33–44 request chạy song song cùng lúc, và chạy nhanh gấp khoảng 15–20 lần so với tuần tự.
- **Không lẫn dữ liệu** giữa các luồng, kể cả khi dùng chung một endpoint.
- **Hạn chế:** phần thống kê thời gian **không thread-safe** khi nhiều luồng dùng chung một endpoint (T1).
- **Khuyến nghị cho actor A4:** mỗi luồng nên tạo `Executor` (và endpoint) riêng, như CC-01.

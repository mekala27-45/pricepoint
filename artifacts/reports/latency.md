| Transport | p50 (ms) | p95 (ms) | p99 (ms) | Successful requests/s | Errors |
| --- | --- | --- | --- | --- | --- |
| in-process ASGI, no network or container | 7.480 | 17.189 | 24.778 | 452.53 | 0 |

Measured 2026-09-15T19:49:01.439725+00:00 on Windows-11-10.0.26200-SP0, Python 3.12.14. Concurrency 4, duration 30s (actual 30.005s), warmup 100 requests. Closed-loop concurrent clients; latency includes client serialization, ASGI routing, feature construction, incumbent and enabled shadow scoring. Warmup excluded. Throughput counts successful responses only.

| Latency bin (ms) | Successful requests |
| --- | --- |
| 0 to 1 | 0 |
| 1 to 2 | 1 |
| 2 to 5 | 939 |
| 5 to 10 | 9491 |
| 10 to 15 | 2107 |
| 15 to 25 | 907 |
| 25 to 50 | 111 |
| 50 to 100 | 14 |
| 100 to infinity | 8 |

| p50 (ms) | p95 (ms) | p99 (ms) | Successful requests/s | Errors |
| --- | --- | --- | --- | --- |
| 11.526 | 15.006 | 16.427 | 345.12 | 0 |

Container TCP measurement: 30s at concurrency 4, 100 warmup requests, Linux-6.17.0-1022-azure-x86_64-with-glibc2.39. CI stores the resolved base and built image identifiers.

Closed-loop concurrent clients; latency includes client serialization, ASGI routing, feature construction, incumbent and enabled shadow scoring. Warmup excluded. Throughput counts successful responses only.

| Latency bin (ms) | Successful requests |
| --- | --- |
| 0 to 1 | 0 |
| 1 to 2 | 0 |
| 2 to 5 | 20 |
| 5 to 10 | 2236 |
| 10 to 15 | 7577 |
| 15 to 25 | 515 |
| 25 to 50 | 0 |
| 50 to 100 | 8 |
| 100 to infinity | 0 |

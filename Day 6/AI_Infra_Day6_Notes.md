# AI Infrastructure — Day 6 Notes

## Theme
**OS Scheduling → GIL → Thread vs Process → Process Isolation → IPC → Data Movement → Shared Memory / Zero-Copy**

> **Find the bottleneck, then optimize the bottleneck. Parallelism is not free.**

## 1. Thread States & OS Scheduling
- **RUNNING**: currently executing on a CPU core.
- **RUNNABLE**: ready to execute, waiting for CPU/scheduler.
- **WAITING / BLOCKED**: waiting for I/O, lock, event, etc.

```text
1000 CPU-heavy tasks → OS Scheduler → 8 CPU cores
```

1000 workers do not create 1000-way hardware parallelism.

- Many RUNNABLE + high CPU → likely CPU contention.
- Many WAITING + low CPU → investigate I/O / DB / locks / downstream.

## 2. Context Switching
The OS saves/restores execution state when switching threads/processes and may disrupt cache locality.

After CPU capacity is saturated, more workers can add:
- scheduler contention
- context switching
- cache disruption
- memory overhead

## 3. Python GIL
ThreadPool CPU-heavy experiment:

| Workers | Time |
|---:|---:|
| 1 | 13.99s |
| 2 | 12.86s |
| 4 | 12.96s |
| 8 | 12.87s |
| 16 | 12.78s |
| 32 | 12.86s |

In ordinary **CPython**, CPU-heavy Python bytecode threads in the same interpreter compete for the **GIL**. More threads therefore do not provide ideal multi-core scaling.

This is runtime-specific: Java threads can execute CPU-heavy work across cores; Python threads can still be useful for I/O-heavy work.

## 4. ProcessPoolExecutor
ProcessPool experiment:

| Workers | Time |
|---:|---:|
| 1 | 14.13s |
| 2 | 7.05s |
| 4 | 3.52s |
| 8 | 2.01s |
| 16 | 1.14s |
| 32 | 1.14s |

Each worker process has its own interpreter/GIL, enabling real CPU parallelism. Scaling plateaus when CPU execution capacity saturates.

```text
Many logical tasks → bounded workers → finite physical resources
```

Use the multiprocessing main guard where needed:

```python
if __name__ == "__main__":
    for num_workers in [1, 2, 4, 8, 16, 32]:
        run_test(num_workers)
```

## 5. AI Workload Mapping

```text
Network / S3
    ↓ I/O-bound
Async / Event Loop
    ↓
Tokenization / preprocessing
    ↓ CPU-heavy
Bounded CPU workers / Process Pool
    ↓
GPU-ready Queue
    ↓
Inference Scheduler
    ↓
GPU
```

Real tokenizer/native-library threading behavior can differ; this is the simplified mental model.

## 6. Queue Location + Consumer Utilization

### CPU-side bottleneck
```text
Request Queue ↑↑
CPU = 100%
GPU = 30%
Profiler: 70% tokenization
```

Likely CPU preprocessing/tokenization bottleneck → GPU is underfed/starving. Do not add GPUs first.

### GPU-side bottleneck
```text
Request Queue: stable
GPU-ready Queue: ↑↑
CPU: 35%
GPU: 96%
HBM: 77/80 GB
Tokens/sec: plateau
TTFT: ↑
```

Investigate:
- inference scheduler
- batching efficiency
- compute throughput
- memory bandwidth
- HBM / KV cache pressure
- kernel efficiency

**GPU utilization 96% ≠ GPU compute efficiency 96%.**

## 7. Process Isolation
Threads in one process share code/heap/resources, while processes have separate virtual address spaces.

```text
Process A address space ≠ Process B address space
```

Process B cannot normally directly access an ordinary heap object owned by Process A.

## 8. IPC & Serialization

```text
Main Process
    ↓ serialize
IPC / memory movement
    ↓ deserialize
Worker Process
    ↓ compute
```

Possible costs:
- serialization
- IPC
- memory copies
- deserialization
- scheduling
- result transfer

Analogy to backend systems:

```text
Java Object → serialize → Kafka → deserialize → Consumer Object
```

## 9. Compute vs Communication Cost

Good Process Pool workload:

```text
small input → heavy computation → small output
Communication << Compute
```

Example: 1 KB input + 5 seconds compute.

Poor workload:

```text
huge input → tiny computation
Communication >>> Compute
```

Example: 5 GB input + 5 ms compute.

> **Process parallelism is useful only when its compute benefit justifies communication/data-movement overhead.**

## 10. IPC Benchmark

| Items | Process | Local |
|---:|---:|---:|
| 1K | 0.05s | ~0s |
| 100K | 0.05s | ~0s |
| 1M | 0.09s | ~0s |
| 5M | 0.27s | 0.02s |

For 5M items:

```text
Local computation ≈ 20 ms
Process total     ≈ 270 ms
Extra overhead    ≈ 250 ms
```

The extra cost includes more than IPC alone: ProcessPool startup, serialization, copying, scheduling, deserialization, and result transfer.

**Benchmark lesson:** know exactly what the measurement includes before attributing latency to one component.

## 11. Shared Memory

Instead of copying huge data between process heaps:

```text
              Shared Memory
             ┌────────────┐
             │   5GB data │
             └────────────┘
                ▲      ▲
                │      │
           Process A Process B
```

Processes can coordinate around explicitly shared memory and avoid some large cross-process copies.

## 12. Zero-Copy & Data Locality
Zero-copy is the broader idea of reducing unnecessary data copies across buffers, processes, address spaces, and devices.

Ask:

```text
Where is the data?
↓
Where must it go?
↓
How many times is it copied?
```

This is **Data Locality** thinking.

## 13. Connection to GPU Systems

```text
CPU RAM → PCIe → GPU HBM
```

Example:

```text
CPU preprocessing:    3 ms
CPU → GPU transfer:  25 ms
GPU compute:          4 ms
GPU → CPU transfer:   2 ms
Total:                34 ms
```

Optimize GPU compute 4ms → 2ms:

```text
New total = 32 ms
Latency reduction = (34-32)/34 ≈ 5.9%
```

GPU computation improved **50%**, but end-to-end latency improved only **~5.9%** because GPU compute was not the dominant component.

This is **Amdahl's Law / bottleneck thinking**.

## 14. Day 6 Debugging Framework

```text
Which Queue is growing?
        ↓
Who consumes it?
        ↓
What is the consumer doing/waiting for?
        ↓
RUNNABLE or WAITING?
        ↓
CPU / GPU / I/O / Memory?
        ↓
Find the actual bottleneck
        ↓
Optimize or scale that bottleneck
```

Before adding parallelism:

```text
Compute benefit
      vs
Communication + serialization + data movement + scheduling overhead
```

## Key Takeaways
1. RUNNABLE = waiting for CPU; WAITING/BLOCKED = waiting for another condition/resource.
2. More workers do not create more physical CPU capacity.
3. Ordinary CPython CPU-heavy threads are constrained by the GIL.
4. ProcessPool enables CPU parallelism but eventually saturates CPU capacity.
5. Process isolation creates communication boundaries.
6. IPC/data movement can dominate useful computation.
7. Small-data + compute-heavy tasks are strong candidates for process parallelism.
8. Shared memory / zero-copy reduce unnecessary movement.
9. GPU utilization alone does not identify the GPU bottleneck.
10. Queue location + consumer utilization is a strong debugging framework.
11. Optimize the dominant end-to-end bottleneck.
12. **Parallelism isn't free.**

## Day 6 Mantra

> **Queue 在哪里增长 → 谁在消费 → Consumer 在忙什么/等什么 → 找到真正的 bottleneck → 再决定 optimize 还是 scale。**

> **Compute can be fast; moving data can still be the bottleneck.**

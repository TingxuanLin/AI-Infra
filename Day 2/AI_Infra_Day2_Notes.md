# Day 2 --- Linux / OS 基础总结

## 1. Program vs Process

``` text
Program
   ↓ execute
Process
```

-   **Program**：硬盘上的静态代码。
-   **Process**：正在运行的程序实例，是 OS 创建的 resource container +
    execution environment。

``` text
Process
│
├── Virtual Address Space
├── Code
├── Heap
├── Threads
├── File Descriptors
└── OS Metadata
```

## 2. Virtual Memory

每个 Process 都有自己的 **Virtual Address Space**。

``` text
Process A Virtual Address → OS / MMU → Physical RAM X
Process B Virtual Address → OS / MMU → Physical RAM Y
```

所以两个 Process 都可以看到地址 `0x1000`，但不一定对应同一块 Physical
RAM。

核心作用之一：**Process Isolation**。

## 3. Stack vs Heap

**Stack**：主要与 Function Call、Local Execution State、Stack Frame
有关。

``` text
function()
   ↓
Stack Frame
├── local variables
├── parameters
└── return information
```

**Heap**：用于 **Dynamic Memory Allocation**。

核心记忆：

``` text
Stack → Function execution / Stack frame
Heap  → Dynamic allocation
```

不要简单记成 `Stack = short-term`、`Heap = long-term`。

## 4. CPU Memory vs GPU Memory

``` text
Process
├── CPU RAM
│   ├── Request Objects
│   ├── Tokenizer Data
│   ├── Buffers
│   └── Queues
└── GPU HBM
    ├── Model Weights
    ├── KV Cache
    └── Activations
```

``` text
CPU OOM  → System RAM / Process Memory
CUDA OOM → GPU HBM
```

System RAM 有空余也仍然可能 CUDA OOM。

## 5. Process vs Thread

``` text
Process
├── Shared
│   ├── Code
│   ├── Heap
│   └── File Descriptors
├── Thread A
│   └── Stack A
├── Thread B
│   └── Stack B
└── Thread C
    └── Stack C
```

同一个 Process 内：

-   Threads 共享 Heap / Code / File Descriptors 等资源。
-   每个 Thread 有自己的 Stack。
-   不同 Processes 默认 Memory Isolated。

## 6. Race Condition

多个 Threads 同时修改 Shared Memory：

``` text
counter = 0

Thread A: read 0 → +1 → write 1
Thread B: read 0 → +1 → write 1
```

理论应该得到 2，实际可能得到 1。

这叫 **Race Condition**。

一种解决方式是 `Lock / Mutex`，但 Lock 也可能带来 Performance Overhead。

## 7. Concurrency vs Parallelism

``` text
8 CPU Cores
100 Runnable Threads
        ↓
   OS Scheduler
        ↓
8 CPU Cores
```

-   **Concurrency**：很多 Threads 都处于进行状态。
-   **Parallelism**：多个 Threads 在同一时刻真正执行。

## 8. OS Scheduler

Scheduler 决定：

> 现在让哪个 Runnable Thread 使用 CPU。

它不断在 Runnable Threads 之间分配 CPU 时间。

## 9. Context Switch

``` text
Thread A Running
      ↓
Save A State
      ↓
Thread A Paused
      ↓
Load B State
      ↓
Thread B Running
```

这叫 **Context Switch**。

它可能因为 I/O Waiting、Time Slice 用完、Priority Change、Scheduler
Decision 等原因发生。

## 10. More Threads ≠ More Performance

``` text
Threads ↑
   ↓
Scheduling Overhead ↑
Context Switching ↑
Cache Disruption ↑
   ↓
Performance 可能下降
```

所以：

> **More Threads ≠ More Throughput**

与 Day 1 的 **Larger Batch ≠ Always Better** 是同一种系统思维。

## 11. CPU-bound vs I/O-bound

### CPU-bound

CPU 持续进行计算：

``` text
Thread → Compute → Compute → Compute → Result
```

例如 Tokenization、Compression、Encryption、Data Transformation。

CPU 已经 100% 时，单纯增加 Threads 通常不会创造更多计算能力。

### I/O-bound

大量时间等待 Network、Disk、Database、File、Socket。

``` text
Thread A
   ↓
Network Request
   ↓
Waiting
   ↓
CPU 执行 Thread B
   ↓
Data Ready
   ↓
Thread A 继续
```

因此 **Concurrency 对 I/O workload 特别重要**。

## 12. Blocking I/O

``` text
Thread
 ↓
recv()
 ↓
BLOCKED / WAITING
 ↓
CPU 执行其他 Thread
 ↓
Data Arrives
 ↓
RUNNABLE
 ↓
Scheduler
 ↓
CPU
```

重要：

> **Blocked Thread ≠ Thread 占着 CPU 空转。**

## 13. 为什么不能无限创建 Threads？

Thread 有成本：

``` text
Thread
├── Stack Memory
├── Scheduler State
└── Context Switching Cost
```

Threads 太多会导致 Memory、Scheduling Overhead、Context Switches 增加。

因此高并发系统常使用：

``` text
Async I/O
Event Loop
```

后续 Networking 会继续学习：

``` text
Socket → File Descriptor → epoll / kqueue → Event Loop
```

## 14. AI Infra 中的 CPU Bottleneck

例如：

``` text
Request Queue:    20,000
CPU Utilization: 100%
GPU Utilization: 25%
HBM Bandwidth:   20%
GPU Memory:      35%
```

可能是：

``` text
CPU Preprocessing / Tokenization
          ↓
      Bottleneck
          ↓
GPU 拿不到足够的数据
          ↓
GPU Utilization Low
```

所以：

> **GPU Utilization Low ≠ GPU 一定有问题**

## 15. 高 CPU Utilization 也不能直接说明原因

先检查 CPU 时间花在哪里：

``` text
├── Tokenization
├── Preprocessing
├── Serialization
├── Scheduler
├── Context Switching
└── Inefficient Code
```

如果大量时间消耗在 Context Switching，可能应该减少 Threads。

如果 CPU cores 都在进行真正有用、可并行的计算，增加 CPU cores
才可能有效。

> **Resource Utilization 高只能说明这里很忙，不能说明为什么忙。**

# Day 2 Lab

## Lab 1 --- Waiting Process

``` python
import os
import time

print("PID:", os.getpid())

while True:
    print("Worker waiting for I/O...")
    time.sleep(5)
```

实际观察：

``` text
Logical CPUs: 18
Process CPU:  0.0%
State:        sleeping
```

原因：

``` text
Thread → sleep() → Waiting → Scheduler 不给 CPU
```

结论：

> **Process 存在 ≠ Process 正在使用 CPU。**

## Lab 2 --- CPU-bound Process

``` python
import os

print("PID:", os.getpid())

x = 0

while True:
    x += 1
```

实际观察：

``` text
Process CPU ≈ 100%
```

因为 Thread continuously runnable，基本吃满一个 Logical CPU。

## 16. CPU % 的计量区别

机器有：

``` text
18 Logical CPUs
```

一个 CPU-bound Python Process：

``` text
≈ 100% CPU
```

在 macOS `top` 的 Process CPU 视角下，通常表示基本吃满 **1 个 Logical
CPU**，不是整台机器。

从整机总 capacity 角度：

``` text
100 / 1800 ≈ 5.6%
```

如果 18 个 CPU-bound Processes 真正并行：

``` text
CPU 1  → Process 1  → ~100%
CPU 2  → Process 2  → ~100%
...
CPU 18 → Process 18 → ~100%
```

整台机器接近 100% utilized。

某些工具采用累计显示时，也可能表示成：

``` text
18 × 100% = 1800%
```

所以看 CPU Metrics 时要先确认：

> **100% 代表一个 Logical CPU，还是整台机器？**

# Day 2 核心模型

``` text
Program
   ↓
Process
├── Virtual Memory
│   ├── Stack
│   └── Heap
├── Threads
│     ↓
│ Runnable / Waiting
│     ↓
│ OS Scheduler
│     ↓
│ CPU Cores
└── I/O
```

# Day 2 最重要的 Performance 思维

``` text
Metrics
   ↓
Locate Bottleneck
   ↓
Understand WHY
   ↓
Choose Optimization
   ↓
Measure Again
```

不要直接：

``` text
CPU 高 → 加 CPU
GPU 低 → 加 Batch
Threads 少 → 加 Threads
```

而应该先判断：

``` text
系统到底在等什么？
资源到底花在哪里？
真正限制 Throughput / Latency 的是什么？
```

## 今日关键词

`Program` · `Process` · `Virtual Memory` · `Stack` · `Heap` · `Thread` ·
`Shared Memory` · `Race Condition` · `Scheduler` · `Context Switch` ·
`Concurrency` · `Parallelism` · `CPU-bound` · `I/O-bound` ·
`Blocking I/O` · `Runnable` · `Waiting` · `Bottleneck`

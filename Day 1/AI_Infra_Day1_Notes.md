# Day 1 --- AI Infra 基础总结

## 1. AI Infra 的基本链路

``` text
User Request
    ↓
API / Load Balancer
    ↓
Queue / Scheduler
    ↓
Inference Engine (vLLM)
    ↓
PyTorch / CUDA
    ↓
GPU
```

核心目标：**低 latency、高 throughput、高 GPU
utilization、低成本、稳定运行。**

------------------------------------------------------------------------

## 2. Latency vs Throughput

**Latency**：一个 request 要等多久。

LLM 常见指标：

-   **TTFT**：Time To First Token
-   **TPOT**：Time Per Output Token

**Throughput**：系统单位时间处理多少工作。

``` text
requests/sec
tokens/sec
```

核心区别：

> Latency 看单个 request；Throughput 看整个系统。

------------------------------------------------------------------------

## 3. Batching

多个 request 一起交给 GPU：

``` text
A ─┐
B ─┼→ Batch → GPU
C ─┤
D ─┘
```

通常：

``` text
Batch ↑
→ Parallelism ↑
→ GPU utilization ↑
→ Throughput ↑
```

但代价可能是：

``` text
Memory usage ↑
Latency ↑
```

所以不是 batch 越大越好。

------------------------------------------------------------------------

## 4. Concurrency vs Parallelism

**Concurrency**

> 很多任务都处于进行状态。

100 threads 可以 concurrent。

**Parallelism**

> 多个任务在同一时刻真正执行。

如果只有 8 个 CPU cores，不代表 100 threads 能同时执行。

OS Scheduler 会：

``` text
100 Threads
    ↓
Scheduler
    ↓
8 CPU Cores
```

不断进行 **context switching**。

------------------------------------------------------------------------

## 5. Process → Thread → CPU

``` text
Application
    ↓
Process
    ↓
Thread
    ↓
OS Scheduler
    ↓
CPU Core
```

**Process**：程序运行实例。

**Thread**：CPU 实际调度执行的基本单位。

**Core**：执行 instructions 的硬件资源。

------------------------------------------------------------------------

## 6. GPU Compute

GPU 有大量并行计算资源：

``` text
GPU
 ├─ SM
 │   ├─ CUDA Cores
 │   └─ Tensor Cores
 │
 └─ HBM
```

**CUDA Core**：通用数值计算。

**Tensor Core**：特别擅长矩阵计算。

Transformer 大量涉及 matrix multiplication，因此适合 GPU。

------------------------------------------------------------------------

## 7. Memory 最重要的两个概念

一定区分：

### Memory Capacity

``` text
单位：GB
```

代表：**能装多少。**

例如：

``` text
Model = 90 GB
HBM = 80 GB

→ 放不下
→ Capacity problem / OOM
```

### Memory Bandwidth

``` text
单位：GB/s、TB/s
```

代表：**数据搬得多快。**

可以记成：

> Capacity = 水箱大小\
> Bandwidth = 水管粗细

------------------------------------------------------------------------

## 8. Compute-bound vs Memory-bound

### Compute-bound

``` text
Memory → GPU → GPU疯狂计算
                  ↑
               bottleneck
```

瓶颈是计算能力。

增加 compute capability 有明显帮助。

### Memory-bound

``` text
HBM ──慢慢送数据──→ GPU
                    ↑
                  等数据
```

瓶颈是 memory access / bandwidth。

即使：

``` text
GPU Compute × 2
```

也可能几乎没提升。

------------------------------------------------------------------------

## 9. GPU Utilization 低 ≠ GPU 不够强

例如：

``` text
GPU Compute = 20%
```

可能是：

``` text
Batch 太小
CPU bottleneck
Scheduler bottleneck
Network bottleneck
Memory bandwidth bottleneck
Synchronization
```

所以不能看到 GPU utilization 低就直接：

``` text
增加 batch
换更强 GPU
```

------------------------------------------------------------------------

## 10. AI Infra 最重要的 Performance 思维

今天最应该记住的是：

``` text
System Slow
    ↓
Measure
    ↓
Find Bottleneck
    ↓
Optimize Bottleneck
    ↓
Measure Again
```

分析整个 pipeline：

``` text
Request
  ↓
Network
  ↓
CPU
  ↓
Scheduler
  ↓
Queue / Batcher
  ↓
GPU
 ├─ Compute
 └─ Memory
     ├─ Capacity
     └─ Bandwidth
```

**不要看到哪里 utilization 低就优化哪里；要找到真正限制整个系统性能的
bottleneck。**

## 今日关键词

`Latency` · `Throughput` · `TTFT` · `Batching` · `Concurrency` ·
`Parallelism` · `Process` · `Thread` · `Context Switch` ·
`GPU Utilization` · `Memory Capacity` · `Memory Bandwidth` ·
`Compute-bound` · `Memory-bound` · `Bottleneck`

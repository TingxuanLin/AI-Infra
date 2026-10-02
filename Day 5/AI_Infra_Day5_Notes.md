# AI Infrastructure --- Day 5 Notes

## Theme

**Concurrency → Thread Pool → Worker Model → Queue / Backpressure →
Little's Law → AI Inference Worker**

> **Scale the bottleneck, not the symptom.**

## 1. Thread Pool Mental Model

Traditional Spring MVC / Tomcat:

``` text
HTTP Request → Request Queue → Tomcat Worker Pool → Controller/Service → DB/downstream
Threads → OS Scheduler → CPU Cores
```

A worker thread is not a CPU core. More CPU-heavy threads do not create
more compute capacity. Too many runnable threads increase scheduling
overhead, context switching, stack memory, and cache disruption.

## 2. Blocking I/O vs Event Loop

Blocking worker:

``` text
Request → Worker Thread → DB call → Thread WAITING
```

The CPU may run another thread, but the worker remains occupied.

Async/event loop:

``` text
Coroutine → await I/O → Coroutine suspends → Event Loop runs other coroutines
```

Coroutine suspends/yields; OS threads block/wait. New coroutine ≠ new
thread.

CPU-heavy work should not occupy an Event Loop Thread for long. It can
be offloaded to a bounded CPU worker pool. Work handoff between threads
is distinct from an OS context switch.

## 3. Three Scheduling Layers

``` text
OS Scheduler:        Threads → CPU Cores
Event Loop:          Coroutines → Event Loop Thread
Inference Scheduler: Requests/Sequences/Tokens → GPU batches/execution
```

Same high-level problem: lots of work competing for finite resources,
but different scheduled objects/resources.

## 4. Thread Pool vs DB Connection Pool

Example:

``` text
Tomcat Threads:       200/200 busy
CPU:                  30%
DB Connections:       50/50 busy
DB latency:           800ms
HTTP Queue:           increasing
```

Do not immediately add Tomcat threads. The DB path may be the
constrained resource.

**Thread occupied ≠ CPU busy.** A worker may be waiting for a connection
or downstream I/O.

Debugging question: \> Why are workers not completing/releasing quickly
enough?

## 5. Kafka Analogy

``` text
8 Kafka partitions ≠ 100 consumers give 100× parallelism
8 CPU cores ≠ 1000 CPU-heavy threads give 1000× compute
1 saturated GPU ≠ 10 inference workers give 10× throughput
```

Find the real constrained resource.

## 6. Little's Law

``` text
L = λW
Average concurrency ≈ arrival rate × average time in system
```

Example:

``` text
500 req/s × 0.2s = 100 concurrent requests
500 req/s × 2.0s = 1000 concurrent requests
```

Traffic can remain unchanged while higher latency causes concurrency to
explode.

``` text
Downstream latency ↑
→ request lifetime ↑
→ concurrency ↑
→ workers occupied longer
→ thread pool full
→ queue ↑
```

## 7. Queue: Burst Absorption, Not Capacity

A queue can absorb a short burst and drain later when arrival rate falls
below service capacity.

For sustained overload:

``` text
arrival rate > service capacity
→ backlog keeps growing
```

Making the queue larger does not increase throughput.

## 8. Waiting Time vs Service Time

``` text
Total latency = queue waiting time + service time
```

Increasing queue capacity can increase accepted backlog, memory usage,
and waiting latency without changing service time or throughput.

For sustained overload, optimize/scale the actual bottleneck, use
appropriate horizontal scaling/batching/caching, or reject/load-shed.

## 9. Backpressure / Admission Control

Example:

``` text
Workers = 3
Queue slots = 5
Total accepted/in-flight = 8
```

If 20 arrive immediately:

``` text
3 executing
5 queued
12 rejected
```

Possible HTTP responses include 429 or 503.

Backpressure protects system stability when arrival rate exceeds
capacity.

## 10. ThreadPoolExecutor Lab

With `max_workers=3`, only three workers execute concurrently. Other
submitted tasks wait in the executor work queue.

Important: \> **Queue order ≠ execution order ≠ log order ≠ completion
order.**

OS scheduling can make logs appear as `3, 5, 4` even if tasks were
dequeued in FIFO order.

## 11. Unbounded Queue Problem

Submitting huge numbers of tasks to three slow workers:

``` text
Fast producer → growing internal queue → 3 workers
```

If each worker takes 2s:

``` text
capacity ≈ 3 / 2 = 1.5 tasks/sec
```

More submitted work increases backlog/memory/waiting latency, not
throughput.

## 12. Bounded Capacity Lab

We used a semaphore to model:

``` text
3 executing + 5 queued = 8 admission slots
```

The admission slot is released only when the Future completes.

``` text
submit ≠ start ≠ finish
```

Releasing immediately after `submit()` would make admission control
ineffective while the executor queue continued growing.

## 13. AI Inference Worker Model

Simplified:

``` text
HTTP
→ async/event loop
→ Request Queue
→ CPU preprocessing
→ Inference Scheduler
→ GPU
```

LLM generation is sequential within a sequence:

``` text
token1 → token2 → token3
```

but different active sequences can participate in the same GPU execution
step/batch. This leads toward **continuous batching**.

## 14. More Inference Workers ≠ More GPU Capacity

Adding workers does not automatically add GPU compute, HBM capacity, or
memory bandwidth.

Same reasoning:

``` text
DB saturated → more Tomcat threads do not add DB capacity
8 cores → 1000 CPU-heavy threads do not add CPU capacity
GPU saturated → more workers do not create GPU capacity
```

## 15. GPU Utilization ≠ Compute Saturation

`GPU-Util = 95%` roughly indicates kernels were executing during most of
the sampling interval. It does not mean 95% of CUDA/Tensor cores were
doing useful math.

Possible bottlenecks: - compute - memory bandwidth - HBM capacity -
batching/scheduling - kernel efficiency/workload shape

Useful metrics include compute throughput, memory bandwidth, HBM usage,
batch size, tokens/sec, TTFT, TPOT, and queue depth.

## 16. Request Queue vs Inference Queue

These are not universally standardized names. For our course mental
model:

``` text
Client
  ↓
Request Queue
  ↓
CPU preprocessing (tokenization/validation)
  ↓
Inference / Scheduler Queue
  ↓
Inference Scheduler
  ↓
Batch
  ↓
GPU
```

### Request Queue

Requests have entered the service but may not have completed CPU-side
preprocessing.

``` text
Request Queue ↑
CPU = 100%
GPU = 35%
```

can indicate CPU bottleneck → GPU starvation.

### Inference / GPU-ready Scheduler Queue

Prepared requests/sequences are waiting for scheduling/GPU execution.

``` text
Inference Queue ↑
CPU = 30%
GPU = 95%
```

provides stronger evidence of GPU-path capacity pressure.

If:

``` text
GPU-ready Queue ↑
GPU = 35%
```

there is ready work but GPU is underutilized; investigate scheduler,
batching, kernels, and workload shapes.

**Debugging rule:**

``` text
Which queue?
Where is it in the pipeline?
Who consumes it?
Is that consumer saturated?
Why can't it keep up?
```

## 17. Unified Bottleneck Framework

``` text
Queue growing
→ identify which queue
→ identify its consumer
→ measure constrained resource
→ determine why it is saturated/underfed
→ optimize or scale the bottleneck
→ measure again
```

> **Scale the bottleneck, not the symptom.**

## 18. Backend ↔ AI Infra Mapping

  Backend / Distributed Systems   AI Infrastructure
  ------------------------------- ------------------------------------
  HTTP Request Queue              Request Queue
  Tomcat Worker Pool              CPU preprocessing workers
  DB/downstream capacity          GPU/scheduler/downstream capacity
  OS Scheduler                    OS Scheduler
  Queue + Backpressure            Admission Queue + Backpressure
  CPU bottleneck                  Tokenizer/scheduler CPU bottleneck
  Batch processing                GPU batching
  Service latency                 TTFT / TPOT / inference latency

The analogy helps reasoning, but the execution mechanisms are not
identical.

## 19. Day 5 Takeaways

1.  Thread busy does not imply CPU busy.
2.  More threads do not create more CPU cores.
3.  Queue absorbs bursts; it does not add capacity.
4.  Bounded queues enable backpressure.
5.  Total latency = queue waiting time + service time.
6.  Little's Law connects arrival rate, latency, and concurrency.
7.  Higher concurrency can result from higher traffic or higher latency.
8.  Adding workers only helps if the underlying constrained resource can
    do more useful work.
9.  GPU utilization alone does not identify compute vs memory
    bottlenecks.
10. Always identify which queue is growing and who consumes it.
11. Scale the bottleneck, not the symptom.

## 20. Follow-up Project Topic --- OpenSearch Map Search

Discuss later: - Map search cap of 500 markers. - Dataset grew from
\~20K to \~2M listings. - Zillow-like behavior: limited price markers
refreshed by viewport/zoom. - Spatially representative selection instead
of retrieving every matching listing. - `geotile_grid` - spatial
partitioning - `top_hits` - viewport/zoom-dependent marker density -
avoiding parallel-pagination fan-out - deterministic selection -
OpenSearch latency/payload benchmarking - browser rendering cost

Design lesson: \> Before adding concurrency, determine whether changing
the query/data representation solves the real problem.

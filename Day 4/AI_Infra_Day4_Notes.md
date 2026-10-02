# AI Infrastructure — Day 4 Notes

## 1. Async / Coroutine / Event Loop
- `async def` defines a coroutine function; it does not automatically mean parallel or non-blocking execution.
- `await` can suspend the **coroutine** and return control to the Event Loop.
- `await asyncio.sleep(5)` suspends the coroutine; `time.sleep(5)` blocks the Event Loop Thread.
- CPU-heavy work that does not yield can also block other coroutines.

```text
await → suspend Coroutine
blocking call → block Thread
```

## 2. Producer / Consumer / Request Queue

```text
Clients → Event Loop / Producer → Request Queue → Consumer / Scheduler → GPU
```

A queue decouples components with different speeds and can absorb short bursts, but it does not create processing capacity.

Example:
```text
Arrival = 1000 req/s
Service = 700 req/s
Backlog growth = 300 req/s
```

## 3. Short Burst vs Sustained Overload
A short burst can be absorbed by a queue and drained later when service capacity exceeds arrival rate.

For sustained overload (`Arrival > Service Capacity`), the backlog keeps growing. Increasing queue capacity only delays saturation; it does not fix the capacity deficit.

## 4. Backpressure
Backpressure means downstream saturation propagates upstream instead of allowing unlimited accumulation.

```python
queue = asyncio.Queue(maxsize=5)
await queue.put(request)
```

When the queue is full, the Producer coroutine suspends until space becomes available. The Event Loop Thread remains free to run other coroutines.

```text
Slow Consumer
    ↑
Queue Full
    ↑
Producer forced to slow down
```

### Backpressure vs Scaling
- **Backpressure:** protects memory, latency, and stability.
- **Scaling:** increases service capacity when the scaled resource is actually the bottleneck.

Real systems may combine bounded queues, 429/503 responses, rate limiting, admission control, deadlines, and autoscaling.

## 5. Queue Lab

### Producer
```python
async def producer(queue):
    for i in range(10):
        request = f"request {i}"
        await queue.put(request)
        print(f"Produced: {request}, Queue size: {queue.qsize()}")
        await asyncio.sleep(0.2)
```

Producer rate ≈ 5 req/s.

### Consumer
```python
async def consumer(queue):
    while True:
        request = await queue.get()
        print(f"Consumed: {request}, Queue size: {queue.qsize()}")
        await asyncio.sleep(2)
        print(f"Finished: {request}")
        queue.task_done()
```

Consumer rate ≈ 0.5 req/s.

### Main
```python
async def main():
    queue = asyncio.Queue(maxsize=5)
    consumer_task = asyncio.create_task(consumer(queue))
    await producer(queue)
    await queue.join()
    consumer_task.cancel()
```

## 6. `get()`, `task_done()`, `join()`
- `await queue.get()` means the item left the waiting queue.
- It does **not** mean processing finished.
- `queue.task_done()` marks one dequeued task as completed.
- `await queue.join()` waits until every queued task has a corresponding `task_done()`.

```text
Queue empty ≠ All work finished
```

## 7. Observed Backpressure
Observed behavior:

```text
Queue reaches size 5
→ Producer tries next put()
→ Producer suspends
→ Consumer removes one item
→ Queue size becomes 4
→ Producer resumes
→ Queue returns to 5
```

The bounded queue prevents unlimited internal growth, but it does not change the Consumer's underlying 0.5 req/s capacity.

## 8. Batching
Instead of processing one request at a time:

```text
R1 → GPU
R2 → GPU
R3 → GPU
```

batching can do:

```text
R1 ─┐
R2 ─┼→ Batch → GPU
R3 ─┘
```

Batching can improve GPU utilization and throughput, but very large batches can increase waiting latency, GPU memory usage, and OOM risk.

## 9. Simple Batch Consumer
```python
async def consumer(queue):
    while True:
        batch = []

        request = await queue.get()
        batch.append(request)

        while len(batch) < 3 and not queue.empty():
            request = queue.get_nowait()
            batch.append(request)

        print(f"Consumed: {batch}, Queue size: {queue.qsize()}")

        await asyncio.sleep(2)

        for _ in batch:
            queue.task_done()
```

Design:
```text
Wait for first request
→ take additional requests already available
→ max batch size = 3
→ start processing
```

The extra requests use `get_nowait()` so an existing request is not forced to wait while the scheduler tries to fill the batch.

With multiple consumers, `empty()` followed by `get_nowait()` is not atomic; another consumer could take the item between the two operations. This will be revisited with race conditions/concurrency.

## 10. Bottleneck Thinking
Scenario:

```text
Request Queue ↑
GPU Utilization = 35%
CPU Utilization = 100%
```

Do not automatically add GPUs. The CPU, tokenizer, scheduler, blocking work, or another upstream component may be the bottleneck, leaving the GPU underfed.

```text
Measure → Locate bottleneck → Profile → Optimize/Scale constrained resource → Measure again
```

## 11. Mapping to LLM Infrastructure

```text
Lab                     LLM Serving
producer()          →   incoming HTTP requests
queue.put()         →   enqueue request
asyncio.Queue       →   inference request queue
consumer()          →   scheduler / worker
asyncio.sleep(2)    →   simulated GPU inference
batch               →   GPU inference batch
maxsize             →   admission capacity
task_done()         →   processing complete
```

Architecture:

```text
HTTP Requests
      ↓
API / Event Loop
      ↓
Admission Control
      ↓
Request Queue
      ↓
Batch / Inference Scheduler
      ↓
GPU Worker
```

## Day 4 Key Takeaways
1. `async def` alone does not make code non-blocking.
2. `await` suspends a coroutine; blocking calls can block the Event Loop Thread.
3. Queue absorbs temporary bursts but does not create processing capacity.
4. Backpressure protects saturated systems from unlimited internal backlog.
5. Backpressure and scaling solve different problems.
6. `queue.get()` means dequeued; `task_done()` means completed.
7. `queue.join()` waits for all unfinished tasks.
8. Batching improves GPU efficiency but introduces latency/memory trade-offs.
9. High queue depth does not automatically mean more GPUs are needed.
10. Measure the real bottleneck before scaling.

```text
Coroutine
   ↓
await / yield
   ↓
Event Loop
   ↓
Producer
   ↓
Bounded Queue
   ↓
Backpressure
   ↓
Batch Scheduler
   ↓
GPU Worker
   ↓
Measure bottleneck
   ↓
Optimize / Scale
```

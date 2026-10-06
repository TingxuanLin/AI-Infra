# AI Infrastructure — Day 7 Notes

## Linux Container Fundamentals → Docker → Networking → Containerized Inference API

## 1. Core Mental Model

```text
Container
≈ isolated/resource-controlled Linux processes

├── Namespace → What can I see?
├── Cgroup    → How much can I use?
├── Image     → What userspace/files/runtime do I start with?
└── Host Linux Kernel
```

A container is not a lightweight VM and does not have its own Linux kernel.

## 2. Container and Process

At the Linux level, the application inside a container is still an ordinary Linux process. A container can contain multiple processes.

Docker/container runtimes configure isolation, resource controls, filesystem, networking, and lifecycle around those processes.

## 3. PID Namespace

Namespaces provide isolated views of system resources.

Day 7 lab:

```text
Host view:
PID 62090 → sleep 3600

Container view:
PID 1 → sleep 3600
```

These are the same process viewed through different PID namespaces.

`docker exec -it infra-lab bash` starts another process inside the existing container; it does not create another container.

The container main process is PID 1 from the container's PID namespace. Container lifecycle is closely tied to that main process.

## 4. Network Namespace

A container has its own network view and port space.

```text
Container A → app :8080
Container B → app :8080
```

These do not conflict because the containers have different network namespaces.

This connects to Day 3:

```text
Process → socket() → bind(IP, port) → listen()
```

Docker does not replace TCP/socket fundamentals.

## 5. Cgroup

Namespaces answer:

> What can I see?

Cgroups answer:

> How much can I use?

Cgroups can control CPU, memory, I/O, and process counts.

Example:

```text
Host: 32 CPU cores
Container CPU limit: 2
```

This does not create or permanently assign two physical cores. It constrains the workload to roughly 2 cores worth of CPU execution time.

```text
50 CPU-heavy threads
        ↓
cgroup CPU limit = 2
        ↓
≈ 2 cores worth of execution capacity
```

Increasing 50 threads to 200 does not change the underlying CPU capacity.

Key rule:

> Physical resource available ≠ workload resource entitlement.

## 6. Cgroup Lab

Started:

```bash
docker run --name limited-lab \
  --cpus="1" \
  --memory="256m" \
  -d ubuntu:24.04 sleep 3600
```

Docker inspection showed:

```text
Memory=268435456 bytes
NanoCPUs=1000000000
```

Inside the container:

```bash
cat /sys/fs/cgroup/cpu.max
```

Observed:

```text
100000 100000
```

For cgroup v2 this represents quota and period:

```text
100000 / 100000 = 1 CPU worth
```

Memory:

```bash
cat /sys/fs/cgroup/memory.max
```

Observed:

```text
268435456
```

which is 256 MiB.

## 7. Container vs VM

Container:

```text
Application
    ↓
Isolated Linux Process
    ↓
Host Linux Kernel
    ↓
Hardware
```

VM:

```text
Application
    ↓
Guest OS
    ↓
Guest Kernel
    ↓
Hypervisor
    ↓
Hardware
```

Core distinction:

> Container shares the Host Kernel. VM has its own Guest Kernel.

## 8. Docker Image

An image is a static reusable package/template containing the userspace environment needed by an application, such as runtime, application code, libraries, files, and metadata/config.

It does not contain its own Linux kernel.

Useful rough analogy:

```text
Java Class → Object
Docker Image → Container
```

Multiple containers can be started from the same image.

## 9. What docker run Does

Conceptually:

```text
docker run
    ↓
prepare image/filesystem
    ↓
configure namespaces
    ↓
configure cgroups
    ↓
configure networking
    ↓
start application process
    ↓
manage lifecycle
```

At the bottom, Linux still schedules ordinary processes.

## 10. Docker Port Publishing

Syntax:

```bash
docker run -p HOST_PORT:CONTAINER_PORT image
```

Lab:

```bash
docker run -p 8080:80 nginx
```

Request path:

```text
Host :8080
    ↓
Docker port publishing
    ↓
Container :80
    ↓
nginx
```

From the host, `curl localhost:8080` succeeded.

Inside the container, `curl localhost:80` succeeded, while `curl localhost:8080` failed because nothing was listening on container port 8080.

Two containers can both listen internally on 8080, but two containers cannot both publish the same host address/port combination.

## 11. Dockerfile

Project:

```text
ai-infra-day7/
├── app.py
├── requirements.txt
└── Dockerfile
```

FastAPI app:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/generate")
def generate(prompt: str):
    return {
        "prompt": prompt,
        "output": f"Generated response for: {prompt}"
    }
```

Dependencies:

```text
fastapi
uvicorn
```

Dockerfile:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Important distinction:

```text
BUILD TIME
Dockerfile → docker build → Image
             ↑
            RUN

RUN TIME
Image → docker run → Container → Process
                         ↑
                        CMD
```

For this image, the container main process/PID 1 is `uvicorn`.

## 12. First AI Infra Image

Built with:

```bash
docker build -t ai-infra-api:v1 .
```

Result:

```text
IMAGE             ID             DISK USAGE   CONTENT SIZE
ai-infra-api:v1   a2c1fc961ae1   250MB        55.4MB
```

Started with:

```bash
docker run --name inference-api \
  -d \
  -p 8000:8000 \
  ai-infra-api:v1
```

Successfully tested:

```bash
curl localhost:8000/health
curl "localhost:8000/generate?prompt=hello"
```

## 13. Full Request Path

```text
Dockerfile
    ↓ docker build
Image: ai-infra-api:v1
    ↓ docker run
Container
    ↓
uvicorn process
    ↓
FastAPI
    ↓
socket :8000
```

Request:

```text
curl
 ↓
Host localhost:8000
 ↓
Docker port publishing
 ↓
Container Network Namespace
 ↓
Container :8000 listening socket
 ↓
uvicorn
 ↓
FastAPI
 ↓
generate()
 ↓
HTTP response
```

## 14. Bottleneck Scenario

Scenario:

```text
Host: 32 CPU cores / 128 GB RAM
Container: CPU limit = 4, Memory limit = 16 GB
Application: FastAPI + vLLM

Request Queue ↑↑
Host CPU = 30%
Container CPU ≈ limit
GPU = 35%
```

Reasoning:

- Host CPU at 30% does not prove the workload has enough CPU because the container is constrained by its cgroup.
- Increasing FastAPI workers from 8 to 64 does not create more CPU capacity.
- First suspected bottleneck is the container CPU / CPU-side processing path.
- GPU at only 35% is consistent with the GPU potentially being underfed.
- In production, profile tokenization, preprocessing, request handling, scheduling, etc. before changing limits.

Key principle:

> Scale the bottleneck, not the symptom.

## 15. Portfolio Project Tracks

### Project 1 — Containerized Inference API

Current starting point:

```text
FastAPI → Docker → Containerized inference-style API
```

Current artifact: `ai-infra-api:v1`.

Future additions: real model inference, configuration, health/readiness endpoints, resource limits, deployment.

### Project 2 — Inference Serving & Performance

Focus on:

- Request queues
- Batching
- Continuous batching
- KV cache
- vLLM
- Throughput vs latency
- Memory pressure
- Serving optimization

Benchmark:

- TTFT
- TPOT
- tokens/sec
- P50/P99 latency

### Project 3 — Distributed LLM Serving Platform

Target:

```text
Client
  ↓
API Gateway
  ↓
Scheduler
  ↓
┌───────────────┐
│ vLLM Worker A │ → GPU
│ vLLM Worker B │ → GPU
│ vLLM Worker C │ → GPU
└───────────────┘
```

Features:

- Request scheduling
- Load balancing
- Multi-GPU
- Horizontal scaling
- Autoscaling
- Failure handling
- Admission control/backpressure

### Project 4 — Observability & Performance Engineering

Potential stack:

```text
Application Metrics
       ↓
Prometheus
       ↓
Grafana
```

Track:

- Request rate
- Queue depth
- CPU
- Memory
- GPU utilization
- HBM
- TTFT
- TPOT
- tokens/sec
- P50/P99 latency

Use load tests to deliberately create bottlenecks and explain them.

### Final Portfolio System

The projects progressively combine into one larger system:

```text
             Client
                ↓
          API Gateway
                ↓
        Admission Control
                ↓
          Request Queue
                ↓
      Inference Scheduler
         /      |      \
        ↓       ↓       ↓
     Worker   Worker   Worker
        ↓       ↓       ↓
       GPU     GPU     GPU

              +
       Observability
              +
         Kubernetes
              +
     Autoscaling / Recovery
```

The goal is to demonstrate Linux/OS, networking, containers, Kubernetes, distributed systems, GPU infrastructure, LLM serving, performance engineering, and observability—not merely that an LLM can generate text.

## 16. Day 7 Final Mental Model

```text
Dockerfile
    ↓
docker build
    ↓
Image
    ↓
docker run
    ↓
Container
    ↓
Linux Processes
    │
    ├── Namespace → What can I see?
    ├── Cgroup    → How much can I use?
    ├── Network Namespace → sockets / port space
    └── Image filesystem/runtime
          ↓
     Host Linux Kernel
          ↓
       Hardware
```

### One-line takeaway

> A container is fundamentally Linux processes running on the host kernel with isolated views, controlled resources, and a packaged userspace/runtime environment.

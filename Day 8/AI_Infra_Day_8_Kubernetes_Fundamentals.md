# Day 8 — Kubernetes Fundamentals

## Learning Goal

Day 8 的目标是从 Docker 的单容器运行模型，进入 Kubernetes 的容器编排模型，并通过本地 `kind` 集群亲手验证：

- Node / Pod / Container 的关系
- Kubernetes Control Plane 的基本职责
- Deployment / ReplicaSet / Pod 的关系
- Desired State 与 Reconciliation
- Labels / Selectors
- Service / ClusterIP / EndpointSlice
- Pod failure 后 Kubernetes 如何自动恢复
- 本地 Docker image 与 kind Node image store 的区别

---

## 1. Why Kubernetes?

Docker 可以运行 container，但当系统开始有大量 replicas 和多台机器时，需要解决：

- Container crash recovery
- Replica management
- Scheduling
- Load distribution
- Node failure
- Rolling updates
- Service discovery

Kubernetes 的核心目标：

> 管理大量 containers across machines，并持续让系统接近我们声明的 desired state。

---

## 2. Core Hierarchy

```text
Cluster
  └── Node
       └── Pod
            └── Container
                 ↑
               Image
```

### Node

Node 可以理解为 Kubernetes 中提供计算资源的机器。

生产环境中通常是：

```text
Physical Server / VM
        ↓
Kubernetes Node
```

CPU、RAM、GPU 等资源属于 Node。

### Pod

Pod 是 Kubernetes 最小的 deployable unit。

通常对于 3 个独立 inference replicas：

```text
Pod A
 └── inference container

Pod B
 └── inference container

Pod C
 └── inference container
```

而不是：

```text
One Pod
 ├── inference replica 1
 ├── inference replica 2
 └── inference replica 3
```

多个 containers 放在同一个 Pod 中，通常意味着它们是 tightly coupled，例如 sidecar。

### Container vs Image

Image 是创建 Container 使用的模板。

```text
Image
  ↓
Container
```

---

## 3. kind — Kubernetes IN Docker

本地环境使用：

```bash
kind
```

`kind` = Kubernetes IN Docker。

它不是“把 Docker 转成 Kubernetes”，而是使用 Docker containers 作为 Kubernetes Nodes，从而在本地创建 Kubernetes cluster。

创建 cluster：

```bash
kind create cluster --name learning-infra
```

检查：

```bash
kubectl config current-context
kubectl get nodes
```

本次环境：

```text
context:
kind-learning-infra

node:
learning-infra-control-plane
```

Docker 中也可以看到这个 Node：

```bash
docker ps
```

mental model：

```text
Mac
 └── Docker
      └── kind Node container
           └── Kubernetes
                └── Pods
```

---

## 4. Control Plane

Day 8 接触到的主要组件：

### kube-apiserver

Kubernetes Control Plane 的 API 入口。

```text
kubectl
   ↓
kube-apiserver
```

注意：

> API Server ≠ Kubernetes Service

API Server 管理 cluster/control-plane 请求。

Service 管理 application traffic。

### kube-scheduler

负责决定：

> 新 Pod 应该运行在哪个 Node？

```text
New Pod
   ↓
Scheduler
   ↓
Choose Node
```

### kube-controller-manager

运行各种 reconciliation/control loops。

核心思想：

```text
Desired State
     ↓
Observe Actual State
     ↓
Compare
     ↓
Reconcile
     ↓
Repeat
```

### etcd

保存 Kubernetes cluster state。

---

## 5. First Pod

使用之前构建的 image：

```text
ai-infra-api:v1
```

创建 Pod：

```bash
kubectl run inference-api \
  --image=ai-infra-api:v1 \
  --port=8000
```

出现：

```text
ErrImagePull
ImagePullBackOff
```

查看原因：

```bash
kubectl describe pod inference-api
```

Kubernetes 尝试：

```text
docker.io/library/ai-infra-api:v1
```

但 image 明明可以通过：

```bash
docker images
```

在 Mac 上看到。

---

## 6. Why ErrImagePull?

关键原因：

```text
Mac Docker Image Store
        ≠
kind Node Image Store
```

本地 Mac Docker 中存在：

```text
ai-infra-api:v1
```

并不代表 Kubernetes Node 可以直接看到。

Node 找不到 image 后，会尝试从 registry（例如 Docker Hub）pull。

解决：

```bash
kind load docker-image ai-infra-api:v1 --name learning-infra
```

这一步把 image 加载到 kind Node 的 container runtime。

之后 Pod 自动恢复：

```text
ErrImagePull
     ↓
image becomes available
     ↓
Kubernetes retries
     ↓
Running
```

---

## 7. Pod Networking

查看 Pod：

```bash
kubectl get pod inference-api -o wide
```

得到 Pod IP，例如：

```text
10.244.0.5
```

但是：

```bash
curl localhost:8000/health
```

失败。

原因：

```text
Mac localhost
    ≠
Pod network
```

`containerPort: 8000` 也不会自动把 Pod 暴露到 Mac。

开发/debug 时可以：

```bash
kubectl port-forward pod/inference-api 8080:8000
```

然后：

```bash
curl localhost:8080/health
```

请求链：

```text
Mac localhost:8080
       ↓
kubectl port-forward
       ↓
Pod :8000
       ↓
FastAPI
```

---

## 8. Bare Pod vs Deployment

删除 bare Pod：

```bash
kubectl delete pod inference-api
```

结果：

```text
Pod disappears
and does NOT come back
```

原因：

> 没有 controller 声明这个 Pod 应该持续存在。

这引出了 Deployment。

---

## 9. Deployment

Day 8 创建：

```yaml
apiVersion: apps/v1
kind: Deployment

metadata:
  name: inference-api

spec:
  replicas: 3

  selector:
    matchLabels:
      app: inference-api

  template:
    metadata:
      labels:
        app: inference-api

    spec:
      containers:
        - name: inference-api
          image: ai-infra-api:v1
          ports:
            - containerPort: 8000
```

应用：

```bash
kubectl apply -f deployment.yaml
```

检查：

```bash
kubectl get deployments
kubectl get replicasets
kubectl get pods -o wide
```

关系：

```text
Deployment
    ↓
ReplicaSet
    ↓
Pod
Pod
Pod
```

---

## 10. Desired State

配置：

```yaml
replicas: 3
```

并不是：

> 创建 3 个 Pods 一次。

而是：

> 持续保持 3 个 Pods。

因此：

```text
Desired = 3
Actual  = 3
```

系统稳定。

如果删除一个：

```text
Desired = 3
Actual  = 2
```

controller 发现 mismatch：

```text
Desired 3
   ↓
Actual 2
   ↓
Reconciliation
   ↓
Create new Pod
   ↓
Actual 3
```

实际实验中删除旧 Pod 后，ReplicaSet 自动创建了新的 Pod。

这是 Kubernetes 最重要的 mental model 之一：

> Kubernetes 是 declarative system。

Docker：

```text
Run this container.
```

Kubernetes：

```text
Keep my system looking like this.
```

---

## 11. Labels and Selectors

Pod：

```yaml
labels:
  app: inference-api
```

Service：

```yaml
selector:
  app: inference-api
```

含义：

```text
Service
   ↓ selector
find Pods where:
app = inference-api
   ↓
Pod A
Pod B
Pod C
```

重要：

> Selector 不是帮助 Node 找 Pods。

它用于匹配具有特定 labels 的 Kubernetes objects。

在 Service 场景中，它决定哪些 Pods 是 Service backends。

---

## 12. Kubernetes Service

创建：

```yaml
apiVersion: v1
kind: Service

metadata:
  name: inference-api-service

spec:
  selector:
    app: inference-api

  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
```

检查：

```bash
kubectl get services
```

得到类似：

```text
inference-api-service
TYPE: ClusterIP
CLUSTER-IP: 10.96.119.62
PORT: 80
```

### port

```yaml
port: 80
```

Service 接收 traffic 的端口。

### targetPort

```yaml
targetPort: 8000
```

Service 将 traffic 转发到 backend Pod 的目标端口。

因此：

```text
Client
   ↓
Service :80
   ↓
Pod :8000
   ↓
FastAPI
```

---

## 13. ClusterIP

当前 Service 类型：

```text
ClusterIP
```

意味着它默认用于 cluster 内部通信。

它并不是：

```text
Internet → Service
```

而是：

```text
Pod / workload inside cluster
        ↓
Service
        ↓
backend Pods
```

以后会继续学习：

- NodePort
- LoadBalancer
- Ingress / Gateway

---

## 14. EndpointSlice

检查：

```bash
kubectl get endpointslices
```

观察到：

```text
inference-api-service
ENDPOINTS:
10.244.0.6
10.244.0.8
10.244.0.9
PORT:
8000
```

这说明 Service selector 找到了对应的 backend Pods。

mental model：

```text
Service
10.96.119.62:80
       ↓
EndpointSlice
       ↓
10.244.0.6:8000
10.244.0.8:8000
10.244.0.9:8000
```

Pod IP 可以变化，但客户端不需要直接依赖 Pod IP。

---

## 15. Service DNS Test

创建测试 Pod：

```bash
kubectl run curl-test \
  --image=curlimages/curl \
  --restart=Never \
  --command -- sleep 3600
```

从 cluster 内部请求：

```bash
kubectl exec curl-test -- \
  curl -v http://inference-api-service/health
```

结果：

```text
Host inference-api-service:80 was resolved.
IPv4: 10.96.119.62

HTTP/1.1 200 OK

{"status":"ok"}
```

完整请求链：

```text
curl-test Pod
      ↓
Kubernetes DNS
      ↓
inference-api-service
      ↓
10.96.119.62:80
      ↓
Service routing
      ↓
one backend Pod :8000
      ↓
Uvicorn / FastAPI
      ↓
GET /health
      ↓
200 OK
```

---

## 16. Failure Recovery Experiment

删除其中一个 inference Pod。

删除前：

```text
Pod A → 10.244.0.6
Pod B → 10.244.0.8
Pod C → 10.244.0.9
```

删除 Pod 后：

```text
ReplicaSet
   ↓
detects Actual < Desired
   ↓
creates replacement Pod
```

新的 Pod 可能得到：

```text
new Pod name
new Pod IP
```

与此同时 EndpointSlice 自动更新。

但是：

```text
inference-api-service
```

保持稳定。

再次：

```bash
kubectl exec curl-test -- \
  curl http://inference-api-service/health
```

仍然成功：

```json
{"status":"ok"}
```

最终验证：

```text
Pod dies
   ↓
ReplicaSet detects actual < desired
   ↓
new Pod + new IP
   ↓
EndpointSlice updates
   ↓
Service stays stable
   ↓
Client still receives 200 OK
```

---

# 17. Deployment vs Service

这是 Day 8 最需要避免混淆的两个组件。

## Deployment

负责：

```text
Desired replica count
       ↓
Maintain Pods
       ↓
Replace failed Pods
```

例如：

```yaml
replicas: 3
```

Deployment/ReplicaSet 会持续维持 3 个 Pods。

## Service

负责：

```text
Stable endpoint
      +
Find matching backend Pods
      +
Route traffic
```

Service **不会创建 Pod**。

---

# 18. What Deployment Does NOT Do

假设：

```text
replicas = 3

CPU = 100%
Queue ↑
Latency ↑
```

Deployment 不会因为 CPU 高就自动：

```text
3 → 6
```

它只知道：

```text
Desired replicas = 3
```

所以继续维持 3。

自动根据 metrics 调整 replicas 的组件是：

```text
HPA
Horizontal Pod Autoscaler
```

未来 mental model：

```text
Metrics
   ↓
HPA
   ↓
replicas 3 → 6
   ↓
Deployment / ReplicaSet
   ↓
more Pods
   ↓
Service routes traffic
```

HPA 尚未正式学习。

---

# 19. Day 8 Final Mental Model

```text
                    Kubernetes Cluster

                         Control Plane
                              │
             ┌────────────────┼────────────────┐
             │                │                │
         API Server       Scheduler       Controllers
                                               │
                                         desired state
                                               │
                                               ▼
                                          Deployment
                                               │
                                               ▼
                                          ReplicaSet
                                               │
                              ┌────────────────┼────────────────┐
                              ▼                ▼                ▼
                            Pod A            Pod B            Pod C
                         10.244.x.x       10.244.x.x       10.244.x.x
                              ▲                ▲                ▲
                              └────────────────┼────────────────┘
                                               │
                                            Service
                                               │
                                      Stable ClusterIP
                                               │
                                             Client
```

---

# 20. Backend Engineering Mapping

可以和熟悉的 backend/distributed-system concepts 做如下映射：

| Kubernetes | Backend Mental Model |
|---|---|
| Node | Server / VM |
| Pod | Deployable application instance |
| Container | Running isolated process |
| Image | Immutable application template |
| Deployment | Desired replica configuration |
| ReplicaSet | Replica-count reconciliation |
| Service | Stable service endpoint / routing layer |
| Label | Instance metadata |
| Selector | Backend membership query |
| Scheduler | Placement decision |
| Controller | Reconciliation/control loop |

注意这些是帮助理解的类比，不代表组件完全等价。

---

# 21. Key Takeaways

Day 8 最重要的不是记 Kubernetes YAML，而是形成以下模型：

### Model 1 — Hierarchy

```text
Node
 └── Pod
      └── Container
           ↑
         Image
```

### Model 2 — Declarative Control

```text
Desired State
     ↓
Actual State
     ↓
Compare
     ↓
Reconcile
```

### Model 3 — Deployment

```text
Deployment
   ↓
ReplicaSet
   ↓
maintains N Pods
```

### Model 4 — Service

```text
Stable Service
      ↓
selector
      ↓
dynamic Pods
```

### Model 5 — Failure Recovery

```text
Pod IP changes
     ≠
Client endpoint changes
```

Clients communicate with Service rather than tracking individual Pod identities.

---

# Day 8 Status

**Completed**

Hands-on tasks completed:

- Created local Kubernetes cluster using kind
- Inspected Kubernetes system Pods
- Created first Pod
- Debugged `ErrImagePull`
- Loaded local Docker image into kind
- Tested Pod using `kubectl port-forward`
- Created Deployment with 3 replicas
- Deleted Pod and observed reconciliation
- Created ClusterIP Service
- Inspected Service endpoints / EndpointSlice
- Tested Kubernetes DNS
- Sent request through Service to FastAPI
- Deleted backend Pod
- Observed replacement Pod and EndpointSlice update
- Confirmed Service remained available

## Next

**Day 9 — Kubernetes Resource Management**

Planned connection:

```text
Docker cgroups
      ↓
Kubernetes requests / limits
      ↓
Scheduler capacity decisions
      ↓
CPU / memory constraints
      ↓
Pending / Insufficient resources
      ↓
later: HPA + inference autoscaling
```

This will connect directly to the earlier Docker CPU-limit experiments and eventually to LLM inference capacity planning.

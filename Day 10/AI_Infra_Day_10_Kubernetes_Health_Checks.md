# AI Infrastructure — Day 10: Kubernetes Health Checks & Self-Healing

**Status:** Completed  
**Environment:** macOS, kind cluster `learning-infra`, Kubernetes v1.37.0  
**Focus:** Startup, Readiness, Liveness Probes; EndpointSlice; container restart vs Deployment rollout

## 1. Day 9 Recap

- **CPU requests** are used by the scheduler for placement. A Pod with CPU request `1` can be scheduled on a node with `2` CPU allocatable remaining even if its CPU limit is `10`; that limit is not a guarantee.
- **CPU throttling** is a runtime cgroup mechanism, not the same as scheduling failure (`Pending`, `Insufficient cpu`).
- **Memory limits** are enforced at runtime. Exceeding them can lead to `OOMKilled`; `Exit Code 137` alone does not prove OOM.
- **Pod phase**, **container state**, and **readiness** are distinct. `Running` does not necessarily mean healthy.

## 2. Three Probes

| Probe | Question | On repeated failure | Typical LLM serving use |
|---|---|---|---|
| Startup | Has initialization finished? | Restart container after failure threshold | Model weight loading, CUDA initialization |
| Readiness | Can this instance accept traffic now? | Mark Pod NotReady; exclude from normal Service routing | Temporarily unavailable worker |
| Liveness | Is the process stuck and in need of restart? | Restart container after failure threshold | Unrecoverable deadlock |

**Key distinction:** Readiness manages traffic; Liveness manages process recovery. A successful Liveness check does **not** imply Readiness.

When a Startup Probe is configured, Liveness and Readiness checks are held back until startup succeeds. Avoid using Liveness to punish temporary overload: a restart interrupts in-flight requests, discards in-memory KV cache, and may require expensive model reloads.

## 3. Lab 1 — Startup Probe

Created a ConfigMap containing a Python HTTP server and a Pod `startup-demo`. The `/startup` endpoint returned HTTP `503` for the first 30 seconds, then HTTP `200`.

```yaml
startupProbe:
  httpGet:
    path: /startup
    port: 8000
  periodSeconds: 5
  failureThreshold: 10
```

Commands:

```bash
kubectl apply -f startup-demo.yaml
kubectl get pod startup-demo -w
kubectl describe pod startup-demo
```

**Observed:**

```text
Warning  Unhealthy  ... (x6) Startup probe failed: HTTP probe failed with statuscode: 503
State: Running
Ready: True
Restart Count: 0
```

**Interpretation:** Temporary startup failures were tolerated; the process was not restarted, and the Pod became Ready once startup succeeded. The nominal `5 × 10 = 50` seconds is an approximate tolerance window, not an exact timer.

## 4. Lab 2 — Readiness Probe and EndpointSlice

Created `readiness-demo.yaml` containing a ConfigMap with a Python server, a one-replica Deployment, and a ClusterIP Service. The server's `/ready` endpoint checks for `/tmp/not-ready`:

```python
if self.path == "/ready":
    status = 503 if os.path.exists("/tmp/not-ready") else 200
```

Probe:

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  periodSeconds: 2
  failureThreshold: 1
```

Initial deployment:

```bash
kubectl apply -f readiness-demo.yaml
kubectl rollout status deployment/readiness-demo
kubectl get pods -l app=readiness-demo
kubectl get endpoints readiness-demo
```

**Observed initial state:** `1/1 Running`, `RESTARTS=0`, endpoint `10.244.0.19:8000`.

Triggered Readiness failure:

```bash
kubectl exec deploy/readiness-demo -- touch /tmp/not-ready
kubectl get pods -l app=readiness-demo
kubectl get endpointslices -l kubernetes.io/service-name=readiness-demo -o yaml
```

**Observed:**

```text
READY  STATUS   RESTARTS
0/1    Running  0
```

EndpointSlice:

```yaml
addresses:
  - 10.244.0.19
conditions:
  ready: false
  serving: false
  terminating: false
```

**Interpretation:** The Pod IP remained in the EndpointSlice, but `ready: false` prevented normal Service routing to that endpoint. The container kept running and was not restarted. Existing connections are not necessarily terminated immediately.

Restored readiness:

```bash
kubectl exec deploy/readiness-demo -- rm /tmp/not-ready
kubectl get pods -l app=readiness-demo
kubectl get endpointslices -l kubernetes.io/service-name=readiness-demo \
  -o jsonpath='{.items[0].endpoints[0].conditions.ready}{"\n"}'
```

**Observed:** Recovery succeeded: `READY=1/1`, EndpointSlice `ready=true`, no restart.

**Note:** The older `v1 Endpoints` API is deprecated in newer Kubernetes releases; prefer `EndpointSlice` (`discovery.k8s.io/v1`).

## 5. Lab 3 — Liveness Probe

Added to the existing Deployment container:

```yaml
livenessProbe:
  exec:
    command:
      - sh
      - -c
      - test ! -f /tmp/unhealthy
  periodSeconds: 2
  failureThreshold: 3
```

### Shell command explained

```bash
sh -c 'test ! -f /tmp/unhealthy'
```

- `sh -c` executes the shell command string.
- `test -f PATH` succeeds if PATH is a regular file.
- `!` negates the test.
- If the file is **absent**, exit code `0` means probe success.
- If the file **exists**, exit code `1` means probe failure.

The file is a **synthetic failure marker**, not a real Python process crash.

### Applying the Deployment change

Editing a local YAML file does **not** change Kubernetes state. Run:

```bash
kubectl apply -f readiness-demo.yaml
kubectl rollout status deployment/readiness-demo
kubectl describe pod -l app=readiness-demo
```

Changing the Deployment Pod template triggered a rolling update:

| | Old Pod | New Pod |
|---|---|---|
| Name | `readiness-demo-57b88bb649-8p9mc` | `readiness-demo-fff8f44bd-nl886` |
| IP | `10.244.0.19` | `10.244.0.20` |
| Liveness | Not configured | Configured |

The old Pod's `Exit Code 137` during termination did not establish OOM; no `OOMKilled` reason was shown.

### Triggering the failure

```bash
kubectl exec deploy/readiness-demo -- touch /tmp/unhealthy
kubectl get pods -l app=readiness-demo
kubectl describe pod readiness-demo-fff8f44bd-nl886
```

**Observed:**

```text
Restart Count: 1
Last State: Terminated
Reason: Error
Exit Code: 137
Warning Unhealthy ... (x3) Liveness probe failed
Normal  Killing ... Container app failed liveness probe, will be restarted
State: Running
Ready: True
```

**Interpretation:** This restart was triggered by the failed Liveness Probe, as confirmed by the kubelet `Killing` event, **not** by OOM. The Pod retained IP `10.244.0.20`; only the container was recreated. The `/tmp/unhealthy` marker was in the container's writable filesystem, so it disappeared with container recreation. If stored on a persistent volume, the failure marker could survive restart.

The Deployment Pod's restart policy is `Always` (default and required for Deployment Pods). Readiness briefly failed with `connection refused` while the replacement Python process was starting, then recovered.

## 6. Core Kubernetes Mechanisms

```text
Application cannot receive new traffic
  -> Readiness fails
  -> Pod NotReady
  -> EndpointSlice ready=false
  -> Service avoids endpoint for new traffic
  -> No container restart

Application needs process recovery
  -> Liveness fails repeatedly
  -> kubelet restarts container
  -> In-memory state lost
  -> Same Pod, generally same Pod IP

Deployment Pod template changes
  -> Deployment creates new ReplicaSet/Pods
  -> Rolling Update
  -> New Pods may have new IPs
```

These operate at different levels:

1. **Traffic:** Readiness + Service/EndpointSlice.
2. **Container:** kubelet + Liveness.
3. **Pod replacement:** Deployment + ReplicaSet.

## 7. LLM Inference Engineering Takeaways

- Use **Startup** to allow slow model loading and CUDA initialization without premature Liveness restarts.
- Use **Readiness** for temporary inability to accept Service traffic; distinguish this from application death.
- Use **Liveness** only for failures where restarting is appropriate, not simply because GPU utilization or queue length is high.
- Restarts may interrupt in-flight requests, lose KV cache, and require model reloads; excessive restarts can worsen an overload incident.
- Consider application-level admission control and routing for more granular overload handling than marking an entire Pod NotReady.
- A process being `Running` is not equivalent to being `Ready`.

## 8. Mastery Check — Answers and Corrections

1. **90-second model load, Liveness every 5 seconds, threshold 3, no Startup:** repeated restarts may prevent the application from ever finishing initialization.
2. **`Running`, `READY=0/1`, `RESTARTS=0`:** consistent with Readiness failure; the container can remain alive without being eligible for traffic. This is not a unique diagnosis without checking probes/events.
3. **GPU 100%, request queue growing:** do not automatically fail Liveness; investigate whether overload is temporary and whether requests still progress. Admission control or capacity scaling may be more appropriate.
4. **Why IP stays the same after Liveness restart but changes during rollout:** Liveness recreates the container within the same Pod; rollout creates a new Pod.

## 9. Useful Commands

```bash
kubectl get pods -l app=readiness-demo
kubectl describe pod -l app=readiness-demo
kubectl get endpointslices -l kubernetes.io/service-name=readiness-demo -o yaml
kubectl rollout status deployment/readiness-demo
kubectl exec deploy/readiness-demo -- touch /tmp/not-ready
kubectl exec deploy/readiness-demo -- rm /tmp/not-ready
kubectl exec deploy/readiness-demo -- touch /tmp/unhealthy
```

Optional cleanup when finished:

```bash
kubectl delete -f startup-demo.yaml
kubectl delete -f readiness-demo.yaml
```

## 10. Next: Day 11 — Kubernetes Networking

Explore **Service DNS, ClusterIP, Pod IP, kube-proxy, and Pod-to-Pod communication**. Continue using multiple replicas of the HTTP inference-worker simulator to understand request routing.

**Project milestone:** Formal construction of the **Distributed LLM Inference Platform** has not started yet; create its separate GitHub repository when that project phase begins.

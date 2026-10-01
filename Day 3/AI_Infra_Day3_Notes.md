# Day 3 --- Networking Fundamentals 总结

## 1. 核心 Request Path

``` text
Client
  ↓
TCP Connection
  ↓
Server NIC
  ↓
Kernel TCP/IP Stack
  ↓
Socket Receive Buffer
  ↓
Socket / FD becomes Ready
  ↓
epoll / kqueue
  ↓
Event Loop
  ↓
recv()/read()
  ↓
HTTP Parser
  ↓
Request Queue
  ↓
Inference Scheduler
  ↓
GPU
```

Day 3 的目标：理解一个 Request 如何真正从 Client 进入 Server Process。

## 2. IP Address vs Port

``` text
IP Address → 找目标 Host / Network Interface
Port       → 找目标 Host 上的 Network Service Endpoint
```

例如 `10.0.0.20:8000`：

``` text
10.0.0.20 → Server
8000      → TCP Port
```

同一台机器可以同时运行：

``` text
:8000 → vLLM
:9000 → Metrics Server
:5432 → PostgreSQL
```

## 3. Port ≠ Connection

一个 Port 可以同时服务很多 TCP Connections。

``` text
Client A 192.168.1.5:51001 → 10.0.0.20:8000
Client B 192.168.1.6:62002 → 10.0.0.20:8000
```

TCP Connection 可用 4-tuple 区分：

``` text
Source IP
Source Port
Destination IP
Destination Port
```

所以：

``` text
Port ≠ Connection
```

## 4. TCP Layer vs Application Layer

都连接 `:8000`：

``` text
Client A → POST /generate
Client B → GET /health
```

可以做不同事情，因为：

``` text
TCP / Port
→ Transport Connection

HTTP / Application Layer
→ Method / Path / Headers / Body
```

## 5. Socket

Socket 可以理解为：

> Application 与 OS Networking Stack 之间的 Network Communication
> Endpoint。

经典 TCP Server 生命周期：

``` text
socket()
   ↓
bind()
   ↓
listen()
   ↓
accept()
   ↓
recv()/send()
```

-   `socket()`：创建 Socket。
-   `bind()`：绑定 Local IP + Port。
-   `listen()`：变成 Listening Socket，准备接受 Incoming Connections。
-   `accept()`：接受 Connection，得到 Connected Socket。
-   `recv()`：从 Connected Socket 读取 Bytes。

核心：

``` text
accept → Connection
recv   → Bytes
```

## 6. Listening Socket vs Connected Socket

``` text
             Listening Socket :8000
                    │
          ┌─────────┼─────────┐
       accept     accept     accept
          ↓         ↓          ↓
       Conn A     Conn B      Conn C
          ↕         ↕          ↕
       Client A  Client B   Client C
```

Listening Socket 接新 Connections；Connected Socket 与某个具体 Client
通信。

## 7. PID vs FD

### PID --- Process ID

``` text
PID → 标识哪个 Process
```

### FD --- File Descriptor

FD 是某个 Process 内部引用 OS-managed resource 的整数编号。

``` text
PID 1001
├── FD 0 → stdin
├── FD 1 → stdout
├── FD 2 → stderr
├── FD 3 → Listening Socket
├── FD 4 → Client A Socket
└── FD 5 → Client B Socket
```

关系：

``` text
PID
 ↓
Process FD Table
 ↓
FD
 ↓
OS Resource
```

FD 是 Process-local，不同 Process 可以同时拥有 `FD 3`。

``` text
FD ≠ PID
FD ≠ Connection ID
```

FD 被关闭后，编号也可以被重新利用。

## 8. Blocking recv()

``` python
data = conn.recv(1024)
```

如果没有 Data：

``` text
Thread
  ↓
recv(FD)
  ↓
Kernel：没有数据
  ↓
Thread → BLOCKED / WAITING
  ↓
Scheduler 不再给它 CPU
```

数据到达后：

``` text
Socket becomes Ready
       ↓
Thread → Runnable
       ↓
Scheduler
       ↓
Thread 获得 CPU
       ↓
recv() returns
```

重要：

> Blocking Thread ≠ CPU Busy Waiting。

普通 blocking `recv(fd5)` 的 Thread 也不会自己去检查 FD6、FD7、FD8。

## 9. Single-thread Server 的问题

``` python
while True:
    conn, addr = server.accept()
    data = conn.recv(1024)
    process(data)
```

如果 Client A connect 后不发送 Data：

``` text
accept Client A
↓
recv(Client A)
↓
BLOCKED
```

CPU 可以执行其他 Process / Thread，但这个 Server 没有第二个 Thread
回去执行下一次 `accept()`。

``` text
CPU 有空
≠
Application 正在处理其他 Client
```

## 10. One Connection per Thread 的问题

``` text
100,000 Connections
→ 100,000 Threads
```

可能造成：

``` text
Scheduler Overhead ↑
Context Switching ↑
Stack Memory ↑
Cache Disruption ↑
```

所以：

> More Threads ≠ Better Scalability。

## 11. I/O Multiplexing

目标：

``` text
少量 Threads
     ↓
管理大量 Socket FDs
```

让 Kernel 告诉 Application 哪些 FDs Ready，而不是 Application
不断轮询所有 FDs。

这就是 I/O Multiplexing。

常见实现：

``` text
Linux       → epoll
macOS / BSD → kqueue
```

## 12. epoll / kqueue + Event Loop

``` text
Event Loop Thread
       ↓
epoll_wait() / kevent()
       ↓
Thread BLOCKED
       ↓
Kernel 监控注册的 FDs
       ↓
FD 6、FD 8 Ready
       ↓
Kernel 唤醒 Thread
       ↓
返回 Ready FDs
       ↓
Event Loop 处理 FD 6、FD 8
```

重点：

> Thread 本身不是不断 Loop 所有 FDs。

而是：

> Kernel 监控 FD readiness，Thread 醒来后处理 Ready FDs。

简化 Event Loop：

``` python
while True:
    ready_fds = wait_for_events()

    for fd in ready_fds:
        handle(fd)
```

## 13. Event Loop 不能被 CPU-heavy Task 卡住

一个 Event Loop Thread 管理很多 Connections 时，如果某个 handler：

``` text
CPU-heavy Task → 10 seconds
```

则：

``` text
Event Loop Thread
      ↓
CPU-heavy Task
████████████ 10 sec
      ↓
无法处理其他 Ready FDs
      ↓
Latency ↑
```

因此：

``` text
Network Event Loop
      ↓
Request
      ↓
Request Queue
      ↓
Inference Scheduler / Worker
      ↓
GPU
```

## 14. TCP 基础

TCP 可以先记：

> Connection-oriented + Reliable + Ordered Byte Stream

简化 3-way handshake：

``` text
Client                 Server

SYN  ─────────────────→
     ←────────────── SYN-ACK
ACK  ─────────────────→

        Connected
```

TCP 给 Application 提供可靠、有序的 Byte Stream。

但：

> TCP 是 Byte Stream，不是 Message Stream。

例如：

``` python
send(b"HELLO")
send(b"WORLD")
```

Server 不保证两次 `recv()` 正好分别得到 `HELLO` 和 `WORLD`。

可能看到：

``` text
HELLOWORLD
```

或者：

``` text
HEL
LOWORLD
```

TCP 保证的是 Byte Sequence，不保证 Application Message Boundary。

## 15. HTTP 在 TCP 上面

``` text
Application Layer
HTTP / gRPC
      ↓
Transport Layer
TCP
      ↓
Network Layer
IP
```

HTTP 负责解释：

``` text
Method
Path
Headers
Body
```

TCP 负责 Reliable Ordered Byte Stream。

## 16. NIC → Kernel → Socket → epoll

``` text
Client
  ↓
Network
  ↓
Server NIC
  ↓
Kernel TCP/IP Stack
  ↓
找到对应 TCP Socket
  ↓
Socket Receive Buffer
  ↓
Socket becomes Readable
  ↓
FD becomes Ready
  ↓
epoll / kqueue reports Ready FD
  ↓
Event Loop wakes
  ↓
recv()/read()
  ↓
Application Memory
```

`epoll/kqueue` 不是负责传输 Data，而是帮助 Application 等待和发现 FD
readiness。

## 17. 今日实际 Lab

Server 使用：

``` python
import socket
import os

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(("127.0.0.1", 8000))
server.listen()

print("PID:", os.getpid())

while True:
    conn, addr = server.accept()

    print("Connected:", addr)
    print("Before recv")

    data = conn.recv(1024)

    print("After recv")
    print("Received:", data.decode())

    conn.sendall(b"Hello from server\n")
    conn.close()
```

Client：

``` bash
nc 127.0.0.1 8000
```

观察：

``` bash
lsof -nP -iTCP:8000
```

## 18. 实际 PID / FD 观察

实际看到：

``` text
Python PID 26943 FD 3
TCP 127.0.0.1:8000 (LISTEN)

Python PID 26943 FD 4
TCP 127.0.0.1:8000->127.0.0.1:54338 (ESTABLISHED)

nc PID 26971 FD 3
TCP 127.0.0.1:54338->127.0.0.1:8000 (ESTABLISHED)
```

对应：

``` text
Python Server
PID 26943
├── FD 3 → Listening Socket :8000
└── FD 4 → Connected Socket ↔ Client A :54338
```

这也验证了不同 Process 可以同时有 `FD 3`。

## 19. Client Source Port

运行：

``` bash
nc 127.0.0.1 8000
```

Client OS 自动选择了临时 Source Port，例如：

``` text
54338
```

所以 4-tuple：

``` text
Source IP        = 127.0.0.1
Source Port      = 54338
Destination IP   = 127.0.0.1
Destination Port = 8000
```

## 20. 最重要的 Lab 发现：ESTABLISHED ≠ accept()

第二个 Client 连接后实际看到：

``` text
Python PID 26943 FD 3
127.0.0.1:8000 LISTEN

Python PID 26943 FD 4
127.0.0.1:8000 → 127.0.0.1:54338 ESTABLISHED

nc PID 26971
127.0.0.1:54338 → 127.0.0.1:8000 ESTABLISHED

nc PID 27070
127.0.0.1:54375 → 127.0.0.1:8000 ESTABLISHED
```

关键：

``` text
Client B TCP = ESTABLISHED

但是

Python 没有新的 Connected FD
```

原因：

``` text
Python Thread
    ↓
recv(FD 4)
    ↓
等待 Client A
    ↓
BLOCKED
```

Python 尚未执行第二次 `accept()`，但 Kernel TCP Stack 已经可以完成
Client B 的 TCP Connection。

因此：

``` text
TCP Connection Established
≠
Application 已经 accept()
```

## 21. Kernel 可以先 Buffer Data

即使 Python 仍 blocked 在 Client A：

``` text
Client B
   ↓
Network Data
   ↓
Kernel
   ↓
Socket Buffer
   ↓
等待 Application accept/read
```

之后：

``` text
Client A data arrives
↓
recv(Client A) returns
↓
close Client A
↓
while loop
↓
accept()
↓
拿到 Client B
↓
recv()
↓
读取已经 Buffer 的 Data
```

## 22. AI Infra 完整 Request Path

``` text
Client
  ↓
TCP Connection
  ↓
Server NIC
  ↓
Kernel TCP/IP
  ↓
Socket Receive Buffer
  ↓
Socket FD Ready
  ↓
epoll / kqueue
  ↓
Event Loop
  ↓
recv()/read()
  ↓
HTTP Parser
  ↓
Request Object
  ↓
Request Queue
  ↓
Inference Scheduler
  ↓
Batching
  ↓
GPU
```

## 23. GPU Low Utilization 不一定是 GPU 问题

例如：

``` text
GPU Utilization = 30%
Request Queue    = Large
Event Loop CPU   = 100%
```

不能直接：

``` text
GPU Low → Add GPU
```

可能是：

``` text
Event Loop / CPU Bottleneck
          ↓
Requests 无法足够快进入 Inference Pipeline
          ↓
GPU 被 Starved
          ↓
GPU Utilization Low
```

但 `Event Loop CPU = 100%` 也只说明它很忙，不直接说明原因。

可能是：

``` text
大量 Ready FDs
HTTP Parsing
Serialization
CPU-heavy Handler
Busy Loop
其他 Expensive Work
```

仍然需要：

``` text
Measure → Profile → Locate Bottleneck
```

# Day 3 核心区别

``` text
Port ≠ Connection
PID ≠ FD
FD ≠ Connection ID
Listening Socket ≠ Connected Socket
TCP ESTABLISHED ≠ Application accept()
accept() ≠ recv()
Blocking recv() ≠ CPU Busy Waiting
TCP Byte Stream ≠ Application Message
Network Connection Count ≠ Request Queue Size
High CPU Utilization ≠ 知道 CPU 为什么忙
```

# Day 3 Mental Model

``` text
Client
 ↓
TCP
 ↓
Kernel
 ↓
Socket
 ↓
FD
 ↓
Readiness
 ↓
epoll / kqueue
 ↓
Event Loop
 ↓
Application
 ↓
Queue
 ↓
Scheduler
 ↓
GPU
```

性能分析继续遵循：

``` text
Metrics
   ↓
Locate Bottleneck
   ↓
Understand WHY
   ↓
Optimize
   ↓
Measure Again
```

## 今日关键词

`IP` · `Port` · `TCP` · `4-tuple` · `Socket` · `Listening Socket` ·
`Connected Socket` · `PID` · `File Descriptor` · `accept()` · `recv()` ·
`Blocking I/O` · `Socket Buffer` · `I/O Multiplexing` · `epoll` ·
`kqueue` · `Event Loop` · `NIC` · `TCP/IP Stack` · `HTTP` ·
`Application Layer` · `ESTABLISHED` · `Accept Queue`

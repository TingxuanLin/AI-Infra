import socket
import os

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.bind(("127.0.0.1", 8000))
server.listen()

print("PID:", os.getpid())
print("Server is listening on port 8000...")

while True:
    print("Waiting for a connection...")

    conn, addr = server.accept()

    print("Connection established with:", addr)
    print("Before reveiving data...")

    data = conn.recv(1024)

    print("Data received:", data.decode())

    conn.sendall(b"Hello from the server!")
    conn.close()
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

start_time = time.monotonic()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        elapsed = time.monotonic() - start_time

        if self.path == "/startup":
            status = 200 if elapsed >= 30 else 503
        else:
            status = 200

        self.send_response(status)
        self.end_headers()
        self.wfile.write(f"Elapsed: {elapsed:.1f}s".encode())

HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
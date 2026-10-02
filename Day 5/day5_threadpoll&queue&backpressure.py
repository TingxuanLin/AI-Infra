from concurrent.futures import ThreadPoolExecutor
import time
import threading

MAX_WORKERS = 3
QUEUE_SIZE = 5

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
capacity = threading.Semaphore(QUEUE_SIZE + MAX_WORKERS)

def handle_request(request_id):
    print(f"Handling request {request_id} in thread {threading.current_thread().name}")
    time.sleep(2)
    print(f"Finished request {request_id}")


def submit_request(request_id):
    acquired = capacity.acquire(blocking=False)

    if not acquired:
        print(f"Request {request_id} rejected due to full capacity")
        return

    future = executor.submit(handle_request, request_id)

    future.add_done_callback(lambda f: capacity.release())

for i in range(20):
    submit_request(i)

executor.shutdown(wait=True)
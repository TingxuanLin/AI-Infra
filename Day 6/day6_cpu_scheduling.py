from concurrent.futures import ProcessPoolExecutor
import time

TOTAL_TASKS = 32

def cpu_work(worker_id):
    x = 0

    for i in range(20_000_000):
        x += i * i

    return worker_id

def run_test(workers):
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(cpu_work, i) for i in range(TOTAL_TASKS)]

        for future in futures:
            result = future.result()

    elapsed = time.time() - start_time
    print(f"Workers: {workers}, Time taken: {elapsed:.2f} seconds")

if __name__ == "__main__":
    for num_workers in [1, 2, 4, 8, 16, 32]:
        run_test(num_workers)

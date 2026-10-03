from concurrent.futures import ProcessPoolExecutor
import time

def process_data(data):
    return sum(data)

def run_local(data):
    start_time = time.time()
    result = process_data(data)
    elapsed = time.time() - start_time
    print(f"Processed data: {result}, Time taken: {elapsed:.2f} seconds")

def run_test(data):
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(process_data, data)
        result = future.result()

    elapsed = time.time() - start_time
    print(f"Processed data: {result}, Time taken: {elapsed:.2f} seconds")

if __name__ == "__main__":

    for size in [1000, 100000, 1000000, 10000000]:
        data = list(range(size))
        run_test(data)
        run_local(data)
        

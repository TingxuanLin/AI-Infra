import asyncio

async def producer(queue):
    for i in range(10):
        request = f"request {i}"

        await queue.put(request)

        print(f"Produced: {request}, "
              f"Queue size: {queue.qsize()}")

        await asyncio.sleep(0.2)

async def consumer(queue):
    while True:

        batch = []

        request = await queue.get()
        batch.append(request)

        while len(batch) < 3 and not queue.empty():
            request = queue.get_nowait()
            batch.append(request)

        print(f"Consumed: {batch}, "
              f"Queue size: {queue.qsize()}")

        await asyncio.sleep(2)

        for _ in batch:
            queue.task_done()

async def main():
    queue = asyncio.Queue(maxsize=5)

    consumer_task = asyncio.create_task(consumer(queue))

    await producer(queue)
    await queue.join()

    consumer_task.cancel()

asyncio.run(main())

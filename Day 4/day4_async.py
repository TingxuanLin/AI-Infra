import asyncio
import time

async def handle_request(name):
    print(f"{name}: start")

    await asyncio.sleep(3)

    print(f"{name}: finished")

async def main():
    start = time.time()
    await asyncio.gather(
        handle_request("request 1"),
        handle_request("request 2"),
        handle_request("request 3"),
    )

    print(f"Total time: {time.time() - start}")

asyncio.run(main())
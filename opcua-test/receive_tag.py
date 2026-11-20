"""Subscribe to one OPC UA variable and print the first sample (None/Anonymous)."""
import argparse
import asyncio
import json

from telemetry import Receiver


async def receive(endpoint, namespace, node):
    receiver = Receiver()
    receiver.connect(endpoint)
    try:
        async with asyncio.timeout(20):
            while receiver.state != "Connected":
                await asyncio.sleep(0.1)
            key = await receiver.add_node(node, namespace)
            receiver.select([key])
            while True:
                sample, = receiver.snapshot()
                if sample["received_at"] or sample["quality"] != "Missing":
                    return sample
                await asyncio.sleep(0.1)
    except TimeoutError as exc:
        raise TimeoutError(receiver.error or "20초 안에 첫 수신값을 받지 못했습니다.") from exc
    finally:
        await receiver.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint")
    parser.add_argument("--namespace", default="urn:hd:opcua:test:v1")
    parser.add_argument("--node", default="s=Stream/1/Pressure")
    args = parser.parse_args()
    sample = asyncio.run(receive(args.endpoint, args.namespace, args.node))
    print(json.dumps(sample, ensure_ascii=False, indent=2, default=str))

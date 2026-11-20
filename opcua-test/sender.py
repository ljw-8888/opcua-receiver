"""Run the workbook-based OPC UA simulator without a GUI."""

import argparse
import asyncio
import logging

from telemetry import Simulator


async def serve(args):
    simulator = Simulator()
    simulator.start(args.host, args.port, args.interval, args.variation)
    await simulator.task
    if simulator.error:
        raise SystemExit(simulator.error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Internal IPv4 address to bind")
    parser.add_argument("--port", type=int, default=4840)
    parser.add_argument("--interval", type=float, default=1.0, help="Update interval in seconds")
    parser.add_argument("--variation", type=float, default=5.0, help="Simulation variation in percent")
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("telemetry").setLevel(logging.INFO)
    try:
        asyncio.run(serve(parser.parse_args()))
    except KeyboardInterrupt:
        pass

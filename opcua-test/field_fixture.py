"""Interoperability fixture: arbitrary tree/types, deliberately no heartbeat."""
import argparse
import asyncio
import signal
from datetime import datetime, timezone

from asyncua import Server, ua


async def run(host, port):
    server = Server()
    await server.init()
    server.set_endpoint(f'opc.tcp://{host}:{port}/vendor/process/')
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    ns = await server.register_namespace('urn:plant:line-a')
    ns2 = await server.register_namespace('urn:plant:line-b')
    root = await server.nodes.objects.add_object(ua.NodeId(500, ns), 'ProductionLine')
    pressure = await root.add_variable(ua.NodeId(1001, ns), 'Pressure', ua.Variant(3.5, ua.VariantType.Float))
    await pressure.add_property(ns, 'EngineeringUnits', ua.EUInformation(DisplayName=ua.LocalizedText('bar')))
    await root.add_variable(ua.NodeId(1001, ns2), 'Running', True)
    await root.add_variable(ua.NodeId('Batch/Serial', ns), 'BatchSerial', ua.Variant(2**63+123, ua.VariantType.UInt64))
    await root.add_variable(ua.NodeId('Recipe', ns), 'Recipe', 'Constant recipe A')
    await root.add_variable(ua.NodeId('StartedAt', ns), 'StartedAt', datetime.now(timezone.utc))
    stopped = asyncio.Event()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    async with server:
        step = 0
        while not stopped.is_set():
            await pressure.write_value(ua.Variant(3.5 + (step % 20)/10, ua.VariantType.Float))
            step += 1
            try:
                await asyncio.wait_for(stopped.wait(), 1)
            except asyncio.TimeoutError:
                pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=4841)
    args = parser.parse_args()
    asyncio.run(run(args.host, args.port))

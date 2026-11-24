"""OPC UA test logic, independent of ovui and Omniverse Kit."""

import asyncio
import contextlib
import copy
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import random
import sys
from datetime import datetime, timezone

from asyncua import Server, ua
from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent
# Source checkouts and PyInstaller use the same client and file contract as Kit.
if not getattr(sys, "frozen", False):
    sys.path.insert(1, str(ROOT.parent / "exts" / "hd.opcua.receiver" / "hd_opcua_receiver"))

from receiver import (LEGACY_PREFIX, NAMESPACE, SECURITY_MODES, Receiver as SubscriptionReceiver,
                      address_key, excel_value, interval, parse_address, secure_client, utc_now,
                      validate_endpoint, validate_security)

HEARTBEAT = "System/Heartbeat"
LOG = logging.getLogger(__name__)
SETUP_FIELDS = {'endpoint', 'namespace', 'root', 'node_id', 'alias', 'unit', 'heartbeat',
                'application_uri', 'certificate', 'private_key', 'server_certificate', 'username'}


def validate_setup(setup):
    if setup.get('version') != 1 or type(setup.get('security_mode')) is not int or not 0 <= setup['security_mode'] < len(SECURITY_MODES):
        raise ValueError('Unsupported setup format')
    fields = setup.get('fields', {})
    if not isinstance(fields, dict) or not set(fields) <= SETUP_FIELDS:
        raise ValueError('Unknown setup fields (passwords must not be stored)')
    if not all(isinstance(v, str) and len(v) <= 4096 for v in fields.values()):
        raise ValueError('Invalid setup field value')
    validate_endpoint(fields.get('endpoint', ''))
    for name in ['root', 'node_id', 'heartbeat']:
        if fields.get(name):
            parse_address(fields[name], fields.get('namespace', ''))
    if not isinstance(setup.get('tags'), list) or len(setup['tags']) > 5000:
        raise ValueError('Setup must have at most 5000 tags')
    keys = set()
    for tag in setup['tags']:
        if not isinstance(tag, dict) or not all(isinstance(tag.get(k), str) for k in
                ['identifier', 'namespace_uri', 'node_id', 'asset', 'metric', 'unit', 'data_type']):
            raise ValueError('Invalid tag definition')
        node, _ = parse_address(tag['node_id'])
        if node.NamespaceIndex or tag['identifier'] != address_key(tag['namespace_uri'], tag['node_id']):
            raise ValueError('Tag address must use a stable Namespace URI')
        if tag['identifier'] in keys:
            raise ValueError('Duplicate tag')
        keys.add(tag['identifier'])
    if not isinstance(setup.get('selected'), list) or not all(isinstance(k, str) and k in keys for k in setup['selected']):
        raise ValueError('Invalid selected tags')
    return setup


def save_setup(fields, security_mode, tags, selected, path=None):
    path = Path(path or ROOT / 'receiver-setup.json')
    setup = validate_setup({'version': 1, 'fields': {k: v for k, v in fields.items() if k in SETUP_FIELDS},
                            'security_mode': security_mode, 'tags': tags, 'selected': sorted(selected)})
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(pending, path)


def load_setup(path=None):
    path = Path(path or ROOT / 'receiver-setup.json')
    if path.stat().st_size > 5_000_000:
        raise ValueError('Setup file is too large')
    return validate_setup(json.loads(path.read_text(encoding='utf-8')))


def load_tags():
    tags = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))["tags"]
    identifiers = [tag["identifier"] for tag in tags]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate data identifiers")
    for tag in tags:
        if not math.isfinite(tag["baseline"]):
            raise ValueError("Non-finite baseline")
    return tags


def endpoint(host, port):
    address = ipaddress.ip_address(host.strip())
    if address.version != 4 or not (address.is_private or address.is_loopback):
        raise ValueError("This test build accepts private IPv4 addresses only")
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535")
    return f"opc.tcp://{address}:{port}/hd/"


def simulated_values(tags, variation, rng):
    """Perturb baseline values; preserve the spreadsheet's derived relations."""
    result = {}
    for tag in tags:
        metric = tag["metric"]
        if metric in {"LiquidFraction", "Velocity", "LevelM"}:
            continue
        base = tag["baseline"]
        span = max(abs(base), 1.0) * variation / 100
        value = base + rng.uniform(-span, span)
        if metric == "VaporFraction":
            value = min(1.0, max(0.0, value))
        elif metric == "LevelPct":
            value = min(100.0, max(0.0, value))
        elif metric != "Temperature":
            value = max(0.0, value)
        result[tag["identifier"]] = value
    for tag in tags:
        key = tag["identifier"]
        prefix = key.rsplit("/", 1)[0]
        if tag["metric"] == "LiquidFraction":
            result[key] = 1.0 - result[prefix + "/VaporFraction"]
        elif tag["metric"] == "Velocity":
            area = math.pi / 4 * (tag["inner_diameter_mm"] / 1000) ** 2
            result[key] = result[prefix + "/VolumeFlow"] / (3600 * area)
        elif tag["metric"] == "LevelM":
            result[key] = tag["height_m"] * result[prefix + "/LevelPct"] / 100
    return result


class Simulator:
    def __init__(self):
        self.tags = load_tags()
        self.state = "Stopped"
        self.error = ""
        self.values = {}
        self.counter = 0
        self.paused = False
        self.update_seconds = 1.0
        self.variation = 5.0
        self.task = None
        self._server = None

    def start(self, host, port, seconds, variation):
        if self.task and not self.task.done():
            raise ValueError("Server is already running")
        url = endpoint(host, port)
        self.update_seconds = interval(seconds, "Update interval")
        variation = float(variation)
        if not math.isfinite(variation) or not 0 <= variation <= 30:
            raise ValueError("Variation must be 0..30 percent")
        self.variation = variation
        self.error = ""
        self.state = "Starting"
        self.task = asyncio.create_task(self._run(url))

    async def _run(self, url):
        server = Server()
        started = False
        try:
            await server.init()
            server.set_endpoint(url)
            server.set_server_name("OPC UA Test Server")
            server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            ns = await server.register_namespace(NAMESPACE)
            root = await server.nodes.objects.add_object(ua.NodeId("Telemetry", ns), "Telemetry")
            nodes = {}
            for tag in self.tags:
                node = await root.add_variable(
                    ua.NodeId(tag["identifier"], ns), tag["identifier"],
                    ua.Variant(tag["baseline"], ua.VariantType.Double),
                )
                await node.add_property(ns, "Unit", tag["unit"])
                nodes[tag["identifier"]] = node
            heartbeat = await root.add_variable(
                ua.NodeId(HEARTBEAT, ns), HEARTBEAT,
                ua.Variant(0, ua.VariantType.UInt64),
            )
            await server.start()
            started = True
            self._server = server
            self.state = "Running"
            LOG.info("Server listening on %s (%s values)", url, len(nodes))
            rng = random.Random()
            self.counter = 0
            while True:
                if not self.paused:
                    self.values = simulated_values(self.tags, self.variation, rng)
                    timestamp = datetime.now(timezone.utc)
                    for key, value in self.values.items():
                        await nodes[key].write_value(ua.DataValue(
                            Value=ua.Variant(value, ua.VariantType.Double),
                            StatusCode=ua.StatusCode(ua.StatusCodes.Good),
                            SourceTimestamp=timestamp,
                        ))
                    self.counter += 1
                    await heartbeat.write_value(ua.DataValue(
                        Value=ua.Variant(self.counter, ua.VariantType.UInt64),
                        SourceTimestamp=timestamp,
                    ))
                await asyncio.sleep(self.update_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
            LOG.exception("Server failed")
        finally:
            if started:
                await server.stop()
            self._server = None
            self.state = "Stopped"

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        self.paused = False


class Receiver(SubscriptionReceiver):
    """Also accept aliases and units supplied by desktop source callers."""

    async def add_node(self, text, namespace_uri='', alias='', unit=''):
        key = await super().add_node(text, namespace_uri)
        tag = next(t for t in self.tags if t["identifier"] == key)
        if alias.strip():
            tag["metric"] = alias.strip()
        if unit:
            tag["unit_override"] = unit
        if tag.get("unit_override"):
            tag["unit"] = tag["unit_override"]
        return key

    async def _subscription_node(self, client, tag):
        node = await super()._subscription_node(client, tag)
        if tag.get("unit_override"):
            tag["unit"] = tag["unit_override"]
        return node

    def accept(self, identifier, dv):
        if identifier in self.selected:
            tag = next(t for t in self.tags if t["identifier"] == identifier)
            self._accept_sample(tag, dv)


class ExcelRecorder:
    HEADERS = ["saved_at", "source", "asset", "metric", "identifier", "value", "raw_value", "unit",
               "quality", "status_code", "source_timestamp", "server_timestamp", "received_at",
               "connection", "freshness", "namespace_uri", "data_type"]
    MAX_ROWS = 200_000

    def __init__(self, directory=None):
        self.directory = Path(directory or ROOT / "exports").resolve()
        self.path = None
        self.workbook = None
        self.task = None
        self.error = ""
        self.saved_at = ""
        self.rows = 0
        self.state = "Stopped"
        self._stop = asyncio.Event()

    def start(self, receiver, filename, seconds):
        if self.task and not self.task.done():
            raise ValueError("Recording is already running")
        seconds = interval(seconds, "Save interval")
        if not receiver.selected:
            raise ValueError("Select and subscribe to data before recording")
        if Path(filename).name != filename or not filename.lower().endswith(".xlsx"):
            raise ValueError("Use a filename ending in .xlsx, without folders")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / filename
        if self.path.exists() or self.path.with_suffix(".pending.xlsx").exists():
            raise ValueError("File already exists; choose a new filename")
        self.workbook = Workbook()
        sheet = self.workbook.active
        sheet.title = "Samples"
        sheet.append(self.HEADERS)
        sheet.freeze_panes = "A2"
        self.rows = 0
        self.error = ""
        self.saved_at = ""
        self._stop.clear()
        self.state = "Recording"
        self.task = asyncio.create_task(self._run(receiver, seconds))

    def _save(self, rows):
        sheet = self.workbook.active
        # shortcut: bounded test workbook; rotate files for continuous production logging.
        if self.rows + len(rows) > self.MAX_ROWS:
            raise OverflowError("200,000-row test limit reached; start a new workbook")
        converted = [[excel_value(record.get(name)) for name in self.HEADERS] for record in rows]
        for row_number, values in enumerate(converted, start=self.rows + 2):
            sheet.append(values)
            for column, value in enumerate(values, start=1):
                if isinstance(value, str):
                    sheet.cell(row_number, column).data_type = "s"  # Preserve leading '=' as text.
        self.rows += len(rows)
        pending = self.path.with_suffix(".pending.xlsx")
        self.workbook.save(pending)
        os.replace(pending, self.path)

    async def _run(self, receiver, seconds):
        try:
            while not self._stop.is_set():
                rows = copy.deepcopy(receiver.snapshot())
                try:
                    await asyncio.to_thread(self._save, rows)
                    self.saved_at = utc_now()
                    self.error = ""
                    self.state = "Recording"
                except OverflowError as exc:
                    self.error = str(exc)
                    break
                except Exception as exc:
                    self.error = str(exc)
                    self.state = "Save error - retrying"
                    LOG.exception("Excel save failed; previous workbook is preserved")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=seconds)
                except asyncio.TimeoutError:
                    pass
            if self.error:
                try:
                    await asyncio.to_thread(self._save, [])
                    self.saved_at = utc_now()
                except Exception:
                    LOG.exception("Final Excel retry failed")
        finally:
            self.state = "Stopped"

    async def stop(self):
        self._stop.set()
        if self.task:
            await self.task

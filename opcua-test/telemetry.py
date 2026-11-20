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
import time
import re
import base64
from datetime import datetime, timezone
from urllib.parse import urlsplit

from asyncua import Client, Server, ua
from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent
NAMESPACE = "urn:hd:opcua:test:v1"
# The original release used the test namespace's organization in local file names.
LEGACY_PREFIX = NAMESPACE.split(":")[1]
HEARTBEAT = "System/Heartbeat"
LOG = logging.getLogger(__name__)


def validate_endpoint(url):
    url = url.strip()
    parsed = urlsplit(url)
    if (parsed.scheme != 'opc.tcp' or not parsed.hostname or not parsed.port
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or any(c.isspace() for c in url)):
        raise ValueError('Use opc.tcp://host:port/path without credentials, query or fragment')
    return url


def parse_address(text, default_uri=''):
    text = text.strip()
    if not re.match(r'^(?:(?:ns=\d+|nsu=[^;]+);)?[isgb]=', text) or len(text) > 4096:
        raise ValueError('NodeId: i=123, s=Tag, ns=2;i=123, g=UUID or b=BASE64')
    try:
        node = ua.NodeId.from_string(text)
    except Exception as exc:
        raise ValueError('Invalid NodeId syntax') from exc
    if not 0 <= node.NamespaceIndex <= 65535:
        raise ValueError('Namespace index must be 0..65535')
    if node.NodeIdType == ua.NodeIdType.Numeric and not 0 <= node.Identifier <= 4294967295:
        raise ValueError('Numeric NodeId must be UInt32')
    uri = getattr(node, 'NamespaceUri', None) or (default_uri.strip() if not text.startswith('ns=') else '')
    return ua.NodeId(node.Identifier, node.NamespaceIndex, node.NodeIdType), uri


def address_key(uri, local_id):
    return json.dumps([uri, local_id], ensure_ascii=False)


SECURITY_MODES = ['None', 'Basic256Sha256 / Sign', 'Basic256Sha256 / SignAndEncrypt']


def validate_security(options):
    result = {name: str(options.get(name, '')).strip() for name in
              ['mode', 'certificate', 'private_key', 'server_certificate', 'application_uri', 'username']}
    result['mode'] = result['mode'] or 'None'
    result['password'] = options.get('password', '')
    result['key_password'] = options.get('key_password', '')
    if result['mode'] not in SECURITY_MODES:
        raise ValueError('Unsupported security policy / mode')
    if result['mode'] == 'None' and (result['username'] or result['password']):
        raise ValueError('Choose a secure policy before entering a username/password')
    if result['mode'] != 'None':
        for name in ['certificate', 'private_key', 'server_certificate']:
            if not result[name] or not Path(result[name]).is_file():
                raise ValueError(f'{name}: choose an existing certificate/key file on this VM')
        if not result['application_uri']:
            raise ValueError('Application URI must match the client certificate SAN URI')
    if result['password'] and not result['username']:
        raise ValueError('Username is required with a password')
    return result


async def secure_client(client, options):
    if options['mode'] == 'None':
        return
    from asyncua.crypto import security_policies, uacrypto
    from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
    from cryptography.hazmat.primitives import hashes
    trusted = await uacrypto.load_certificate(options['server_certificate'])
    validator = CertificateValidator(CertificateValidatorOptions.TIME_RANGE | CertificateValidatorOptions.URI)

    async def validate(cert, application):
        if cert.fingerprint(hashes.SHA256()) != trusted.fingerprint(hashes.SHA256()):
            raise ua.UaStatusCodeError(ua.StatusCodes.BadCertificateUntrusted)
        await validator.validate(cert, application)

    client.certificate_validator = validate
    client.application_uri = options['application_uri']
    await client.set_security(
        security_policies.SecurityPolicyBasic256Sha256, options['certificate'], options['private_key'],
        private_key_password=options['key_password'] or None,
        server_certificate=options['server_certificate'],
        mode=ua.MessageSecurityMode.SignAndEncrypt if options['mode'].endswith('SignAndEncrypt') else ua.MessageSecurityMode.Sign,
    )
    if options['username']:
        client.set_user(options['username'])
        client.set_password(options['password'])


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


def excel_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, datetime):
        value = value.isoformat()
    elif isinstance(value, bytes):
        value = 'base64:' + base64.b64encode(value).decode('ascii')
    elif isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    else:
        value = str(value)
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', lambda m: f'\\u{ord(m[0]):04x}', value)
    if len(value) > 32767:
        raise ValueError('Value exceeds the Excel 32,767 character cell limit')
    return value


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


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


def interval(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.2 <= value <= 3600:
        raise ValueError(f"{name} must be 0.2..3600 seconds")
    return value


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


class Receiver:
    def __init__(self):
        self.tags = []
        self.folders = []
        self.namespaces = []
        self.selected = set()
        self.samples = {}
        self.state = "Disconnected"
        self.error = ""
        self.task = None
        self.client = None
        self.url = ''
        self.security = {}
        self._node_keys = {}
        self._heartbeat_node = None
        self._heartbeat_value = None
        self.heartbeat = ('', '')
        self.heartbeat_error = ''
        self.browse_note = ''
        self.subscription_count = 0
        self.notification_count = 0
        self.connections = 0
        self.heartbeat_at = None
        self.stale_seconds = 6.0
        self._revision = 0

    def connect(self, url, security=None):
        if self.task and not self.task.done():
            raise ValueError("Disconnect before changing the server")
        url = validate_endpoint(url)
        security = validate_security(security or {})
        if self.url != url:
            self.tags.clear()
            self.folders.clear()
            self.selected.clear()
        self.samples.clear()
        self.url = url
        self.security = security
        self.connections = 0
        self.error = ""
        self.state = "Connecting"
        self.task = asyncio.create_task(self._run())

    def select(self, identifiers):
        known = {tag["identifier"] for tag in self.tags}
        if not set(identifiers) <= known:
            raise ValueError("Unknown selection; browse the server first")
        self.selected = set(identifiers)
        self._revision += 1

    def set_heartbeat(self, text, namespace_uri='', seconds=6):
        if text.strip():
            parse_address(text, namespace_uri)
        self.stale_seconds = interval(seconds, 'Stale threshold')
        self.heartbeat = (text.strip(), namespace_uri.strip())
        self.heartbeat_at = None
        self._heartbeat_value = None
        self.heartbeat_error = ''
        self._revision += 1

    def _address(self, text, namespace_uri=''):
        node, uri = parse_address(text, namespace_uri)
        if uri:
            if uri not in self.namespaces:
                raise ValueError('Namespace URI is not in the server NamespaceArray: ' + uri)
            node = ua.NodeId(node.Identifier, self.namespaces.index(uri), node.NodeIdType)
        if node.NamespaceIndex >= len(self.namespaces):
            raise ValueError('Namespace index is not in the server NamespaceArray')
        uri = self.namespaces[node.NamespaceIndex]
        local = ua.NodeId(node.Identifier, 0, node.NodeIdType).to_string()
        return node, uri, local

    def _resolve_tag(self, tag):
        return self._address(tag['node_id'], tag['namespace_uri'])[0]

    async def add_node(self, text, namespace_uri='', alias='', unit=''):
        requested_unit = unit
        if not self.client:
            raise ValueError("Connect to the server first")
        node_id, uri, local = self._address(text, namespace_uri)
        node = self.client.get_node(node_id)
        if await node.read_node_class() != ua.NodeClass.Variable:
            raise ValueError('Choose a Variable node, not an Object or Method')
        display = await node.read_display_name()
        variant_type = await node.read_data_type_as_variant_type()
        key = address_key(uri, local)
        if not unit:
            with contextlib.suppress(ua.UaStatusCodeError):
                for prop in await node.get_properties():
                    name = (await prop.read_browse_name()).Name
                    if name in ('EngineeringUnits', 'Unit'):
                        value = await prop.read_value()
                        unit = value.DisplayName.Text if isinstance(value, ua.EUInformation) else str(value)
                        break
        tag = {'identifier': key, 'namespace_uri': uri, 'node_id': local,
               'asset': 'OPC UA', 'metric': alias.strip() or display.Text or local,
               'unit': unit or '', 'data_type': variant_type.name}
        previous = next((t for t in self.tags if t['identifier'] == key), None)
        if previous:
            if alias.strip():
                previous['metric'] = alias.strip()
            if requested_unit or not previous['unit']:
                previous['unit'] = unit or ''
            previous['data_type'] = variant_type.name
        else:
            self.tags.append(tag)
        return key

    async def browse(self, text='ns=0;i=85', namespace_uri=''):
        if not self.client:
            raise ValueError('Connect before browsing')
        node_id, _, _ = self._address(text, namespace_uri)
        root = self.client.get_node(node_id)
        refs = await root.get_children_descriptions()
        self.folders = []
        keys = []
        failed = 0
        for ref in refs:
            if getattr(ref.NodeId, 'ServerIndex', 0) or getattr(ref.NodeId, 'NamespaceUri', None):
                continue  # Remote ExpandedNodeIds require a separate server session.
            address = ua.NodeId(ref.NodeId.Identifier, ref.NodeId.NamespaceIndex, ref.NodeId.NodeIdType).to_string()
            if ref.NodeClass == ua.NodeClass.Variable:
                try:
                    keys.append(await self.add_node(address))
                except (ua.UaStatusCodeError, ValueError):
                    failed += 1
            elif ref.NodeClass == ua.NodeClass.Object:
                self.folders.append({'name': ref.DisplayName.Text or address, 'node_id': address})
        self.browse_note = f'{len(refs)} children; {failed} unreadable variables'
        return keys

    async def _subscribe(self, client, subscription):
        if subscription:
            await subscription.delete()
        self.subscription_count = 0
        self._node_keys = {}
        self._heartbeat_node = None
        self.heartbeat_at = None
        self._heartbeat_value = None
        self.heartbeat_error = ''
        self.samples = {k: v for k, v in self.samples.items() if k in self.selected}
        by_id = {tag['identifier']: tag for tag in self.tags}
        nodes = {}
        for key in sorted(self.selected):
            try:
                node_id = self._resolve_tag(by_id[key])
                self._node_keys[node_id.to_string()] = key
                nodes[node_id.to_string()] = client.get_node(node_id)
            except ValueError:
                self.samples[key] = {'value': None, 'quality': 'MissingNamespace'}
        if self.heartbeat[0]:
            try:
                node_id, uri, local = self._address(*self.heartbeat)
                self.heartbeat = (local, uri)
                self._heartbeat_node = node_id.to_string()
                nodes[self._heartbeat_node] = client.get_node(node_id)
            except ValueError as exc:
                self.heartbeat_error = str(exc)
        if not nodes:
            return None
        subscription = await client.create_subscription(250, self)
        try:
            node_list = list(nodes.values())
            handles = await subscription.subscribe_data_change(node_list, queuesize=10, sampling_interval=200)
            for node, handle in zip(node_list, handles):
                address = node.nodeid.to_string()
                key = self._node_keys.get(address)
                if isinstance(handle, ua.StatusCode):
                    if key:
                        self.accept(key, ua.DataValue(StatusCode=handle))
                    if address == self._heartbeat_node:
                        self.heartbeat_error = handle.name
                    continue
                if key:
                    self.subscription_count += 1
                self._accept_node(address, await node.read_data_value(raise_on_bad_status=False))
            return subscription
        except BaseException:
            with contextlib.suppress(Exception):
                await subscription.delete()
            raise

    async def _run(self):
        retry = 1.0
        try:
            while True:
                self.state = "Connecting" if not self.connections else "Reconnecting"
                client = Client(self.url, timeout=4, auto_reconnect=False)
                try:
                    await secure_client(client, self.security)
                    async with client:
                        self.namespaces = await client.get_namespace_array()
                        self.client = client
                        self.samples.clear()
                        self.heartbeat_at = None
                        self.connections += 1
                        self.state = "Connected"
                        self.error = ""
                        retry = 1.0
                        LOG.info("Connected to %s; %s namespaces", self.url, len(self.namespaces))
                        subscription = None
                        revision = -1
                        try:
                            while True:
                                if revision != self._revision:
                                    requested_revision = self._revision
                                    subscription = await self._subscribe(client, subscription)
                                    revision = requested_revision
                                await asyncio.sleep(0.5)
                                await client.check_connection()
                        finally:
                            if subscription:
                                with contextlib.suppress(Exception):
                                    await subscription.delete()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.error = f"{type(exc).__name__}: {exc}"
                    self.state = "Reconnecting"
                    LOG.warning("Connection lost: %s", self.error)
                finally:
                    self.client = None
                    self.subscription_count = 0
                await asyncio.sleep(retry)
                retry = min(retry * 2, 10)
        finally:
            self.client = None
            self.state = "Disconnected"
            self.subscription_count = 0

    def accept(self, identifier, dv):
        self.notification_count += 1
        if identifier not in self.selected:
            return
        raw = dv.Value.Value if dv.Value else None
        self.samples[identifier] = {
            "value": raw if dv.StatusCode.is_good() else None,
            "raw_value": raw,
            "quality": dv.StatusCode.name,
            "status_code": dv.StatusCode.value,
            "source_timestamp": dv.SourceTimestamp.isoformat() if dv.SourceTimestamp else "",
            "server_timestamp": dv.ServerTimestamp.isoformat() if dv.ServerTimestamp else "",
            "received_at": utc_now(),
        }

    def _accept_node(self, address, dv):
        if address == self._heartbeat_node:
            raw = dv.Value.Value if dv.Value else None
            if dv.StatusCode.is_good():
                if self.heartbeat_at is None or raw != self._heartbeat_value:
                    self.heartbeat_at = time.monotonic()
                self._heartbeat_value = copy.deepcopy(raw)
                self.heartbeat_error = ''
            else:
                self.heartbeat_error = dv.StatusCode.name
        key = self._node_keys.get(address)
        if key:
            self.accept(key, dv)

    def datachange_notification(self, node, value, data):
        self._accept_node(node.nodeid.to_string(), data.monitored_item.Value)

    def status_change_notification(self, status):
        LOG.warning("Subscription status: %s", status)
        code = getattr(status, 'Status', status)
        if isinstance(code, ua.StatusCode) and not code.is_good():
            self._revision += 1

    @property
    def freshness(self):
        if self.state != "Connected":
            return "Unknown"
        if not self.heartbeat[0]:
            return 'Not monitored'
        if self.heartbeat_error:
            return 'Heartbeat unavailable'
        if self.heartbeat_at is None:
            return 'Waiting for heartbeat'
        return "Stale" if time.monotonic() - self.heartbeat_at > self.stale_seconds else "Fresh"

    def snapshot(self):
        stamp = utc_now()
        by_id = {tag["identifier"]: tag for tag in self.tags}
        rows = []
        for identifier in sorted(self.selected):
            tag = by_id[identifier]
            sample = self.samples.get(identifier, {})
            rows.append({
                "saved_at": stamp, "source": self.url, "asset": tag["asset"],
                "metric": tag["metric"], "unit": tag["unit"], "identifier": tag['node_id'],
                "namespace_uri": tag['namespace_uri'], 'data_type': tag['data_type'],
                "value": sample.get("value"), "raw_value": sample.get("raw_value"),
                "quality": sample.get("quality", "Missing"), "status_code": sample.get("status_code"),
                "source_timestamp": sample.get("source_timestamp", ""),
                "server_timestamp": sample.get("server_timestamp", ""),
                "received_at": sample.get("received_at", ""),
                "connection": self.state, "freshness": self.freshness,
            })
        return rows

    async def disconnect(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task


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

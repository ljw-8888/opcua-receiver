"""OPC UA client code adapted from ljw-8888/opcua-receiver,
opcua-test/telemetry.py at 4596945705cf92aa303c08f9f43bd0326b95000e.
"""

import asyncio
import base64
import contextlib
import copy
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from asyncua import Client, ua

ROOT = Path(__file__).resolve().parent.parent / "data"
NAMESPACE = "urn:hd:opcua:test:v1"
LEGACY_PREFIX = NAMESPACE.split(":")[1]
LOG = logging.getLogger(__name__)
SECURITY_MODES = ["None", "Basic256Sha256 / Sign", "Basic256Sha256 / SignAndEncrypt"]


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


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def interval(value, name):
    value = float(value)
    if not math.isfinite(value) or not 0.2 <= value <= 3600:
        raise ValueError(f"{name} must be 0.2..3600 seconds")
    return value


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
            start, batch_size = 0, 64
            while start < len(node_list):
                batch = node_list[start:start + batch_size]
                try:
                    handles = await subscription.subscribe_data_change(batch, queuesize=10, sampling_interval=200)
                except ua.UaStatusCodeError as exc:
                    if exc.code == ua.StatusCodes.BadTooManyOperations and len(batch) > 1:
                        batch_size = max(1, len(batch) // 2)
                        continue
                    if exc.code != ua.StatusCodes.BadTooManyMonitoredItems:
                        raise
                    handles = [ua.StatusCode(exc.code)] * len(batch)
                for node, handle in zip(batch, handles):
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
                # Monitored items receive an initial DataChange as well as subsequent changes.
                start += len(batch)
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


def load_tags():
    tags = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))["tags"]
    identifiers = [tag["identifier"] for tag in tags]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate data identifiers")
    for tag in tags:
        if not math.isfinite(tag["baseline"]):
            raise ValueError("Non-finite baseline")
    return tags

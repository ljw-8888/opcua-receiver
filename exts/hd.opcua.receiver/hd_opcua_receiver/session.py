"""Receiver session shared by the Kit settings window and scene consumers."""

import asyncio
import contextlib
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from asyncua import ua
from filelock import FileLock

from .language import tr
from .latest_excel import hysys_definitions, save_latest
from .receiver import NAMESPACE, Receiver, address_key, interval

SAVED_FIELDS = ("mode", "auth", "username", "certificate", "private_key",
                "server_certificate", "application_uri", "seconds")
ROOT_NODE = "i=85"


class Session:
    def __init__(self, config):
        self.receiver = Receiver()
        self.config = Path(config)
        self.definitions = hysys_definitions()
        self.settings = {}
        self.registered = {}
        self.chosen = set()
        self.overrides = {}
        self.paused = {}
        self.tags = {}
        self.groups = {}
        self.members = {}
        self.catalog = set()
        self.scanning = False
        self.scan_error = ""
        self.skipped = 0
        self._client = None
        self._scan = None
        self.writer = None
        self.save_status = tr("Excel 저장 대기")
        self.last_save = ""
        self.preview = None
        self.revision = 0
        if self.config.exists():
            self._read_settings()

    def _read_settings(self):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        self.settings = {k: v for k, v in data.get("settings", {}).items() if k in SAVED_FIELDS}
        self.registered = {k: tag for k, tag in data.get("registrations", {}).get(self.receiver.url, {}).items()
                           if not tag.get("legacy")}

    def persist(self, *, settings=None, add=None, remove=()):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.config) + ".lock", timeout=1):
            data = json.loads(self.config.read_text(encoding="utf-8")) if self.config.exists() else {}
            records = data.setdefault("registrations", {}).setdefault(self.receiver.url, {})
            if add:
                records[add["identifier"]] = add
            for key in remove:
                records.pop(key, None)
            if settings is not None:
                data["settings"] = {k: settings[k] for k in SAVED_FIELDS}
            pending = self.config.with_suffix(".tmp")
            pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            pending.replace(self.config)
            self._read_settings()
        self.revision += 1

    def connect(self, endpoint, options):
        self.receiver.connect(endpoint, options)
        self.receiver.tags.clear()
        self.receiver.select([])
        self.chosen.clear()
        self.overrides.clear()
        self.tags.clear()
        self.paused.clear()
        self.registered = {}
        if self.config.exists():
            self._read_settings()
        self.revision += 1

    def update_client(self):
        client = self.receiver.client
        if client is self._client:
            return
        self._client = client
        if self._scan:
            self._scan.cancel()
        self.groups.clear()
        self.members.clear()
        self.catalog.clear()
        self.scan_error = ""
        self.skipped = 0
        self.scanning = client is not None
        self.revision += 1
        self._scan = asyncio.create_task(self._discover(client)) if client else None

    async def _discover(self, client):
        """Browse hierarchical children including nested variables and continuation pages."""
        queue = deque([ROOT_NODE])
        visited = {ROOT_NODE}
        try:
            while queue:
                parents = [queue.popleft() for _ in range(min(12, len(queue)))]
                results = await asyncio.gather(*(client.get_node(p).get_children_descriptions()
                                                 for p in parents), return_exceptions=True)
                if self.receiver.client is not client:
                    return
                for parent, refs in zip(parents, results):
                    if isinstance(refs, ua.UaStatusCodeError):
                        self.skipped += 1
                        continue
                    if isinstance(refs, BaseException):
                        raise refs
                    folders, keys = [], set()
                    for ref in refs:
                        node = ref.NodeId
                        if getattr(node, "ServerIndex", 0) or getattr(node, "NamespaceUri", None) or ref.NodeClass not in (
                                ua.NodeClass.Object, ua.NodeClass.Variable):
                            continue
                        address = ua.NodeId(node.Identifier, node.NamespaceIndex, node.NodeIdType).to_string()
                        name = ref.DisplayName.Text or address
                        if address not in visited:
                            visited.add(address)
                            queue.append(address)
                        if ref.NodeClass == ua.NodeClass.Object:
                            folders.append((address, name))
                        else:
                            local = ua.NodeId(node.Identifier, 0, node.NodeIdType).to_string()
                            uri = self.receiver.namespaces[node.NamespaceIndex]
                            key = address_key(uri, local)
                            keys.add(key)
                            self.catalog.add(key)
                            if key not in self.tags:
                                definition = self.definitions.get(local, {}) if uri == NAMESPACE else {}
                                tag = dict(identifier=key, node_id=local, namespace_uri=uri,
                                           metric=name, asset=definition.get("asset", "OPC UA"),
                                           unit="", data_type="")
                                self.tags[key] = tag
                                self.receiver.tags.append(tag)
                    self.groups[parent] = folders
                    self.members[parent] = keys
                self.revision += 1
                await asyncio.sleep(0)
        except Exception as exc:
            if client is self._client:
                self.scan_error = str(exc) or type(exc).__name__
        finally:
            if client is self._client:
                self.scanning = False
                self.revision += 1

    async def _resolve(self, node, uri):
        client = self.receiver.client
        key = await self.receiver.add_node(node, uri)
        if not client or client is not self.receiver.client:
            raise ValueError(tr("서버 연결이 변경되었습니다."))
        tag = next(t for t in self.receiver.tags if t["identifier"] == key)
        self.tags[key] = tag
        return tag

    async def register(self, node, uri, alias, unit):
        tag = await self._resolve(node, uri)
        record = dict(tag, metric=alias.strip() or tag["metric"], unit=unit.strip() or tag["unit"])
        self.persist(add=record)
        return tag["identifier"]

    async def include_registered(self, keys):
        for key in keys:
            record = self.registered[key]
            await self._resolve(record["node_id"], record["namespace_uri"])
            self.overrides[key] = record
            self.chosen.add(key)
        self.revision += 1

    def choose(self, keys, enabled):
        if self.receiver.selected:
            raise ValueError(tr("수신을 중지한 뒤 태그를 변경하세요."))
        if enabled:
            self.chosen.update(keys)
        else:
            self.chosen.difference_update(keys)
            for key in keys:
                self.overrides.pop(key, None)
        self.revision += 1

    async def start(self, *, filename=None, seconds="5", settings=None):
        if self.receiver.state != "Connected" or not self.chosen:
            raise ValueError(tr("서버에 연결하고 수신할 태그를 선택하세요."))
        if self.writer:
            raise ValueError(tr("이미 저장 중입니다."))
        if filename is not None:
            path = Path(filename.strip()).expanduser().resolve()
            if not filename.strip() or path.suffix.lower() != ".xlsx" or not path.parent.is_dir():
                raise ValueError(tr("기존 폴더 안에 결과 파일(.xlsx)을 지정하세요."))
            seconds = interval(seconds, tr("저장 주기"))
        if settings is not None:
            self.persist(settings=settings)
        if not self.receiver.selected:
            # Browse returns addresses and names cheaply. Read the type and engineering
            # unit only for the tags the operator actually subscribes to.
            pending = [self.tags[k] for k in self.chosen if not self.tags[k]["data_type"]]
            for start in range(0, len(pending), 8):
                results = await asyncio.gather(*(self._resolve(t["node_id"], t["namespace_uri"])
                                                 for t in pending[start:start + 8]), return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException) and not isinstance(result, (ValueError, ua.UaStatusCodeError)):
                        raise result
            self.paused.clear()
            self.receiver.samples.clear()
            self.receiver.select(self.chosen)
        if filename is not None:
            self._stop_save = asyncio.Event()
            self.last_save = ""
            self.save_status = tr("첫 수신 대기 중")
            self.writer = asyncio.create_task(self._write(path, seconds))
        self.revision += 1

    def snapshot(self):
        if self.receiver.state != "Connected":
            return []
        rows = self.receiver.snapshot()
        for row in rows:
            override = self.overrides.get(address_key(row["namespace_uri"], row["identifier"]))
            if override:
                row.update(metric=override["metric"], unit=override["unit"])
        return rows

    async def _write(self, path, seconds):
        try:
            with FileLock(str(path) + ".lock", timeout=0):
                while not self._stop_save.is_set():
                    try:
                        tables = await asyncio.to_thread(save_latest, path, self.snapshot(),
                                                         self.definitions, preview=True)
                        if tables:
                            self.last_save = datetime.now(timezone.utc).strftime("%H:%M:%S")
                            self.preview = (path.name, self.last_save, tables)
                            self.save_status = tr("{name} 저장 완료 · {n:g}초 간격").format(name=path.name, n=seconds)
                        else:
                            self.save_status = tr("수신 대기 중")
                    except OSError as exc:
                        self.save_status = tr("저장 실패 · 다음 주기에 재시도합니다.") + " " + str(exc)
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stop_save.wait(), seconds)
        except Exception as exc:
            self.save_status = tr("Excel 저장 중지") + " · " + str(exc)
        finally:
            self.writer = None
            self.revision += 1

    async def stop_save(self):
        if self.writer:
            self._stop_save.set()
            await self.writer
            self.save_status = tr("Excel 저장 중지")

    async def pause(self):
        await self.stop_save()
        self.paused = self.receiver.samples.copy()
        self.receiver.select([])
        self.revision += 1

    async def disconnect(self):
        await self.stop_save()
        if self._scan:
            self._scan.cancel()
            await asyncio.gather(self._scan, return_exceptions=True)
        await self.receiver.disconnect()
        self.receiver.select([])
        self.paused.clear()
        self.update_client()
        self.revision += 1

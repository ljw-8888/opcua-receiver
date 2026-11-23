"""Make the packaged Python dependencies available without installing into Kit."""
import hashlib
import platform
import site
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

import carb.tokens


def prepare_dependencies():
    system = {"Linux": "linux", "Windows": "windows"}.get(platform.system())
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    bundle = Path(__file__).resolve().parents[1] / "bundles" / f"{system}-x86_64-{abi}.zip"
    if platform.machine().lower() not in {"x86_64", "amd64"} or not bundle.is_file():
        raise RuntimeError(f"OPC UA Receiver requires desktop Kit with CPython 3.12 on Linux or Windows x86-64 ({abi})")
    key = bundle.with_suffix(".zip.sha256").read_text().strip()
    cache = Path(carb.tokens.get_tokens_interface().resolve("${cache}")) / "hd.opcua.receiver"
    target = cache / key
    if not target.is_dir():
        cache.mkdir(parents=True, exist_ok=True)
        with bundle.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != key:
                raise RuntimeError(f"Incomplete OPC UA dependency bundle: {bundle.name}")
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            staging = Path(tmp) / "packages"
            with ZipFile(bundle) as archive:
                archive.extractall(staging)
            try:
                staging.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    if str(target) not in sys.path:
        site.addsitedir(str(target))

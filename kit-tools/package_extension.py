"""Package the standalone Kit extension, optionally rebuilding its offline dependencies."""
import argparse
import hashlib
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "exts" / "hd.opcua.receiver"


def archive(source, target, prefix=""):
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source)
            if path.is_file() and "__pycache__" not in rel.parts and path.suffix != ".pyc":
                if not prefix and rel.parts[0] in ("bin", "Scripts"):
                    continue
                output.write(path, Path(prefix) / rel)


def build_bundle(platform, sources):
    target = EXT / "bundles" / f"{platform}-cp312.zip"
    with tempfile.TemporaryDirectory() as tmp:
        args = [sys.executable, "-m", "pip", "install", "--no-compile", "--only-binary=:all:",
                "--target", tmp, "-r", str(ROOT / "kit-tools" / "requirements-kit.txt")]
        if platform == "windows-x86_64":
            args += ["--platform", "win_amd64", "--python-version", "3.12", "pywin32==311"]
        if sources:
            args += ["--no-index", "--find-links", sources]
        subprocess.run(args, check=True)
        archive(Path(tmp), target)
    with target.open("rb") as stream:
        target.with_suffix(".zip.sha256").write_text(hashlib.file_digest(stream, "sha256").hexdigest() + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-bundles", action="store_true")
    parser.add_argument("--wheelhouse", help="Optional local directory of replacement dependency wheels")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    if args.rebuild_bundles:
        if sys.version_info[:2] != (3, 12) or sys.platform != "linux":
            parser.error("Rebuild the Linux and Windows bundles on x86-64 Linux with Python 3.12.")
        for platform in ("linux-x86_64", "windows-x86_64"):
            build_bundle(platform, args.wheelhouse)
    for bundle in (EXT / "bundles").glob("*.zip"):
        with bundle.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != bundle.with_suffix(".zip.sha256").read_text().strip():
                raise ValueError(f"Checksum mismatch: {bundle.name}")
    with (EXT / "config" / "extension.toml").open("rb") as f:
        version = tomllib.load(f)["package"]["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    result = args.output / f"hd.opcua.receiver-{version}.zip"
    archive(EXT, result, "exts/hd.opcua.receiver")
    print(result)


if __name__ == "__main__":
    main()

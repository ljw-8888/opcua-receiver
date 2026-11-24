from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, get_package_paths

root = Path(SPECPATH)
if sys.platform == "win32":
    # Other desktop tools can put incompatible OpenSSL and ICU DLLs on PATH.
    system = Path(os.environ["SystemRoot"])
    os.environ["PATH"] = os.pathsep.join(map(str, (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        system / "System32", system,
    )))
assets = [(str(root / "fonts"), "fonts"), (str(root / "data.json"), ".")]
icon = str(root / "icons" / "opcua-receiver.ico")
assets.append((icon, "icons"))
assets += collect_data_files("asyncua") + copy_metadata("asyncua")
assets += collect_data_files("pxr", includes=["pluginfo/plugInfo.json", "pluginfo/ar/**/*", "pluginfo/sdf/**/*"])
assets += copy_metadata("usd-core")
# OpenUSD imports its compiled bindings at runtime.
bindings = ["pxr." + name + "._" + name.lower() for name in ("Ar", "Gf", "Plug", "Sdf", "Tf", "Trace", "Ts", "Vt", "Work")]
pxr = Path(get_package_paths("pxr")[1])
if sys.platform == "win32":
    usd_libs = [(str(pxr / name), "pxr") for name in ("usd_ms.dll", "tbb.dll")]
    bindings.append("win32com.client")
else:
    usd_libs = [(str(p), "usd_core.libs") for p in (pxr.parent / "usd_core.libs").glob("*.so*")]
shared = root.parent / "exts" / "hd.opcua.receiver" / "hd_opcua_receiver"
a = Analysis([str(root / "receiver_gui.py")], datas=assets, binaries=usd_libs,
             pathex=[str(root), str(shared)], hiddenimports=bindings,
             excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick"])
exe = EXE(PYZ(a.pure), a.scripts, a.binaries, a.datas, [],
          name="OPCUA-Receiver", icon=icon if sys.platform == "win32" else None,
          console=False, upx=False)

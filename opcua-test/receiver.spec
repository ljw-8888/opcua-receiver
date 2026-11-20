from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

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
a = Analysis([str(root / "receiver_gui.py")], datas=assets,
             hiddenimports=["win32com.client"] if sys.platform == "win32" else [],
             excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick"])
exe = EXE(PYZ(a.pure), a.scripts, a.binaries, a.datas, [],
          name="OPCUA-Receiver", icon=icon if sys.platform == "win32" else None,
          console=False, upx=False)

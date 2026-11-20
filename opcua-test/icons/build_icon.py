"""Rebuild the Windows and Qt icon from the SVG using the receiver's PySide6."""
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

base = Path(__file__).resolve().parent
svg = QSvgRenderer(str(base / "opcua-receiver.svg"))
if not svg.isValid():
    raise ValueError("Invalid receiver icon SVG")
sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
header = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
frames = bytearray()
for size in sizes:
    surface = QImage(size, size, QImage.Format.Format_ARGB32)
    surface.fill(Qt.GlobalColor.transparent)
    painter = QPainter(surface)
    svg.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not surface.save(buffer, "PNG"):
        raise RuntimeError(f"Cannot encode icon at {size}px")
    frame = bytes(buffer.data())
    offset = 6 + 16 * len(sizes) + len(frames)
    header.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(frame), offset))
    frames.extend(frame)
(base / "opcua-receiver.ico").write_bytes(header + frames)

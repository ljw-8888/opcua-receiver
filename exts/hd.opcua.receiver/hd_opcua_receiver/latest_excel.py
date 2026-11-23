"""Replace the latest-value workbook atomically. No sample history is appended."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook, load_workbook
from openpyxl.packaging.custom import StringProperty
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .receiver import LEGACY_PREFIX, NAMESPACE, excel_value, load_tags


HEADERS = ("설비", "항목", "값", "단위", "품질", "측정 시각", "수신 시각",
           "연결 상태", "저장 시각", "Namespace URI", "NodeId", "Endpoint")
FIELDS = ("asset", "metric", "value", "unit", "quality", "source_timestamp", "received_at",
          "connection", "saved_at", "namespace_uri", "identifier", "source")
MARKER = "OPC UA receiver snapshot v1"


def literal(cell, value):
    cell.value = excel_value(value)
    if isinstance(cell.value, str):
        cell.data_type = "s"


def result_sheet(book, title, create=True):
    key = "OPCUA." + title
    properties = book.custom_doc_props
    old_key = LEGACY_PREFIX.upper() + "." + key
    if key not in properties.names and old_key in properties.names:
        properties[old_key].name = key
    if key in properties.names:
        name = properties[key].value
        if name in book.sheetnames:
            return book[name]
    elif book.properties.identifier == MARKER and title in book.sheetnames:
        sheet = book[title]
        if ((title == "최신값" and sheet["A1"].value == HEADERS[0])
                or (title == "HYSYS" and sheet["B2"].value == "선택한 시험 태그의 현재값")):
            properties.append(StringProperty(name=key, value=sheet.title))
            return sheet
    if create:
        sheet = book.create_sheet(title)
        if key in properties.names:
            properties[key].value = sheet.title
        else:
            properties.append(StringProperty(name=key, value=sheet.title))
        return sheet


def save_latest(path, rows, definitions, *, preview=False):
    path = Path(path)
    if path.suffix.lower() != ".xlsx" or not path.parent.is_dir():
        raise ValueError("기존 폴더 안에 .xlsx 파일명을 지정하세요.")
    if not any(row["received_at"] for row in rows):
        return False
    original = path.stat() if path.exists() else None
    if original:
        book = load_workbook(path, rich_text=True)
        if book.properties.identifier == LEGACY_PREFIX.upper() + " " + MARKER:
            book.properties.identifier = MARKER
    else:
        book = Workbook()
        book.remove(book.active)
        book.properties.identifier = MARKER
    sheet = result_sheet(book, "최신값")
    for col, header in enumerate(HEADERS, 1):
        sheet.cell(1, col).value = header
    for row in sheet.iter_rows(min_row=len(rows) + 2, max_row=sheet.max_row, max_col=len(HEADERS)):
        for cell in row:
            cell.value = None
    sheet.freeze_panes = "C2"
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="22613A")
    for i, width in enumerate((22, 27, 20, 12, 18, 37, 37, 18, 37, 36, 46, 50), 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    mapped = [r for r in rows if r["namespace_uri"] == NAMESPACE and r["identifier"] in definitions]
    layout = result_sheet(book, "HYSYS", create=bool(mapped))
    if layout is not None:
        for tag in definitions.values():
            layout[tag["source_cell"]].value = None
        layout["B2"] = "선택한 시험 태그의 현재값"
        layout["B25"] = "설비"
        for row in mapped:
            tag = definitions[row["identifier"]]
            cell = layout[tag["source_cell"]]
            if tag["identifier"].startswith("Stream/"):
                layout.cell(3, cell.column, tag["asset"])
                layout.cell(4, cell.column, tag["fluid"])
                layout.cell(cell.row, 2, tag["metric"])
                layout.cell(cell.row, 3, tag["unit"])
            else:
                layout.cell(26, cell.column, tag["asset"])
                layout.cell(cell.row, 2, tag["metric"] + " (" + tag["unit"] + ")")
            if row["connection"] == "Connected":
                literal(cell, row["value"])
        for col in range(2, 17):
            layout.column_dimensions[get_column_letter(col)].width = 25
        layout.freeze_panes = "D5"
    for i, row in enumerate(rows, 2):
        for j, field in enumerate(FIELDS, 1):
            literal(sheet.cell(i, j), row[field])
    temp = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as f:
            temp = Path(f.name)
        book.save(temp)
        if original:
            if path.stat().st_mtime_ns != original.st_mtime_ns:
                raise OSError("저장 중 대상 파일이 변경되어 이번 저장을 건너뜁니다.")
            os.replace(temp, path)
        else:
            os.link(temp, path)
        if preview:
            return {s.title: list(s.values) for s in (sheet, layout) if s is not None}
    finally:
        book.close()
        if temp:
            temp.unlink(missing_ok=True)
    return True


def hysys_definitions():
    return {"s=" + tag["identifier"]: tag for tag in load_tags()}

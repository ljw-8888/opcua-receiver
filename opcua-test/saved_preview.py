"""Display the receiver-owned sheets from the last successfully saved workbook."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import sys

from openpyxl.utils import get_column_letter
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

class ExcelWindow:
    """All calls run on the same COM thread and target a dedicated workbook."""

    def __init__(self):
        self.app = self.book = None
        self.sheets = []

    def show(self, name, tables):
        from win32com.client import DispatchEx
        if self.app is None:
            self.app = DispatchEx("Excel.Application")
            self.book = self.app.Workbooks.Add(-4167)  # xlWBATWorksheet
            self.sheets = [self.book.Worksheets(1)]
            self.app.Visible = True
        self.book.Windows(1).Caption = name + " · OPC UA 저장값 보기"
        for i, (title, rows) in enumerate(tables.items(), 1):
            if len(self.sheets) < i:
                self.sheets.append(self.book.Worksheets.Add())
            sheet = self.sheets[i - 1]
            resize = sheet.Name != title or sheet.UsedRange.Count == 1
            if sheet.Name != title:
                sheet.Name = title
            # Keep server-provided strings literal when copying into desktop Excel.
            values = tuple(tuple("'" + v if isinstance(v, str) else v for v in row) for row in rows)
            if values:
                target = sheet.Range(sheet.Cells(1, 1), sheet.Cells(len(values), len(values[0])))
                if sheet.UsedRange.Rows.Count > len(values) or sheet.UsedRange.Columns.Count > len(values[0]):
                    sheet.UsedRange.ClearContents()
                target.Value = values
                if resize:
                    target.Columns.AutoFit()
        for sheet in self.sheets[len(tables):]:
            sheet.UsedRange.ClearContents()
        if resize and len(self.sheets) > 1:
            self.sheets[0].Activate()
        self.book.Saved = True

    def close(self):
        if self.app is not None:
            try:
                if self.book is not None:
                    self.book.Close(False)
            except Exception:
                pass  # The operator may already have closed the view.
            try:
                if self.app.Workbooks.Count == 0:
                    self.app.Quit()
            except Exception:
                pass
            self.book = self.app = None
            self.sheets.clear()


class SavedPreview(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Excel 저장값 보기")
        self.resize(1000, 540)
        layout = QVBoxLayout(self)
        self.info = QLabel("첫 저장을 기다리고 있습니다.")
        layout.addWidget(self.info)
        self.sheets = QTabWidget()
        layout.addWidget(self.sheets)
        self.excel = ExcelWindow()
        self.worker = None
        self.show_excel = False
        if sys.platform == "win32":
            button = QPushButton("Microsoft Excel 창으로 보기")
            button.clicked.connect(self.open_excel)
            layout.addWidget(button)
        self.latest = None
        self.task = None

    def open_excel(self):
        self.show_excel = True
        self.refresh()

    def saved(self, path, stamp, tables):
        self.latest = (path, stamp, tables)
        self.refresh()

    def refresh(self):
        if self.latest and (self.isVisible() or self.show_excel) and (not self.task or self.task.done()):
            self.task = asyncio.create_task(self.update_views())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    async def update_views(self):
        while True:
            current = self.latest
            path, stamp, tables = current
            try:
                if self.isVisible():
                    self.render(tables)
                self.info.setText(f"{path.name}   ·   마지막 저장 성공 (UTC)  {stamp}")
                if self.show_excel:
                    try:
                        if self.worker is None:
                            import pythoncom
                            self.worker = ThreadPoolExecutor(1, initializer=pythoncom.CoInitialize)
                        await asyncio.get_running_loop().run_in_executor(self.worker, self.excel.show, path.name, tables)
                    except Exception as exc:
                        self.show_excel = False
                        if self.worker:
                            await asyncio.get_running_loop().run_in_executor(self.worker, self.excel.close)
                        self.info.setText("Excel 창을 열거나 갱신할 수 없습니다. 데스크톱 Excel 설치 및 창 상태를 확인하세요. 아래 표에서 계속 볼 수 있습니다.")
                        self.info.setToolTip(str(exc))
            except Exception as exc:
                self.info.setText(f"저장값 표시 오류: {exc}")
            if current is self.latest:
                return

    def render(self, tables):
        for index, (title, rows) in enumerate(tables.items()):
            table = self.sheets.widget(index)
            fresh = table is None
            if fresh:
                table = QTableWidget()
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                self.sheets.addTab(table, title)
            self.sheets.setTabText(index, title)
            table.setRowCount(len(rows))
            table.setColumnCount(len(rows[0]) if rows else 0)
            if fresh:
                table.setHorizontalHeaderLabels([get_column_letter(i + 1) for i in range(table.columnCount())])
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    text = "" if value is None else str(value)
                    item = table.item(r, c)
                    if item is None:
                        table.setItem(r, c, QTableWidgetItem(text))
                    elif item.text() != text:
                        item.setText(text)
            if fresh:
                table.resizeColumnsToContents()
        while self.sheets.count() > len(tables):
            page = self.sheets.widget(self.sheets.count() - 1)
            self.sheets.removeTab(self.sheets.count() - 1)
            page.deleteLater()

    async def shutdown(self):
        self.hide()
        self.show_excel = False
        if self.task:
            await self.task
        if self.worker:
            await asyncio.get_running_loop().run_in_executor(self.worker, self.excel.close)
            self.worker.shutdown()

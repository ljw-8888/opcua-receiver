"""Windows Excel preview, shared with the desktop receiver."""

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


class DesktopPreview:
    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor
        import pythoncom
        self.worker = ThreadPoolExecutor(1, initializer=pythoncom.CoInitialize)
        self.window = ExcelWindow()
        self.task = None
        self.enabled = True
        self.displayed = None

    async def update(self, preview):
        import asyncio
        name, _, tables = preview
        await asyncio.get_running_loop().run_in_executor(self.worker, self.window.show, name, tables)
        self.displayed = preview

    async def close(self):
        import asyncio
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
        await asyncio.get_running_loop().run_in_executor(self.worker, self.window.close)
        self.worker.shutdown()

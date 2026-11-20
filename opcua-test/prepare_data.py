"""Extract the supplied HYSYS workbook into an auditable test data definition."""

import json
from pathlib import Path
import sys

from openpyxl import load_workbook


def extract(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["Sheet1"]
    metrics = [
        (5, "VaporFraction", "fraction"), (6, "LiquidFraction", "fraction"),
        (7, "Temperature", "degC"), (8, "Pressure", "barG"),
        (9, "MassFlow", "kg/hr"), (10, "VolumeFlow", "m3/hr"),
        (18, "Velocity", "m/s"), (19, "Density", "kg/m3"),
    ]
    tags = []
    for column in range(4, 17):
        stream = str(sheet.cell(3, column).value)
        for row, metric, unit in metrics:
            tag = {
                "identifier": f"Stream/{stream}/{metric}", "asset": f"Stream {stream}",
                "metric": metric, "unit": unit, "baseline": float(sheet.cell(row, column).value),
                "source_cell": sheet.cell(row, column).coordinate,
                "fluid": sheet.cell(4, column).value,
            }
            if metric == "Velocity":
                tag["inner_diameter_mm"] = float(sheet.cell(17, column).value)
            tags.append(tag)
    # The receiver vessel has no equipment ID in the supplied sheet.
    # Keep that omission explicit rather than inventing a plant tag.
    for column, asset, height in [(3, "V-102", 2.2), (4, "Receiver_UNASSIGNED", 1.6)]:
        for row, metric, unit in [(29, "LevelPct", "%"), (30, "LevelM", "m"),
                                  (31, "Pressure", "barG"), (32, "Temperature", "degC")]:
            tag = {
                "identifier": f"Equipment/{asset}/{metric}", "asset": asset,
                "metric": metric, "unit": unit, "baseline": float(sheet.cell(row, column).value),
                "source_cell": sheet.cell(row, column).coordinate,
            }
            if metric == "LevelM":
                tag["height_m"] = height
            tags.append(tag)
    workbook.close()
    assert len(tags) == 112
    return {"source_workbook": Path(path).name, "sheet": "Sheet1", "tags": tags}


if __name__ == "__main__":
    target = Path(__file__).with_name("data.json")
    target.write_text(json.dumps(extract(sys.argv[1]), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {target}")

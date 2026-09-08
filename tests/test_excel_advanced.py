from pathlib import Path

import pandas as pd

from xiaozhi_assistant.tools.office import (
    excel_batch_process_directory,
    excel_calculate_column,
    excel_deduplicate,
    excel_lookup_merge,
    excel_plan_from_instruction,
    excel_split_by_column,
)


def _write(path: Path, rows: list[dict]):
    pd.DataFrame(rows).to_excel(path, index=False)


def test_split_by_column_files(tmp_path: Path):
    src = tmp_path / "sales.xlsx"
    _write(src, [
        {"部门": "销售", "金额": 10},
        {"部门": "财务", "金额": 20},
        {"部门": "销售", "金额": 30},
    ])
    result = excel_split_by_column(str(src), "部门", mode="files")
    assert result["groups"] == 2
    created = [Path(x) for x in result["created"]]
    assert any(x.name == "销售.xlsx" for x in created)
    assert any(x.name == "财务.xlsx" for x in created)
    sales = pd.read_excel(next(x for x in created if x.name == "销售.xlsx"))
    assert sales["金额"].sum() == 40


def test_split_by_column_sheets(tmp_path: Path):
    src = tmp_path / "sales.xlsx"
    _write(src, [{"区域": "华东", "金额": 1}, {"区域": "华南", "金额": 2}])
    result = excel_split_by_column(str(src), "区域", mode="sheets")
    target = Path(result["created"][0])
    book = pd.ExcelFile(target)
    assert {"华东", "华南", "拆分清单"}.issubset(set(book.sheet_names))


def test_calculate_and_deduplicate(tmp_path: Path):
    src = tmp_path / "calc.xlsx"
    _write(src, [
        {"订单号": "A", "金额": 10, "税额": 1},
        {"订单号": "A", "金额": 10, "税额": 1},
        {"订单号": "B", "金额": 20, "税额": 2},
    ])
    calc = excel_calculate_column(str(src), "金额,税额", "含税金额", "sum")
    df = pd.read_excel(calc["file"])
    assert df["含税金额"].tolist() == [11, 11, 22]
    dedup = excel_deduplicate(calc["file"], subset="订单号")
    assert pd.read_excel(dedup["file"]).shape[0] == 2


def test_lookup_merge(tmp_path: Path):
    left = tmp_path / "orders.xlsx"
    right = tmp_path / "customers.xlsx"
    _write(left, [{"订单号": 1, "客户ID": "C1"}, {"订单号": 2, "客户ID": "C2"}])
    _write(right, [{"客户ID": "C1", "客户名称": "甲"}, {"客户ID": "C2", "客户名称": "乙"}])
    result = excel_lookup_merge(str(left), str(right), "客户ID", right_columns="客户名称")
    out = pd.read_excel(result["file"])
    assert out["客户名称"].tolist() == ["甲", "乙"]


def test_local_plan_recognizes_split(tmp_path: Path):
    src = tmp_path / "split.xlsx"
    _write(src, [{"部门": "销售", "金额": 1}, {"部门": "财务", "金额": 2}])
    plan = excel_plan_from_instruction(str(src), "按部门的不同值拆分成多个小表格", allow_ai=False)
    assert plan["source"] == "local_rules"
    assert any(op["op"] == "split_by_column" and op["column"] == "部门" for op in plan["operations"])


def test_batch_process_plan_reused(tmp_path: Path):
    folder = tmp_path / "batch"
    folder.mkdir()
    for i in range(3):
        _write(folder / f"{i}.xlsx", [{"A": 1, "B": 2}, {"A": 3, "B": 4}])
    result = excel_batch_process_directory(str(folder), "每行合计", max_files=10)
    assert result["processed"] == 3
    assert result["failed_count"] == 0

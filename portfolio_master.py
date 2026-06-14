from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
DEFAULT_EXCEL_PATH = ROOT / "outputs" / "yahoo_finance_portfolio_backup.xlsx"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    value = cell.find("x:v", NS)
    if value is None or value.text is None:
        inline = cell.find("x:is/x:t", NS)
        return inline.text if inline is not None and inline.text is not None else ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value.text)]
    return value.text


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("x:si", NS):
        parts = [node.text or "" for node in item.findall(".//x:t", NS)]
        strings.append("".join(parts))
    return strings


def _sheet_path_by_name(zf: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_by_id = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels
        if rel.attrib.get("Id") and rel.attrib.get("Target")
    }
    for sheet in workbook.findall("x:sheets/x:sheet", NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_by_id.get(rel_id or "")
        if not target:
            break
        target = target.lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    raise FileNotFoundError(f"Excel内に「{sheet_name}」シートがありません。")


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def read_excel_master(path: Path = DEFAULT_EXCEL_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"銘柄マスターExcelが見つかりません: {path}")

    with zipfile.ZipFile(path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_path = _sheet_path_by_name(zf, "銘柄検索")
        root = ElementTree.fromstring(zf.read(sheet_path))

    rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", NS):
        values: list[str] = []
        for cell in row.findall("x:c", NS):
            index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append("")
            values[index] = _cell_value(cell, shared_strings)
        rows.append(values)

    if not rows:
        return []

    headers = rows[0]
    index = {name: headers.index(name) for name in headers if name}
    required = ["ポートフォリオ番号", "ポートフォリオ名", "銘柄コード", "名称"]
    missing = [name for name in required if name not in index]
    if missing:
        raise ValueError(f"銘柄検索シートに必要な列がありません: {', '.join(missing)}")

    master_rows = []
    for raw in rows[1:]:
        def get(name: str) -> str:
            pos = index[name]
            return raw[pos].strip() if pos < len(raw) else ""

        symbol = get("銘柄コード")
        if not symbol:
            continue
        portfolio_id = get("ポートフォリオ番号")
        master_rows.append(
            {
                "portfolio_id": int(float(portfolio_id)) if portfolio_id else "",
                "portfolio_name": get("ポートフォリオ名"),
                "symbol": symbol,
                "name": get("名称"),
            }
        )
    return master_rows


def unique_symbols_from_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    symbols = []
    for row in rows:
        symbol = row["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append({"symbol": symbol, "name": row.get("name", "")})
    return symbols


def portfolios_from_rows(rows: list[dict], source_path: Path = DEFAULT_EXCEL_PATH) -> dict:
    portfolios: dict[str, dict] = {}
    for row in rows:
        key = str(row["portfolio_id"])
        portfolio = portfolios.setdefault(
            key,
            {
                "id": row["portfolio_id"],
                "name": row.get("portfolio_name") or f"ポートフォリオ{row['portfolio_id']}",
                "url": "",
                "count_text": "",
                "as_of": "Excel銘柄マスター",
                "symbols": [],
            },
        )
        portfolio["symbols"].append({"symbol": row["symbol"], "name": row.get("name", "")})
    for portfolio in portfolios.values():
        portfolio["count_text"] = f"{len(portfolio['symbols'])}件"
    return {
        "source": f"excel:{source_path}",
        "fetched_at": "",
        "default_portfolio_id": next(iter(portfolios.values()), {}).get("id"),
        "portfolios": list(portfolios.values()),
    }


def load_master_payload(config: dict, base_dir: Path = ROOT) -> tuple[list[dict], dict]:
    source_file = config.get("symbol_source_file") or str(DEFAULT_EXCEL_PATH.relative_to(base_dir))
    path = Path(source_file)
    if not path.is_absolute():
        path = base_dir / path
    rows = read_excel_master(path)
    return unique_symbols_from_rows(rows), portfolios_from_rows(rows, path)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

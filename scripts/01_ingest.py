import io
import sys
import time
from pathlib import Path

import openpyxl
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://storage.dosm.gov.my"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

DOSM_PARQUETS = {
    "hies_state": {
        "path": "hies/hies_state.parquet",
        "columns": {"date", "state", "income_mean", "income_median", "expenditure_mean", "gini", "poverty"},
    },
    "hies_district": {
        "path": "hies/hies_district.parquet",
        "columns": {"date", "state", "district", "income_mean", "income_median", "expenditure_mean", "gini", "poverty"},
    },
    "hies_state_percentile": {
        "path": "hies/hies_state_percentile.parquet",
        "columns": {"date", "state", "percentile", "variable", "income"},
    },
    "hies_malaysia_percentile": {
        "path": "hies/hies_malaysia_percentile.parquet",
        "columns": {"date", "percentile", "variable", "income"},
    },
    "hh_income": {
        "path": "hies/hh_income.parquet",
        "columns": {"date", "income_mean", "income_median"},
    },
    "hh_poverty_state": {
        "path": "hies/hh_poverty_state.parquet",
        "columns": {"state", "date", "poverty_absolute", "poverty_hardcore", "poverty_relative"},
    },
    "cpi_2d_state": {
        "path": "cpi/cpi_2d_state.parquet",
        "columns": {"state", "date", "division", "index"},
    },
    "formal_wages_state": {
        "path": "labour/formal_wages_state.parquet",
        "columns": {"state", "date", "employees", "wages_median"},
    },
}

ALL_STATES = {
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang",
    "Pulau Pinang", "Perak", "Perlis", "Selangor", "Terengganu", "Sabah",
    "Sarawak", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya",
}

MAX_ATTEMPTS = 5
TIMEOUT = 90
# The host resets rapid connections, so requests are paced
DELAY_BETWEEN_REQUESTS = 4.0


def fetch(url):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            last_error = error
            wait_time = attempt * 3
            print(f"[RETRY] {url} attempt {attempt}/{MAX_ATTEMPTS}: {error}. Waiting {wait_time}s...")
            time.sleep(wait_time)
    raise RuntimeError(f"Could not download {url}") from last_error


def sync_parquets(force=False):
    for name, meta in DOSM_PARQUETS.items():
        out_file = RAW_DIR / f"{name}.parquet"
        if out_file.exists() and not force:
            print(f"[SKIP] {name:<26} already in data/raw")
            continue
        content = fetch(f"{BASE_URL}/{meta['path']}")
        df = pd.read_parquet(io.BytesIO(content))
        missing = meta["columns"] - set(df.columns)
        if missing:
            raise ValueError(f"{name}: missing expected columns: {sorted(missing)}")
        if df.empty:
            raise ValueError(f"{name}: downloaded table is empty")
        tmp_file = out_file.with_suffix(".parquet.tmp")
        df.to_parquet(tmp_file, index=False)
        tmp_file.replace(out_file)
        print(f"[OK]   {name:<26} -> data/raw ({df.shape[0]:,} rows)")
        time.sleep(DELAY_BETWEEN_REQUESTS)


def sync_pli_excel(force=False):
    out_file = RAW_DIR / "pli_state.parquet"
    if out_file.exists() and not force:
        print(f"[SKIP] {'pli_state':<26} already in data/raw")
        return
    content = fetch(f"{BASE_URL}/hies/poverty_2024.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True)["1.1"]

    rows = []
    header_found = False
    for row in ws.iter_rows(values_only=True):
        if not header_found:
            header_found = 2022 in row and 2024 in row
            continue
        values = [v for v in row if v is not None]
        if len(values) >= 3 and isinstance(values[0], str):
            state = values[0].strip()
            if state in ALL_STATES or state == "Malaysia":
                rows.append({"state": state, "pli_2022": float(values[1]), "pli_2024": float(values[2])})

    df = pd.DataFrame(rows)
    if len(df) != 17:
        raise ValueError(f"Expected 17 rows (16 states + Malaysia) in pli_state, got {len(df)}")
    df.to_parquet(out_file, index=False)
    print(f"[OK]   {'pli_state':<26} -> data/raw ({len(df)} rows)")
    time.sleep(DELAY_BETWEEN_REQUESTS)


def state_columns(ws):
    """Find the header row of a Table 4.2 sheet; column positions differ by sheet."""
    for r in range(1, 15):
        found = {}
        for c in range(1, ws.max_column + 1):
            value = ws.cell(r, c).value
            if isinstance(value, str):
                name = value.replace("\n", " ").strip()
                if name in ALL_STATES:
                    found[c] = name
                elif name == "Jumlah Total":
                    found[c] = "Malaysia"
        if len(found) >= 3:
            return r, found
    raise ValueError(f"No state header row found in sheet {ws.title}")


def sync_spending_excel(force=False):
    out_file = RAW_DIR / "spending_group_state.parquet"
    if out_file.exists() and not force:
        print(f"[SKIP] {'spending_group_state':<26} already in data/raw")
        return
    content = fetch(f"{BASE_URL}/hies/household_expenditure_2024.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)

    group_codes = {f"{i:02d}" for i in range(1, 14)}
    rows = []
    for sheet in ["4.2 (T1)", "4.2 (T2)", "4.2 (T3)", "4.2 (T4)"]:
        ws = wb[sheet]
        header_row, columns = state_columns(ws)
        for r in range(header_row + 1, ws.max_row + 1):
            labels = [ws.cell(r, c).value for c in range(1, 4)]
            if not any(isinstance(v, str) and v.startswith("Kumpulan") for v in labels):
                continue
            cells = [ws.cell(r, c).value for c in range(2, 6)]
            code_at = next(i for i, v in enumerate(cells) if str(v).strip() in group_codes)
            code = str(cells[code_at]).strip()
            name = next(v for v in cells[code_at + 1:] if v)
            name_en = str(name).split("\n")[-1].strip()
            for c, state in columns.items():
                rows.append({
                    "state": state,
                    "group_code": code,
                    "group_name_en": name_en,
                    "spend_rm": round(float(ws.cell(r, c).value), 2),
                    "share_pct": round(float(ws.cell(r, c + 1).value), 2),
                })

    df = pd.DataFrame(rows)
    if len(df) != 221:
        raise ValueError(f"Expected 221 rows (17 geographies x 13 groups) in spending_group_state, got {len(df)}")
    df.to_parquet(out_file, index=False)
    print(f"[OK]   {'spending_group_state':<26} -> data/raw ({len(df)} rows)")


if __name__ == "__main__":
    force_sync = "--force" in sys.argv
    sync_parquets(force=force_sync)
    sync_pli_excel(force=force_sync)
    sync_spending_excel(force=force_sync)

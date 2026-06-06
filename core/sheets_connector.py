import gspread
from google.oauth2.service_account import Credentials
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *

_COLORS = {
    "yellow": {"red": 1.0,  "green": 0.95, "blue": 0.6},
    "red":    {"red": 0.95, "green": 0.3,  "blue": 0.3},
    "orange": {"red": 1.0,  "green": 0.65, "blue": 0.0},
    "purple": {"red": 0.7,  "green": 0.4,  "blue": 0.9},
    "white":  {"red": 1.0,  "green": 1.0,  "blue": 1.0},
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class SheetsConnector:

    def __init__(self):
        self.client     = None
        self.spreadsheet = None
        self._connect()

    def _connect(self):
        try:
            creds = Credentials.from_service_account_file(
                SHEETS_CREDENTIALS_FILE, scopes=SCOPES
            )
            self.client      = gspread.authorize(creds)
            self.spreadsheet = self.client.open(SHEETS_SPREADSHEET_NAME)
            print("✅ חיבור לגוגל שיטס הצליח")
        except Exception as e:
            print(f"❌ שגיאה בחיבור לגוגל שיטס: {e}")
            self.spreadsheet = None

    def get_sheet(self, sheet_name):
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except Exception as e:
            print(f"❌ שגיאה בפתיחת לשונית {sheet_name}: {e}")
            return None

    def read_all(self, sheet_name):
        try:
            sheet = self.get_sheet(sheet_name)
            if sheet is None:
                return []
            return sheet.get_all_records()
        except Exception as e:
            print(f"❌ שגיאה בקריאה מ-{sheet_name}: {e}")
            return []

    def append_row(self, sheet_name, row_data):
        try:
            sheet = self.get_sheet(sheet_name)
            if sheet is None:
                return False
            sheet.append_row(row_data)
            return True
        except Exception as e:
            print(f"❌ שגיאה בהוספת שורה ל-{sheet_name}: {e}")
            return False

    def update_cell(self, sheet_name, row, col, value):
        try:
            sheet = self.get_sheet(sheet_name)
            if sheet is None:
                return False
            sheet.update_cell(row, col, value)
            return True
        except Exception as e:
            print(f"❌ שגיאה בעדכון תא: {e}")
            return False

    def get_headers(self, sheet_name):
        try:
            sheet = self.get_sheet(sheet_name)
            return sheet.row_values(1) if sheet else []
        except Exception:
            return []

    def get_sheet_data_with_rows(self, sheet_name):
        try:
            sheet = self.get_sheet(sheet_name)
            if not sheet:
                return []
            all_vals = sheet.get_all_values()
            if len(all_vals) < 2:
                return []
            headers = all_vals[0]
            result  = []
            for i, row in enumerate(all_vals[1:], start=2):
                padded = row + [""] * (len(headers) - len(row))
                record = dict(zip(headers, padded))
                record["__row__"] = i
                result.append(record)
            return result
        except Exception as e:
            print(f"Error reading {sheet_name} with rows: {e}")
            return []

    def ensure_columns(self, sheet_name, required_cols):
        try:
            sheet    = self.get_sheet(sheet_name)
            if not sheet:
                return
            existing = sheet.row_values(1)
            if not existing:
                sheet.update("A1", [required_cols])
                return
            missing  = [c for c in required_cols if c not in existing]
            if not missing:
                return
            start = len(existing) + 1
            for i, col in enumerate(missing):
                sheet.update_cell(1, start + i, col)
        except Exception as e:
            print(f"Error ensuring columns in {sheet_name}: {e}")

    def highlight_row(self, sheet_name, row_num, color_name):
        try:
            sheet = self.get_sheet(sheet_name)
            if not sheet:
                return
            color = _COLORS.get(color_name, _COLORS["white"])
            sheet.format(f"A{row_num}:Z{row_num}", {"backgroundColor": color})
        except Exception as e:
            print(f"Error highlighting row {row_num} in {sheet_name}: {e}")

    def highlight_cell_by_col(self, sheet_name, row_num, col_name, color_name):
        try:
            sheet   = self.get_sheet(sheet_name)
            if not sheet:
                return
            headers = sheet.row_values(1)
            if col_name not in headers:
                return
            col_idx = headers.index(col_name) + 1
            cell    = gspread.utils.rowcol_to_a1(row_num, col_idx)
            color   = _COLORS.get(color_name, _COLORS["white"])
            sheet.format(cell, {"backgroundColor": color})
        except Exception as e:
            print(f"Error highlighting cell {col_name}@{row_num} in {sheet_name}: {e}")

    def update_row_fields(self, sheet_name, row_num, fields_dict):
        try:
            sheet   = self.get_sheet(sheet_name)
            if not sheet:
                return
            headers = sheet.row_values(1)
            for col_name, value in fields_dict.items():
                if col_name not in headers:
                    continue
                col_idx = headers.index(col_name) + 1
                sheet.update_cell(row_num, col_idx, value)
        except Exception as e:
            print(f"Error updating row {row_num} in {sheet_name}: {e}")

    def delete_row(self, sheet_name, row_num):
        try:
            sheet = self.get_sheet(sheet_name)
            if sheet:
                sheet.delete_rows(row_num)
        except Exception as e:
            print(f"Error deleting row {row_num} in {sheet_name}: {e}")

    def color_cell(self, sheet_name, row, col, color):
        try:
            sheet = self.get_sheet(sheet_name)
            if sheet is None:
                return False
            sheet.format(
                gspread.utils.rowcol_to_a1(row, col),
                {"backgroundColor": color}
            )
            return True
        except Exception as e:
            print(f"❌ שגיאה בצביעת תא: {e}")
            return False

    def append_note_to_pending(self, ticker: str, note: str):
        sheet = self.client.open_by_key(self.sheet_id).worksheet(self.config.SHEET_PENDING)
        rows = sheet.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0] == ticker:
                current = sheet.cell(i, 8).value or ""
                sheet.update_cell(i, 8, (current + " " + note).strip())
                return

    def upsert_pending_order(self, row_dict: dict) -> str:
        ticker = row_dict.get("Ticker")
        if not ticker:
            raise ValueError("row_dict must contain 'Ticker'")

        rows = self.get_sheet_data_with_rows(SHEET_PENDING)

        for row in rows:
            if str(row.get("Ticker", "")).upper() == ticker.upper():
                self.update_row_fields(SHEET_PENDING, row["__row__"], row_dict)
                return "updated"

        sheet = self.get_sheet(SHEET_PENDING)
        if sheet is None:
            return "error"
        headers = sheet.row_values(1)
        new_row = [row_dict.get(h, "") for h in headers]
        sheet.append_row(new_row, value_input_option="USER_ENTERED")
        return "appended"
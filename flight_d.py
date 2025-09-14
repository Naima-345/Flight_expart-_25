import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime, date

DB_PATH = "flights.db"
JSON_PATH = "flight_data.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  flight_name     TEXT NOT NULL,
  travel_date     TEXT NOT NULL,      -- YYYY-MM-DD (normalized)
  origin          TEXT NOT NULL,      -- IATA (e.g., ICN)
  destination     TEXT NOT NULL,      -- IATA (e.g., BER)
  departure_time  TEXT,               -- ISO8601 or NULL
  arrival_time    TEXT,               -- ISO8601 or NULL
  UNIQUE (flight_name, travel_date, departure_time) ON CONFLICT IGNORE
);
CREATE INDEX IF NOT EXISTS idx_flights_route_date ON flights(origin, destination, travel_date);
CREATE INDEX IF NOT EXISTS idx_flights_date       ON flights(travel_date);
"""

# ---- Date normalization (only change you asked for) ----
# Change this if you want to store in a different string format
OUTPUT_DATE_FMT = "%Y-%m-%d"

_ISO_DATE_RE     = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLASHED_RE      = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")   # DD/MM/YYYY or MM/DD/YYYY
_DASHED_DMY_RE   = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")   # DD-MM-YYYY
_YMD_SLASH_RE    = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")   # YYYY/MM/DD

def iso_date(s: str | None, *, output_fmt: str = OUTPUT_DATE_FMT, day_first: bool = True) -> str | None:
    """
    Normalize various date strings to `output_fmt` (default YYYY-MM-DD).
    Supports:
      - YYYY-MM-DD
      - ISO datetimes (e.g., 2025-09-08T16:30:00Z or +00:00)
      - DD/MM/YYYY and MM/DD/YYYY (uses heuristic + day_first preference)
      - DD-MM-YYYY
      - YYYY/MM/DD
    Returns None if parsing fails.
    """
    if not s:
        return None
    s = s.strip()

    # Pure ISO date
    if _ISO_DATE_RE.match(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime(output_fmt)
        except ValueError:
            return None

    # ISO datetime (accept 'Z')
    if "T" in s:
        try:
            zfixed = s.replace("Z", "+00:00")
            return datetime.fromisoformat(zfixed).date().strftime(output_fmt)
        except ValueError:
            pass

    # DD/MM/YYYY or MM/DD/YYYY
    m = _SLASHED_RE.match(s)
    if m:
        a, b, y = map(int, m.groups())
        if a > 12 and b <= 12:
            day, month = a, b
        elif b > 12 and a <= 12:
            day, month = b, a
        else:
            # ambiguous -> choose based on preference
            day, month = (a, b) if day_first else (b, a)
        try:
            return date(y, month, day).strftime(output_fmt)
        except ValueError:
            return None

    # DD-MM-YYYY
    m = _DASHED_DMY_RE.match(s)
    if m:
        d, mth, y = map(int, m.groups())
        try:
            return date(y, mth, d).strftime(output_fmt)
        except ValueError:
            return None

    # YYYY/MM/DD
    m = _YMD_SLASH_RE.match(s)
    if m:
        y, mth, d = map(int, m.groups())
        try:
            return date(y, mth, d).strftime(output_fmt)
        except ValueError:
            return None

    return None
# --------------------------------------------------------

def make_flight_name(item: dict) -> str:
    airline = ((item.get("airline") or {}).get("name") or "Unknown").strip()
    fl = item.get("flight") or {}
    no = (fl.get("iata") or fl.get("number") or "").strip()
    return (airline + (" " + no if no else "")).strip()

def insert_from_json(cur: sqlite3.Cursor, item: dict) -> None:
    dep = item.get("departure") or {}
    arr = item.get("arrival") or {}
    origin = (dep.get("iata") or "").strip().upper()
    destination = (arr.get("iata") or "").strip().upper()

    # date: prefer item.flight_date, else derive from departure.scheduled/estimated
    date_raw = item.get("flight_date") or dep.get("scheduled") or dep.get("estimated")
    travel_date = iso_date(date_raw)

    if not (origin and destination and travel_date):
        return  # skip incomplete rows

    flight_name = make_flight_name(item)
    departure_time = dep.get("scheduled") or dep.get("estimated")
    arrival_time = arr.get("scheduled") or arr.get("estimated")

    cur.execute(
        """INSERT OR IGNORE INTO flights
           (flight_name, travel_date, origin, destination, departure_time, arrival_time)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (flight_name, travel_date, origin, destination, departure_time, arrival_time),
    )

def main():
    if not Path(JSON_PATH).exists():
        raise SystemExit(f"❌ No JSON found at {JSON_PATH}")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f).get("data", [])

    if not data:
        print("ℹ️ No flights in JSON.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        cur = conn.cursor()
        before = conn.total_changes
        for item in data:
            insert_from_json(cur, item)
        conn.commit()
        added = conn.total_changes - before
        print(f"✅ Inserted {added}/{len(data)} flights into {DB_PATH} (duplicates ignored).")
    finally:
        conn.close()

if __name__ == "__main__":
    main()

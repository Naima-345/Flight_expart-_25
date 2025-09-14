from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted, FollowupAction
import json
import os
import sqlite3
from datetime import datetime
import re
from pathlib import Path

# --- Allowed countries loader (unchanged) ---

def load_allowed_countries() -> Dict[str, str]:
    json_path = os.path.join(os.path.dirname(__file__), '..', 'allowed_countries.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        airports = json.load(f)

    # Build a dict: City → IATA
    city_to_iata = {}
    for airport, info in airports.items():
        city = info.get("city")
        iata = info.get("iata")
        if city and iata:
            city_to_iata[city.title()] = iata.upper()
    return city_to_iata

CITY_TO_IATA = load_allowed_countries()
ALLOWED_COUNTRIES = CITY_TO_IATA  # alias
ALLOWED_COUNTRIES_SET = set(CITY_TO_IATA.keys())

def validate_country(country: str) -> bool:
    """Return True if the user-provided city is allowed"""
    return bool(country) and country.strip().title() in ALLOWED_COUNTRIES_SET

def format_country_list() -> str:
    """Return a nicely formatted string of allowed cities"""
    return "\n".join(f"• {city}" for city in sorted(ALLOWED_COUNTRIES_SET))

# If you want to override via env, set FLIGHTS_DB=/path/to/flights.db
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FLIGHTS_DB_PATH = os.getenv("FLIGHTS_DB") or str(PROJECT_ROOT / "flights.db")
print(f"[actions] Using flights DB at: {FLIGHTS_DB_PATH}")

NEARBY_BY_IATA: Dict[str, List[str]] = {
    "BNE": ["OOL"],                 # Brisbane -> also check Gold Coast
    "ICN": ["GMP"], "GMP": ["ICN"], # Seoul metro example
}

def _city_to_iata(name: str) -> str:
    """Map a city to its IATA; fallback to uppercased input."""
    key = (name or "").strip().title()
    return CITY_TO_IATA.get(key, (name or "").strip().upper())

def _expand_iata_candidates(name: str) -> List[str]:
    primary = _city_to_iata(name)
    if not primary:
        return []
    out = [primary] + NEARBY_BY_IATA.get(primary, [])
    seen, result = set(), []
    for c in out:
        if c and c not in seen:
            result.append(c); seen.add(c)
    return result

# Strict DD/MM/YYYY matcher
_DDMMYYYY_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Small helper to render flight lines
def _format_flights_message(rows: List[tuple], origin: str, destination: str, date_str: str) -> str:
    """
    rows: (flight_name, departure_time, arrival_time)
    """
    if not rows:
        return f"⚠️ No flights found for {origin} → {destination} on {date_str}."
    lines = [f"✈️ Flights for {origin} → {destination} on {date_str}:"]
    for i, (fname, dep, arr) in enumerate(rows, start=1):
        lines.append(f"{i}. {fname}  |  Dep: {dep}  →  Arr: {arr}")
    return "\n".join(lines)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLASHED_RE  = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

def _to_iso_from_ddmmyyyy(s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if _ISO_DATE_RE.match(s):
        return s
    m = _SLASHED_RE.match(s)
    if m:
        d, mth, y = map(int, m.groups())
        try:
            return datetime(y, mth, d).date().isoformat()
        except ValueError:
            return None
    return None

def _query_flights_for_date(origin: str, destination: str, travel_date: str) -> List[tuple]:
    """
    Returns rows: (flight_name, departure_time, arrival_time)
    Uses columns: travel_date, origin, destination (matching your DB)
    """
    date_iso = _to_iso_from_ddmmyyyy(travel_date)
    if not date_iso:
        return []

    origin_codes = _expand_iata_candidates(origin)   # e.g., ['BNE','OOL']
    dest_codes   = _expand_iata_candidates(destination)
    if not origin_codes or not dest_codes:
        return []

    o_pl = ",".join("?" for _ in origin_codes)
    d_pl = ",".join("?" for _ in dest_codes)
    params = [date_iso, *origin_codes, *dest_codes]

    sql = f"""
        SELECT flight_name, departure_time, arrival_time
        FROM flights
        WHERE travel_date = ?
          AND origin IN ({o_pl})
          AND destination IN ({d_pl})
        ORDER BY (departure_time IS NULL), departure_time
        LIMIT 5
    """

    try:
        conn = sqlite3.connect(FLIGHTS_DB_PATH)
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            print(f"[actions] 0 flights for date={date_iso} origin={origin_codes} dest={dest_codes}")
        return rows or []
    except Exception as e:
        print(f"[actions] DB query error: {e} (db={FLIGHTS_DB_PATH})")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

# --- DB helpers (BOOKINGS + PASSENGERS with per-passenger seat) ---
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'bookings.db')

def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT,
                destination TEXT,
                travel_date TEXT,
                seat_preference TEXT,      -- (legacy/global; optional)
                class_selection TEXT,
                passenger_name TEXT,       -- primary contact
                phone_number TEXT,         -- primary contact
                travel_count INTEGER,
                return_date TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passengers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER,
                name TEXT,
                phone TEXT,
                email TEXT,
                seat_preference TEXT,      -- per-passenger seat
                FOREIGN KEY(booking_id) REFERENCES bookings(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

def _save_booking(row: Dict[str, Any]) -> int:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
         INSERT INTO bookings
            (origin, destination, travel_date,return_date, seat_preference, class_selection,
            passenger_name, phone_number, travel_count, created_at)
            VALUES (:origin, :destination, :travel_date, :flight_name, :flight_schedule_time, :return_date, :seat_preference, :class_selection,
            :passenger_name, :phone_number, :travel_count, :created_at)
            """,
            {**row, "created_at": datetime.utcnow().isoformat()}
        )
        booking_id = cur.lastrowid
        conn.commit()
        return booking_id
    finally:
        conn.close()

def _save_passengers(booking_id: int, passengers: List[Dict[str, str]]):
    if not passengers:
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executemany(
            "INSERT INTO passengers (booking_id, name, phone, email, seat_preference) VALUES (?, ?, ?, ?, ?)",
            [
                (booking_id, p.get("name",""), p.get("phone",""), p.get("email",""), p.get("seat",""))
                for p in passengers
            ]
        )
        conn.commit()
    finally:
        conn.close()

# ------------------- FORM VALIDATION -------------------

class ValidateFlightBookingForm(FormValidationAction):

    def name(self) -> Text:
        return "validate_flight_booking_form"

    def _normalize_country(self, value: Optional[Text]) -> Optional[Text]:
        return value.strip().title() if value else value

    # >>> helper to parse "from X to Y" or "X to Y"
    def _parse_from_to(self, text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract (origin, destination) from text like:
        - "from Bangladesh to Canada"
        - "Bangladesh to Canada"
        """
        if not text:
            return None, None

        s = text.strip()
        m = re.match(r"^\s*from\s+(.+?)\s+to\s+(.+?)\s*$", s, flags=re.IGNORECASE)
        if m:
            o = m.group(1).strip().title()
            d = m.group(2).strip().title()
            return o, d

        m2 = re.match(r"^\s*(.+?)\s+to\s+(.+?)\s*$", s, flags=re.IGNORECASE)
        if m2:
            o = m2.group(1).strip().title()
            d = m2.group(2).strip().title()
            return o, d

        return None, None

    # ---------------------------
    # Origin / Destination
    # ---------------------------

    def validate_origin(self, value, dispatcher, tracker, domain):
        o, d = self._parse_from_to(value)
        if o and d and validate_country(o) and validate_country(d):
            if o == d:
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose different places.")
                return {"origin": None}
            dispatcher.utter_message(text=f"Got it ✅ Origin: {o}, Destination: {d}.")
            return {"origin": o, "destination": d}

        norm = self._normalize_country(value)
        if validate_country(norm):
            dest = tracker.get_slot("destination")
            if dest and norm == self._normalize_country(dest):
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose a different origin.")
                return {"origin": None}
            return {"origin": norm}

        dispatcher.utter_message(
            text=f"Sorry, '{value}' is not supported.\nChoose origin from:\n{format_country_list()}"
        )
        return {"origin": None}

    def validate_destination(self, value, dispatcher, tracker, domain):
        o, d = self._parse_from_to(value)
        if o and d and validate_country(o) and validate_country(d):
            if o == d:
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose different places.")
                return {"destination": None}
            dispatcher.utter_message(text=f"Got it ✅ Origin: {o}, Destination: {d}.")
            return {"origin": o, "destination": d}

        if not d:
            norm = self._normalize_country(value)
            if validate_country(norm):
                origin = tracker.get_slot("origin")
                if origin and norm == self._normalize_country(origin):
                    dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose a different destination.")
                    return {"destination": None}
                return {"destination": norm}
            dispatcher.utter_message(
                text=f"Sorry, '{value}' is not supported.\nChoose destination from:\n{format_country_list()}"
            )
            return {"destination": None}

        if validate_country(d):
            origin = tracker.get_slot("origin")
            if origin and self._normalize_country(origin) == d:
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose a different destination.")
                return {"destination": None}
            return {"destination": d}

        dispatcher.utter_message(
            text=f"Sorry, '{value}' is not supported.\nChoose destination from:\n{format_country_list()}"
        )
        return {"destination": None}

    # ---------------------------
    # Travel date (simple only)
    @staticmethod
    def required_slots(domain_slots: List[Text], dispatcher, tracker, domain) -> List[Text]:
        """If no_flights is True, end the form immediately (no more slots)."""
        if tracker.get_slot("no_flights"):
            return []
        return domain_slots

    def validate_travel_date(self, value, dispatcher, tracker, domain):
        # Must be DD/MM/YYYY
        if not _DDMMYYYY_RE.match(value or ""):
            dispatcher.utter_message(text="❌ Please enter the date in DD/MM/YYYY format (e.g., 15/09/2025).")
            return {"travel_date": None}

        # No past dates
        try:
            dt = datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            dispatcher.utter_message(text="❌ Invalid date. Please check the day, month, and year.")
            return {"travel_date": None}

        if dt < datetime.utcnow().date():
            dispatcher.utter_message(text="⚠️ Past dates aren’t allowed. Please choose a future date.")
            return {"travel_date": None}

        origin = tracker.get_slot("origin")
        destination = tracker.get_slot("destination")

        # If places aren’t set yet, just store date
        if not origin or not destination:
            return {"travel_date": value}

        # Check DB
        rows = _query_flights_for_date(origin, destination, value)
        print(f"[validate_travel_date] origin={origin!r} dest={destination!r} date={value!r} rows_found={len(rows)}")

        if not rows:
            # Mark to end form; submit will handle apology/restart
            return {
                "travel_date": value,
                "no_flights": True,
            }

        # Flights exist → show, keep going
        dispatcher.utter_message(text=_format_flights_message(rows, origin, destination, value))
        return {
            "travel_date": value,
            "no_flights": False,
        }


    def validate_class_selection(self, value, dispatcher, tracker, domain):
        v = (value or "").lower().strip()
        if v in {"economy", "business", "first"}:
            return {"class_selection": v}
        dispatcher.utter_message(text="Please choose a class: economy, business, or first.")
        return {"class_selection": None}

    def validate_return_date(self, value, dispatcher, tracker, domain):
        pattern = r"^\d{2}/\d{2}/\d{4}$"
        if not re.match(pattern, value or ""):
            dispatcher.utter_message(text="❌ Please enter the date in DD/MM/YYYY format (e.g., 15/09/2025).")
            return {"return_date": None}
        try:
            dep = tracker.get_slot("travel_date")
            dep_dt = datetime.strptime(dep, "%d/%m/%Y").date() if dep else None
            ret_dt = datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            dispatcher.utter_message(text="❌ Invalid date. Please check the day, month, and year.")
            return {"return_date": None}
        today = datetime.utcnow().date()
        if ret_dt < today:
            dispatcher.utter_message(text="❌ Return date cannot be in the past. Please choose a future date.")
            return {"return_date": None}
        if dep_dt and ret_dt < dep_dt:
            dispatcher.utter_message(text="❌ Return date cannot be before the travel date. Please choose a valid return date.")
            return {"return_date": None}
        return {"return_date": value}

    def validate_passenger_name(self, value, dispatcher, tracker, domain):
        if value and value.strip():
            return {"passenger_name": value.strip()}
        dispatcher.utter_message(text="Please enter the main passenger's name.")
        return {"passenger_name": None}

    def validate_travel_count(self, value, dispatcher, tracker, domain):
        if value and str(value).strip().isdigit():
            n = int(str(value).strip())
            if n >= 1:
                return {
                    "travel_count": n,
                    "expected_passengers": n,
                    "current_passenger_index": 1,
                    "passengers": json.dumps([]),
                    "current_passenger_name": None,
                    "current_passenger_phone": None,
                    "current_passenger_email": None,
                    "current_passenger_seat_preference": None,
                }
        dispatcher.utter_message(text="Please enter a valid number of travelers (e.g., 1, 2, 3).")
        return {"travel_count": None}

    def validate_current_passenger_name(self, value, dispatcher, tracker, domain):
        if value and value.strip():
            return {"current_passenger_name": value.strip()}
        idx = tracker.get_slot("current_passenger_index") or 1
        dispatcher.utter_message(text=f"Please enter passenger {idx}'s full name.")
        return {"current_passenger_name": None}

    def validate_current_passenger_phone(self, value, dispatcher, tracker, domain):
        if value and (re.fullmatch(r"\+?[1-9]\d{7,14}", value) or re.fullmatch(r"[0-9\-+ ]{7,15}", value)):
            return {"current_passenger_phone": value}
        idx = tracker.get_slot("current_passenger_index") or 1
        dispatcher.utter_message(text=f"Please enter a valid phone number for passenger {idx} (e.g., +15551234567).")
        return {"current_passenger_phone": None}

    def validate_current_passenger_email(self, value, dispatcher, tracker, domain):
        if value and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
            return {"current_passenger_email": value.strip()}
        idx = tracker.get_slot("current_passenger_index") or 1
        dispatcher.utter_message(text=f"Please enter a valid email for passenger {idx} (e.g., name@example.com).")
        return {"current_passenger_email": None}

    def validate_current_passenger_seat_preference(self, value, dispatcher, tracker, domain):
        v = (value or "").lower().strip()
        if v in {"window", "aisle", "middle"}:
            # Collect all current passenger fields
            name  = tracker.get_slot("current_passenger_name")
            phone = tracker.get_slot("current_passenger_phone")
            email = tracker.get_slot("current_passenger_email")
            idx   = int(tracker.get_slot("current_passenger_index") or 1)
            expected = int(tracker.get_slot("expected_passengers") or 1)

            # Load current list
            passengers_json = tracker.get_slot("passengers") or "[]"
            try:
                passengers: List[Dict[str, str]] = json.loads(passengers_json)
            except Exception:
                passengers = []

            # Append this passenger (all 4 fields present now)
            if all([name, phone, email, v]):
                passengers.append({"name": name, "phone": phone, "email": email, "seat": v})

            # Advance or finish
            if idx < expected:
                next_idx = idx + 1
                dispatcher.utter_message(text=f"Got it ✅. Now, please provide details for passenger {next_idx}.")
                return {
                    "passengers": json.dumps(passengers),
                    "current_passenger_index": next_idx,
                    # clear fields for the next passenger
                    "current_passenger_name": None,
                    "current_passenger_phone": None,
                    "current_passenger_email": None,
                    "current_passenger_seat_preference": None,
                }

            # Done collecting; keep seat set so the form can complete
            return {
                "passengers": json.dumps(passengers),
                "current_passenger_seat_preference": v,
            }

        idx = tracker.get_slot("current_passenger_index") or 1
        dispatcher.utter_message(text=f"Please choose seat for passenger {idx}: window, aisle, or middle.")
        return {"current_passenger_seat_preference": None}


class ActionBookFlight(Action):
    def name(self) -> Text:
        return "action_book_flight"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Booking your flight now!")
        return []

# =========================
# LOOKUP HELPERS & ACTIONS
# =========================

class ActionAskLookup(Action):
    """Prompts the user for a booking id or phone number."""
    def name(self) -> Text:
        return "action_ask_lookup"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict]:
        dispatcher.utter_message(text="Please share your booking ID or the phone number used for the booking.")
        return []

def _get_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]

def _row_to_dict(row: tuple, cols: List[str]) -> Dict[str, Any]:
    return {col: row[i] for i, col in enumerate(cols)}

class ActionLookupBooking(Action):
    """Looks up a booking by booking ID (int) or phone number (partial match)."""
    def name(self) -> Text:
        return "action_lookup_booking"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict]:
        query = (tracker.latest_message.get("text") or "").strip()
        if not query:
            dispatcher.utter_message(text="Please provide a booking ID or phone number.")
            return []

        try:
            conn = sqlite3.connect(DB_PATH)
        except Exception as e:
            dispatcher.utter_message(text=f"⚠️ Could not open database: {e}")
            return []

        try:
            bcols = _get_table_columns(conn, "bookings")
            pcols = _get_table_columns(conn, "passengers")
            cur = conn.cursor()

            # Try booking id
            booking_row = None
            try:
                bid = int(query)
                if "id" in bcols:
                    cur.execute(f"SELECT {', '.join(bcols)} FROM bookings WHERE id = ?", (bid,))
                    row = cur.fetchone()
                    if row:
                        booking_row = _row_to_dict(row, bcols)
            except Exception:
                pass

            # Fallback: phone partial match
            if not booking_row and "phone_number" in bcols:
                cur.execute(
                    f"SELECT {', '.join(bcols)} FROM bookings WHERE phone_number LIKE ?",
                    (f"%{query}%",)
                )
                row = cur.fetchone()
                if row:
                    booking_row = _row_to_dict(row, bcols)

            if not booking_row:
                dispatcher.utter_message(text="Sorry, I couldn't find a booking with that information.")
                return []

            # Fetch passengers
            pax_lines = "   (no additional passengers)"
            if "id" in booking_row:
                cols_to_select = [c for c in ["name", "phone", "email", "seat_preference"] if c in pcols]
                if cols_to_select:
                    cur.execute(
                        f"SELECT {', '.join(cols_to_select)} FROM passengers WHERE booking_id = ?",
                        (booking_row["id"],)
                    )
                    fetched = cur.fetchall()
                    if fetched:
                        idx = {c: i for i, c in enumerate(cols_to_select)}
                        lines = []
                        for r in fetched:
                            name  = r[idx["name"]]  if "name"  in idx else "N/A"
                            phone = r[idx["phone"]] if "phone" in idx else "N/A"
                            email = r[idx["email"]] if "email" in idx else "N/A"
                            seat  = r[idx["seat_preference"]] if "seat_preference" in idx else "(no seat)"
                            lines.append(f"   - {name} | {phone} | {email} | Seat: {seat}")
                        pax_lines = "\n".join(lines)

            g = lambda k, d="N/A": booking_row.get(k, d)

            msg = (
                f"🔎 Booking #{g('id')}\n"
                f"📍 {g('origin')} → {g('destination')}\n"
                f"📅 Dates: {g('travel_date')} → {g('return_date', 'N/A')}\n"
                f"🎫 Class: {g('class_selection')}\n"
                f"👤 Primary: {g('passenger_name')}\n"
                f"👥 Travelers: {g('travel_count', 1)}\n"
                f"🪑 Seat (global): {g('seat_preference', 'N/A')}\n"
                f"📜 Passengers:\n{pax_lines}"
            )
            dispatcher.utter_message(text=msg)
            return []
        except Exception as e:
            dispatcher.utter_message(text=f"⚠️ Lookup failed: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

class ActionSubmitBooking(Action):
    def name(self) -> str:
        return "action_submit_booking"

    def run(self, dispatcher, tracker, domain):
        # If you’re using no_flights logic elsewhere, handle it gracefully
        if tracker.get_slot("no_flights"):
            origin = tracker.get_slot("origin") or "N/A"
            destination = tracker.get_slot("destination") or "N/A"
            travel_date = tracker.get_slot("travel_date") or "N/A"
            dispatcher.utter_message(
                text=f"😔 Sorry, no flights for {origin} → {destination} on {travel_date}. "
                     f"Please change your travel date or destination and try again."
            )
            # End the session so the form doesn’t keep asking
            return [Restarted()]

        # Build the DB row with only the columns your schema needs.
        # (flight_name / flight_schedule_time removed since you don’t keep those slots.)
        row = {
            "origin": tracker.get_slot("origin") or "N/A",
            "destination": tracker.get_slot("destination") or "N/A",
            "travel_date": tracker.get_slot("travel_date") or "N/A",
            "return_date": tracker.get_slot("return_date") or "N/A",
            "seat_preference": "N/A",
            "class_selection": tracker.get_slot("class_selection") or "N/A",
            "passenger_name": tracker.get_slot("passenger_name") or "N/A",
            "phone_number": "N/A",
            "travel_count": tracker.get_slot("travel_count") or 1,
        }

        passengers_json = tracker.get_slot("passengers") or "[]"
        try:
            passengers = json.loads(passengers_json)
        except Exception:
            passengers = []

        try:
            booking_id = _save_booking(row)
            _save_passengers(booking_id, passengers)
            saved_msg = f"💾 Booking #{booking_id} saved with {len(passengers)} passenger(s)."
        except Exception as e:
            saved_msg = f"⚠️ Could not save booking to database: {e}"

        pax_lines = "\n".join(
            [
                f"   {i+1}. {p.get('name','N/A')} | {p.get('phone','N/A')} | "
                f"{p.get('email','N/A')} | Seat: {p.get('seat','N/A')}"
                for i, p in enumerate(passengers)
            ]
        ) or "   (no additional passengers)"

        dispatcher.utter_message(
            text=(
                f"✅ Booking Confirmed!\n\n"
                f"📍 From → To: {row['origin']} → {row['destination']}\n"
                f"📅 Date: {row['travel_date']} → {row['return_date']}\n"
                f"🎫 Class: {row['class_selection']}\n"
                f"👤 Primary Contact: {row['passenger_name']}\n"
                f"👥 Travelers: {row['travel_count']}\n"
                f"🪑 Seats: per passenger below\n"
                f"📜 Passenger List:\n{pax_lines}\n\n"
                f"{saved_msg}"
            )
        )

        # Clear ONLY the slots that exist in your domain
        return [
            SlotSet("origin", None),
            SlotSet("destination", None),
            SlotSet("travel_date", None),
            SlotSet("return_date", None),
            SlotSet("class_selection", None),
            SlotSet("passenger_name", None),
            SlotSet("travel_count", None),
            SlotSet("expected_passengers", None),
            SlotSet("current_passenger_index", None),
            SlotSet("current_passenger_name", None),
            SlotSet("current_passenger_phone", None),
            SlotSet("current_passenger_email", None),
            SlotSet("current_passenger_seat_preference", None),
            SlotSet("passengers", None),
            SlotSet("no_flights", None),
        ]


class ActionCache(Action):
    def name(self) -> str:
        return "action_cache"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        dispatcher.utter_message(json_message={"clear_chat": True})
        return [Restarted(), FollowupAction(name="utter_greet")]

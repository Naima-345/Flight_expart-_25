from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted, FollowupAction
import json
import os
import sqlite3
from datetime import datetime
import re

# --- Allowed countries loader (unchanged) ---
def load_allowed_countries() -> List[str]:
    json_path = os.path.join(os.path.dirname(__file__), '..', 'allowed_countries.json')
    with open(json_path, 'r') as f:
        return json.load(f)

ALLOWED_COUNTRIES = load_allowed_countries()
ALLOWED_COUNTRIES_SET = {c.strip().title() for c in ALLOWED_COUNTRIES}

def validate_country(country: str) -> bool:
    return bool(country) and country.strip().title() in ALLOWED_COUNTRIES_SET

def format_country_list() -> str:
    return "\n".join(f"• {country}" for country in sorted(ALLOWED_COUNTRIES_SET))

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
                flight_time TEXT,
                seat_preference TEXT,      -- (legacy/global; optional)
                class_selection TEXT,
                passenger_name TEXT,       -- primary contact
                phone_number TEXT,         -- primary contact
                travel_count INTEGER,
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
            (origin, destination, travel_date, flight_time, seat_preference, class_selection,
             passenger_name, phone_number, travel_count, created_at)
            VALUES (:origin, :destination, :travel_date, :flight_time, :seat_preference, :class_selection,
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
    # def name(self) -> Text:
    #     return "validate_flight_booking_form"

    # def _normalize_country(self, value: Optional[Text]) -> Optional[Text]:
    #     return value.strip().title() if value else value

    # # Origin / Destination
    # def validate_origin(self, value, dispatcher, tracker, domain):
    #     norm = self._normalize_country(value)
    #     if validate_country(norm):
    #         dest = tracker.get_slot("destination")
    #         if dest and norm == self._normalize_country(dest):
    #             dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose a different origin.")
    #             return {"origin": None}
    #         return {"origin": norm}
    #     dispatcher.utter_message(
    #         text=f"Sorry, '{value}' is not supported.\nChoose origin from:\n{format_country_list()}"
    #     )
    #     return {"origin": None}

    # def validate_destination(self, value, dispatcher, tracker, domain):
    #     norm = self._normalize_country(value)
    #     if validate_country(norm):
    #         origin = tracker.get_slot("origin")
    #         if origin and norm == self._normalize_country(origin):
    #             dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose a different destination.")
    #             return {"destination": None}
    #         return {"destination": norm}
    #     dispatcher.utter_message(
    #         text=f"Sorry, '{value}' is not supported.\nChoose destination from:\n{format_country_list()}"
    #     )
    #     return {"destination": None}





    # -------------------------------------------
# inside class ValidateFlightBookingForm ...
# -------------------------------------------

    def name(self) -> Text:
        return "validate_flight_booking_form"

    def _normalize_country(self, value: Optional[Text]) -> Optional[Text]:
        return value.strip().title() if value else value

# >>> ADDED: helper to parse "from X to Y" or "X to Y"
    def _parse_from_to(self, text: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """
        Try to extract (origin, destination) from a free text like:
        - "from Bangladesh to Canada"
        - "Bangladesh to Canada"
        Returns (origin, destination) or (None, None) if not matched.
        """
        if not text:
            return None, None

        s = text.strip()
        # "from X to Y"
        m = re.match(r"^\s*from\s+(.+?)\s+to\s+(.+?)\s*$", s, flags=re.IGNORECASE)
        if m:
            o = m.group(1).strip().title()
            d = m.group(2).strip().title()
            return o, d

        # "X to Y"
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
        # >>> CHANGED: first, attempt to parse "from X to Y"
        o, d = self._parse_from_to(value)
        if o and d and validate_country(o) and validate_country(d):
            if o == d:
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose different places.")
                return {"origin": None}
            # Fill BOTH slots at once
            dispatcher.utter_message(text=f"Got it ✅ Origin: {o}, Destination: {d}.")
            return {"origin": o, "destination": d}

        # >>> UNCHANGED behavior: treat it as a plain origin
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
        # >>> CHANGED: also accept "from X to Y" here (user might type both while asked for destination)
        o, d = self._parse_from_to(value)
        if o and d and validate_country(o) and validate_country(d):
            if o == d:
                dispatcher.utter_message(text="Origin and destination cannot be the same. Please choose different places.")
                return {"destination": None}
            dispatcher.utter_message(text=f"Got it ✅ Origin: {o}, Destination: {d}.")
            return {"origin": o, "destination": d}

        # >>> If user typed "X to Y" while we already have an origin, still try to use the destination part
        if not d:
            # No explicit "to Y" found above; fall back to normal destination handling
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

        # We did match "X to Y" but origin was invalid; try setting only destination if valid
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


    # Contact & booking-level fields
    def validate_phone_number(self, value, dispatcher, tracker, domain):
        if value and (re.fullmatch(r"\+?[1-9]\d{7,14}", value) or re.fullmatch(r"[0-9\-+ ]{7,15}", value)):
            return {"phone_number": value}
        dispatcher.utter_message(text="Please enter a valid phone number (e.g., +15551234567).")
        return {"phone_number": None}

    def validate_class_selection(self, value, dispatcher, tracker, domain):
        v = (value or "").lower().strip()
        if v in {"economy", "business", "first"}:
            return {"class_selection": v}
        dispatcher.utter_message(text="Please choose a class: economy, business, or first.")
        return {"class_selection": None}

    def validate_flight_time(self, value, dispatcher, tracker, domain):
        if value and str(value).strip():
            cleaned = str(value).strip().lstrip("]}> )").rstrip(" ]})")
            return {"flight_time": cleaned}
        dispatcher.utter_message(text="Please enter a valid flight time (e.g., 09:30 or 'morning').")
        return {"flight_time": None}

    def validate_travel_date(self, value, dispatcher, tracker, domain):
        pattern = r"^\d{2}/\d{2}/\d{4}$"
        if not re.match(pattern, value or ""):
            dispatcher.utter_message(text="❌ Please enter the date in DD/MM/YYYY format (e.g., 15/09/2025).")
            return {"travel_date": None}
        try:
            dt = datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            dispatcher.utter_message(text="❌ Invalid date. Please check the day, month, and year.")
            return {"travel_date": None}
        if dt < datetime.utcnow().date():
            dispatcher.utter_message(text="❌ Travel date cannot be in the past. Please choose a future date.")
            return {"travel_date": None}
        return {"travel_date": value}

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

    # Per-passenger fields (loop)
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

# --- SUBMIT BOOKING (saves passengers with seat) ---
class ActionSubmitBooking(Action):
    def name(self) -> str:
        return "action_submit_booking"

    def run(self, dispatcher, tracker, domain):
        # Trip & primary contact
        row = {
            "origin": tracker.get_slot("origin") or "N/A",
            "destination": tracker.get_slot("destination") or "N/A",
            "travel_date": tracker.get_slot("travel_date") or "N/A",
            "flight_time": tracker.get_slot("flight_time") or "N/A",
            # Global seat (legacy). You can remove this slot from the form; kept for compatibility.
            "seat_preference": tracker.get_slot("seat_preference") or "N/A",
            "class_selection": tracker.get_slot("class_selection") or "N/A",
            "passenger_name": tracker.get_slot("passenger_name") or "N/A",  # primary contact
            "phone_number": tracker.get_slot("phone_number") or "N/A",      # primary contact
            "travel_count": tracker.get_slot("travel_count") or 1,
        }

        # Parse passengers list
        passengers_json = tracker.get_slot("passengers") or "[]"
        try:
            passengers = json.loads(passengers_json)
        except Exception:
            passengers = []

        # Save
        try:
            booking_id = _save_booking(row)
            _save_passengers(booking_id, passengers)
            saved_msg = f"💾 Booking #{booking_id} saved with {len(passengers)} passenger(s)."
        except Exception as e:
            saved_msg = f"⚠️ Could not save booking to database: {e}"

        # Pretty list (with seat per passenger)
        pax_lines = "\n".join(
            [
                f"   {i+1}. {p.get('name','N/A')} | {p.get('phone','N/A')} | {p.get('email','N/A')} | Seat: {p.get('seat','N/A')}"
                for i, p in enumerate(passengers)
            ]
        ) or "   (no additional passengers)"

        dispatcher.utter_message(
            text=(
                f"✅ Booking Confirmed!\n\n"
                f"📍 From → To: {row['origin']} → {row['destination']}\n"
                f"📅 Date: {row['travel_date']}\n"
                f"⏰ Time: {row['flight_time']}\n"
                f"🎫 Class: {row['class_selection']}\n"
                f"👤 Primary Contact: {row['passenger_name']} ({row['phone_number']})\n"
                f"👥 Travelers: {row['travel_count']}\n"
                f"🪑 Seats: per passenger below\n"
                f"📜 Passenger List:\n{pax_lines}\n\n"
                f"{saved_msg}"
            )
        )

        # Clear all slots
        return [
                SlotSet("origin", None),
                SlotSet("destination", None),
                SlotSet("travel_date", None),
                SlotSet("flight_time", None),
                # SlotSet("seat_preference", None),  # <-- remove this line
                SlotSet("class_selection", None),
                SlotSet("passenger_name", None),
                SlotSet("phone_number", None),
                SlotSet("travel_count", None),
                SlotSet("expected_passengers", None),
                SlotSet("current_passenger_index", None),
                SlotSet("current_passenger_name", None),
                SlotSet("current_passenger_phone", None),
                SlotSet("current_passenger_email", None),
                SlotSet("current_passenger_seat_preference", None),
                SlotSet("passengers", None),
                ]

class ActionCache(Action):
    def name(self) -> str:
        return "action_cache"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        dispatcher.utter_message(json_message={"clear_chat": True})
        return [Restarted(), FollowupAction(name="utter_greet")]

class ActionBookFlight(Action):
    def name(self) -> Text:
        return "action_book_flight"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Booking your flight now!")
        return []

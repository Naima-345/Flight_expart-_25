from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import json
import os
import sqlite3
# --- Load allowed countries from JSON file ---
def load_allowed_countries() -> List[str]:
    """Load allowed countries from allowed_countries.json file."""
    json_path = os.path.join(os.path.dirname(__file__), '..', 'allowed_countries.json')
    with open(json_path, 'r') as f:
        return json.load(f)

ALLOWED_COUNTRIES = load_allowed_countries()

# --- Helper function to validate country ---
def validate_country(country: str) -> bool:
    """Check if the country is in the allowed list."""
    if not country:
        return False
    normalized = country.strip().title()
    return normalized in ALLOWED_COUNTRIES

# --- Helper to format allowed countries list ---
def format_country_list() -> str:
    return "\n".join(f"• {country}" for country in ALLOWED_COUNTRIES)

# --- Form validation for flight booking ---
class ValidateFlightBookingForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_flight_booking_form"

    def validate_origin(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        if validate_country(value):
            return {"origin": value}
        dispatcher.utter_message(
            text=(
                f"Sorry, '{value}' is not a supported country.\n"
                "Where do you want to travel from? Please choose from our listed countries:\n"
                + ", ".join(ALLOWED_COUNTRIES)
            )
        )
        return {"origin": None}

    def validate_destination(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        if validate_country(value):
            return {"destination": value}
        dispatcher.utter_message(
            text=(
                f"Sorry, '{value}' is not a supported country.\n"
                "Where do you want to travel to? Please choose from our listed countries:\n"
                + ", ".join(ALLOWED_COUNTRIES)
            )
        )
        return {"destination": None}
    def validate_phone_number(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        import re
        if re.fullmatch(r"[0-9\-+ ]{7,15}", value):
            return {"phone_number": value}
        dispatcher.utter_message(text="Please enter a valid phone number (digits, +, - allowed).")
        return {"phone_number": None}

    def validate_seat_preference(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        valid = ["window", "aisle", "middle"]
        if value.lower() in valid:
            return {"seat_preference": value.lower()}
        dispatcher.utter_message(text="Please choose a seat preference: window, aisle, or middle.")
        return {"seat_preference": None}

    def validate_class_selection(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        valid = ["economy", "business", "first"]
        if value.lower() in valid:
            return {"class_selection": value.lower()}
        dispatcher.utter_message(text="Please choose a class: economy, business, or first.")
        return {"class_selection": None}

    def validate_flight_time(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        if value.strip():
            return {"flight_time": value}
        dispatcher.utter_message(text="Please enter a valid flight time.")
        return {"flight_time": None}
    

    def validate_travel_date(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        if value.strip():
            return {"travel_date": value}
        dispatcher.utter_message(text="Please enter a valid travel date.")
        return {"travel_date": None}

    def validate_passenger_name(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        if value.strip():
            return {"passenger_name": value}
        dispatcher.utter_message(text="Please enter the passenger's name.")
        return {"passenger_name": None}



# --- Main action for submitting booking ---
class ActionSubmitBooking(Action):
    def name(self) -> Text:
        return "action_submit_booking"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Collect slot values
        booking_data = {
            "origin": tracker.get_slot("origin"),
            "destination": tracker.get_slot("destination"),
            "travel_date": tracker.get_slot("travel_date"),
            "passenger_name": tracker.get_slot("passenger_name"),
            "phone_number": tracker.get_slot("phone_number"),
            "seat_preference": tracker.get_slot("seat_preference"),
            "class_selection": tracker.get_slot("class_selection"),
            "flight_time": tracker.get_slot("flight_time")
        }

        # Save to SQLite DB
        conn = sqlite3.connect("rasa.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_booking_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT,
                destination TEXT,
                travel_date TEXT,
                passenger_name TEXT,
                phone_number TEXT,
                seat_preference TEXT,
                class_selection TEXT,
                flight_time TEXT
            )
        """)
        cursor.execute("""
            INSERT INTO ticket_booking_details (
                origin, destination, travel_date, passenger_name, phone_number, seat_preference, class_selection, flight_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            booking_data["origin"], booking_data["destination"], booking_data["travel_date"],
            booking_data["passenger_name"], booking_data["phone_number"], booking_data["seat_preference"],
            booking_data["class_selection"], booking_data["flight_time"]
        ))
        conn.commit()
        conn.close()

        dispatcher.utter_message(text="Your ticket has been booked and saved!")
        return []

  
        origin = tracker.get_slot("origin")
        destination = tracker.get_slot("destination")
        travel_date = tracker.get_slot("travel_date")
        passenger_name = tracker.get_slot("passenger_name")
        phone_number = tracker.get_slot("phone_number")
        seat_preference = tracker.get_slot("seat_preference")
        class_selection = tracker.get_slot("class_selection")
        flight_time = tracker.get_slot("flight_time")


        # Confirm booking
        
        dispatcher.utter_message(
            text=(
                f"✅ Booking confirmed!\n"
                f"Passenger: {passenger_name}\n"
                f"Phone: {phone_number}\n"
                f"From: {origin} -> To: {destination}\n"
                f"Date: {travel_date}\n"
                f"Seat: {seat_preference}\n"
                f"Class: {class_selection}\n"
                f"Flight Time: {flight_time}\n"
                "Thank you for choosing Flight Expert!"
            )
        )
        return [
            SlotSet("origin", None),
            SlotSet("destination", None),
            SlotSet("travel_date", None),
            SlotSet("passenger_name", None),
            SlotSet("phone_number", None),
            SlotSet("seat_preference", None),
            SlotSet("class_selection", None),
            SlotSet("flight_time", None)
        ]

# --- Optional action for booking trigger ---
class ActionBookFlight(Action):
    def name(self) -> Text:
        return "action_book_flight"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Booking your flight now!")
        return []
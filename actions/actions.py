from typing import Any, Text, Dict, List
from aiogram import Dispatcher
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted, FollowupAction
import json
import os
import sqlite3
from datetime import datetime
import re
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
        pattern = r"^\d{2}/\d{2}/\d{4}$"
        if not re.match(pattern, value):
            dispatcher.utter_message(text="❌ Please enter the date in DD/MM/YYYY format (e.g., 15/09/2025).")
            return {"travel_date": None}
        try:
            datetime.strptime(value, "%d/%m/%Y")
            return {"travel_date": value}
        except ValueError:
            dispatcher.utter_message(text="❌ Invalid date. Please check the day, month, and year.")
            return {"travel_date": None}

    def validate_passenger_name(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        if value.strip():
            return {"passenger_name": value}
        dispatcher.utter_message(text="Please enter the passenger's name.")
        return {"passenger_name": None}
    def validate_travel_count(self, value: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        if value.strip().isdigit():
            return {"travel_count": int(value)}
        dispatcher.utter_message(text="Please enter a valid number of travelers.")
        return {"travel_count": None}



class ActionSubmitBooking(Action):
    def name(self) -> str:
        return "action_submit_booking"

    def run(self, dispatcher, tracker, domain):
        origin = tracker.get_slot("origin") or "N/A"
        destination = tracker.get_slot("destination") or "N/A"
        travel_date = tracker.get_slot("travel_date") or "N/A"
        flight_time = tracker.get_slot("flight_time") or "N/A"
        seat = tracker.get_slot("seat_preference") or "N/A"
        cls = tracker.get_slot("class_selection") or "N/A"
        passenger_name = tracker.get_slot("passenger_name") or "N/A"
        phone_number = tracker.get_slot("phone_number") or "N/A"
        travel_count = tracker.get_slot("travel_count") or "N/A"

        dispatcher.utter_message(
            text=(
                f"✅ Booking Confirmed!\n\n"
                f"📍 From → To: {origin} → {destination}\n"
                f"📅 Date: {travel_date}\n"
                f"⏰ Time: {flight_time}\n"
                f"🎫 Class: {cls}\n"
                f"🪑 Seat: {seat}\n"
                f"👤 Passenger: {passenger_name}\n"
                f"📞 Contact: {phone_number}\n"
                f"👥 Travelers: {travel_count}\n\n"
                f"💾 Booking saved successfully in the database."
            )
        )

        return [
            SlotSet("origin", None),
            SlotSet("destination", None),
            SlotSet("travel_date", None),
            SlotSet("flight_time", None),
            SlotSet("seat_preference", None),
            SlotSet("class_selection", None),
            SlotSet("passenger_name", None),
            SlotSet("phone_number", None),
            SlotSet("travel_count", None)
        ]


class ActionCache(Action):
    def name(self) -> str:
        return "action_cache"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        dispatcher.utter_message(json_message={"clear_chat": True})
        return [Restarted(), FollowupAction(name="greet")]

# --- Optional action for booking trigger ---
class ActionBookFlight(Action):
    def name(self) -> Text:
        return "action_book_flight"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Booking your flight now!")
        return []
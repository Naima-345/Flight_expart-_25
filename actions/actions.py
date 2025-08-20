# from typing import Any, Text, Dict, List
# from rasa_sdk import Action, Tracker, FormValidationAction
# from rasa_sdk.executor import CollectingDispatcher
# from rasa_sdk.events import SlotSet, EventType
# from rasa_sdk.forms import FormAction

# # List of allowed travel destinations
# ALLOWED_COUNTRIES = [
#     "Bangladesh", "India", "Japan", "Australia", "Canada",
#     "Germany", "France", "Brazil", "Egypt", "South Africa"
# ]

# class ActionFlightBookingForm(FormAction):
#     """Custom form action to handle flight booking."""

#     def name(self) -> Text:
#         """Unique identifier of the form."""
#         return "flight_booking_form"

#     @staticmethod
#     def required_slots(tracker: Tracker) -> List[Text]:
#         """A list of required slots that the form has to fill."""
#         return ["destination", "inform_date"]

#     def slot_mappings(self) -> Dict[Text, Any]:
#         """A dictionary to map intents and entities to slots."""
#         return {
#             "destination": self.from_entity(entity="destination"),
#             "inform_date": self.from_entity(entity="inform_date")
#         }

#     def validate_destination(
#         self,
#         slot_value: Any,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any],
#     ) -> Dict[Text, Any]:
#         """Validate destination value."""

#         country = slot_value.strip().title()

#         if country in ALLOWED_COUNTRIES:
#             dispatcher.utter_message(
#                 text=f"Great choice! We have flights to {country}."
#             )
#             return {"destination": country}
#         else:
#             dispatcher.utter_message(
#                 text=f"Sorry, we only serve flights to these countries: {', '.join(ALLOWED_COUNTRIES)}."
#             )
#             return {"destination": None}
    
#     def submit(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any],
#     ) -> List[Dict]:
#         """Define what the form does once all required slots are filled."""
#         # The rule will now call `action_confirm_booking` after the form is completed.
#         return []

# class ActionConfirmBooking(Action):
#     """Custom action to confirm the flight booking."""

#     def name(self) -> Text:
#         """Unique name of the action."""
#         return "action_confirm_booking"

#     def run(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any],
#     ) -> List[Dict[Text, Any]]:

#         destination = tracker.get_slot("destination")
#         travel_date = tracker.get_slot("inform_date")

#         if destination and travel_date:
#             dispatcher.utter_message(
#                 text=f"Your booking to {destination} on {travel_date} is confirmed! ✈️"
#             )
#         else:
#             dispatcher.utter_message(
#                 text="Booking details are incomplete. Please provide all the required details."
#             )
        
#         # It's good practice to reset the slots after a successful booking
#         return [SlotSet("destination", None), SlotSet("inform_date", None)]



# from typing import Any, Text, Dict, List
# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher
# from rasa_sdk.events import SlotSet

# ALLOWED_COUNTRIES = [
#     "Bangladesh", "India", "Japan", "Australia", "Canada",
#     "Germany", "France", "Brazil", "Egypt", "South Africa"
# ]
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

#  Allowed countries
ALLOWED_COUNTRIES = [
    "Bangladesh", "India", "Japan", "France", "Germany",
    "Canada", "Australia", "Brazil", "United Kingdom", "United States"
]

#  Normalize and validate country
def validate_country(country: str) -> bool:
    if not country:
        return False
    normalized = country.strip().title()  # Removes extra spaces and capitalizes
    return normalized in ALLOWED_COUNTRIES

class ActionSubmitBooking(Action):
    def name(self) -> Text:
        return "action_submit_booking"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        origin = tracker.get_slot("origin")
        destination = tracker.get_slot("destination")
        travel_date = tracker.get_slot("travel_date")

        # Debug print (optional)
        print(f"Origin: {origin}, Destination: {destination}, Date: {travel_date}")

        #  Validate origin
        if not validate_country(origin):
            dispatcher.utter_message(
                text=f" Sorry, we don't support flights from '{origin}'.\n"
                     f"Supported countries are:\n" +
                     "\n".join(f"• {country}" for country in ALLOWED_COUNTRIES)
            )
            return []

        #  Validate destination
        if not validate_country(destination):
            dispatcher.utter_message(
                text=f" Sorry, we don't support flights to '{destination}'.\n"
                     f" Supported countries are:\n" +
                     "\n".join(f"• {country}" for country in ALLOWED_COUNTRIES)
            )
            return []

        # Confirm booking
        dispatcher.utter_message(
            text=f" Your flight from {origin} to {destination} on {travel_date} is confirmed!\n"
                 f" Thank you for choosing Flight Expert!"
        )
        return []

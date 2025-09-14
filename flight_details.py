import requests
import json

url = "http://api.aviationstack.com/v1/flights"
params = {
    "access_key": "af713cc236059da2ac1412c3876c4a34",  # demo key
    "limit": 1
}

resp = requests.get(url, params=params)
print("Status Code:", resp.status_code)

data = resp.json()

# Save full response (same as before)
with open("flight_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Response data saved to flight_data.json")

flights = data.get("data", [])

# Dictionary of airports
airports_dict = {}

for flight in flights:
    for place in ["departure", "arrival"]:
        info = flight.get(place, {})
        airport = info.get("airport")
        city = info.get("city") or airport  # fallback if city missing
        iata = info.get("iata")

        if airport and city and iata:
            airports_dict[airport] = {
                "city": city,
                "iata": iata
            }

# Save airports dictionary
with open("allowed_countries.json", "w", encoding="utf-8") as f:
    json.dump(airports_dict, f, indent=2, ensure_ascii=False)

print(f"Airports dictionary saved to allowed_countries.json (count={len(airports_dict)})")

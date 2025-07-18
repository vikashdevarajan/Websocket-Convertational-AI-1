import requests

class get_weather:
    openai_schema = {
        "name": "get_weather",
        "description": "Get the weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
        }
    }

    def __init__(self, location):
        self.location = location

    def run(self):
        # Use Open-Meteo geocoding to get latitude/longitude
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={self.location}&count=1"
        geo_resp = requests.get(geo_url)
        geo_data = geo_resp.json()
        if not geo_data.get("results"):
            return f"Could not find location: {self.location}"

        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]

        # Get current weather
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_resp = requests.get(weather_url)
        weather_data = weather_resp.json()
        if "current_weather" not in weather_data:
            return f"Could not fetch weather for {self.location}"

        temp = weather_data["current_weather"]["temperature"]
        wind = weather_data["current_weather"]["windspeed"]
        desc = f"The current temperature in {self.location} is {temp}°C with wind speed {wind} km/h."
        return desc
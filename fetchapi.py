
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os

OPENSKY_URL = "https://opensky-network.org/api/states/all"

def fetch_opensky_snapshot() -> pd.DataFrame:
    """
    Fetches a snapshot of current flights from the OpenSky API.
    Returns a pandas DataFrame of flight state vectors.
    """
    r = requests.get(OPENSKY_URL, timeout=20)
    if r.status_code != 200:
        raise RuntimeError("Failed to fetch OpenSky data")

    data = r.json()
    states = data.get("states", [])
    timestamp = data.get("time", datetime.utcnow().timestamp())

    cols = [
        "icao24", "callsign", "origin_country", "time_position", "last_contact",
        "longitude", "latitude", "baro_altitude", "on_ground", "velocity",
        "true_track", "vertical_rate", "sensors", "geo_altitude", "squawk",
        "spi", "position_source"
    ]
    df = pd.DataFrame(states, columns=cols)
    df["last_contact"] = pd.to_datetime(df["last_contact"], unit="s")
    df.attrs["timestamp"] = datetime.utcfromtimestamp(timestamp)
    return df

def fetch_aviation_API_airlines_endpoint():
    """
    Fetches airline data from the AviationStack API airlines endpoint.
    
    Parameters:
    - None
    
    Returns:
    - dict: The JSON response from the AviationStack API containing the airline data.
    """
    #api_key = os.environ.get("AVIATION_KEY") # Retrieve the API key (when running on HuggingFace)
    # Comment the line above and uncomment the two lines below if you are running the app locally (not on HuggingFace) and have a .env file with the AviationStack API key
    load_dotenv()
    api_key = os.getenv("AVIATION_KEY") # Retrieve the API key
    url = f"https://api.aviationstack.com/v1/airlines?access_key={api_key}"
    response = requests.get(url)
    return response.json()

if __name__ == "__main__":
    print("Fetching live flight data from OpenSky…")
    try:
        df = fetch_opensky_snapshot()
        print(f"Fetched {len(df)} flights at {df.attrs['timestamp']}")
        print(df.head())
    except Exception as e:
        print("Error:", e)

    print("Fetching airline data from AviationStack…")
    try:
        airline_data = fetch_aviation_API_airlines_endpoint()
        print(f"Fetched {len(airline_data.get('data', []))} airlines")
        print(airline_data)
    except Exception as e:
        print("Error:", e)
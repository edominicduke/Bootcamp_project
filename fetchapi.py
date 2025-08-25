
import requests
import pandas as pd
from datetime import datetime

OPENSKY_URL = "https://opensky-network.org/api/states/all"

def fetch_opensky_snapshot() -> pd.DataFrame:
    """
    Fetches a snapshot of current flights from the OpenSky API.
    Returns a pandas DataFrame of flight state vectors.
    """
    r = requests.get(OPENSKY_URL, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to fetch OpenSky data: {r.status_code} {r.reason} -> {r.text[:200]}")   


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

if __name__ == "__main__":
    print("Fetching live flight data from OpenSky…")
    try:
        df = fetch_opensky_snapshot()
        print(f"Fetched {len(df)} flights at {df.attrs['timestamp']}")
        print(df.head())
    except Exception as e:
        print("Error:", e)


import requests
import pandas as pd
from datetime import datetime
import time

OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_URL_DEPARTURES = "https://opensky-network.org/api/flights/departure"
OPENSKY_URL_ARRIVALS = "https://opensky-network.org/api/flights/arrival"

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

def fetch_rdu_departures(hours=6) -> pd.DataFrame:
    """
    Fetch recent departures from RDU (KRDU) within the last n hours (default is 6).
    Returns a pandas DataFrame.
    """
    end = int(time.time())
    begin = end - hours * 3600
    params = {
        "airport": "KRDU",
        "begin": begin,
        "end": end
    }

    response = requests.get(OPENSKY_URL_DEPARTURES, params=params, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch data, {response.headers}")
    
    data = response.json()
    columns = [
        "icao24", "firstSeen", "estDepartureAirport", "lastSeen", "estArrivalAirport", "callsign",
        "estDepartureAirportHorizDistance", "estDepartureAirportVertDistance", "estArrivalAirportHorizDistance",
        "estArrivalAirportVertDistance", "departureAirportCandidatesCount", "arrivalAirportCandidatesCount"
    ]
    data_df = pd.DataFrame(data, columns=columns)

    # print(data_df)

    flights = []
    for _, flight in data_df.iterrows():
        # print(flight)
        flights.append({
            "icao24": flight["icao24"],
            "callsign": flight["callsign"],
            "departure": flight["estDepartureAirport"],
            "arrival": flight["estArrivalAirport"]
        })
    return pd.DataFrame(flights)

if __name__ == "__main__":
    print("Fetching live flight data from OpenSky…")
    try:
        df = fetch_opensky_snapshot()
        print(f"Fetched {len(df)} flights at {df.attrs['timestamp']}")
        print(df.head())

        df_2 = fetch_rdu_departures(hours=6)
        print(f"Fetched {len(df)} flights at {df.attrs['timestamp']}")
        print(df.head())
    except Exception as e:
        print("Error:", e)

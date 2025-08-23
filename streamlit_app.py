import pandas as pd
import requests
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime

st.set_page_config(page_title="Flight Volume by Country (OpenSky)", layout="wide")
st.title("🌍 Global Flight Snapshot (via OpenSky Network)")

st.caption("Showing a snapshot of the most recent ~1,800 aircraft globally. Data is live and limited by OpenSky’s API.")

run = st.button("Fetch Live Flights")

# ---------- API ----------
OPENSKY_URL = "https://opensky-network.org/api/states/all"

@st.cache_data(show_spinner=False)
def fetch_opensky_states():
    r = requests.get(OPENSKY_URL, timeout=20)
    if r.status_code == 200:
        return r.json()
    return None

# ---------- Main ----------
if run:
    st.info("Fetching live data from OpenSky…")
    data = fetch_opensky_states()

    if not data or "states" not in data:
        st.error("Failed to fetch data from OpenSky. Try again later.")
        st.stop()

    states = data["states"]
    now = datetime.utcfromtimestamp(data.get("time", datetime.utcnow().timestamp()))

    # Convert to DataFrame
    cols = [
        "icao24", "callsign", "origin_country", "time_position", "last_contact",
        "longitude", "latitude", "baro_altitude", "on_ground", "velocity",
        "true_track", "vertical_rate", "sensors", "geo_altitude", "squawk",
        "spi", "position_source"
    ]
    df = pd.DataFrame(states, columns=cols)
    df["last_contact"] = pd.to_datetime(df["last_contact"], unit="s")

    st.metric("Flights in snapshot", len(df))

    if df.empty:
        st.warning("No flights found in snapshot.")
        st.stop()

    # Aggregate by country
    summary = df.groupby("origin_country").size().reset_index(name="flights")
    summary = summary.sort_values("flights", ascending=False).head(30)

    # ---------- Plot Top 30 Countries ----------
    st.subheader("✈️ Top 30 Countries by Active Flights")

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(summary["origin_country"], summary["flights"])
    ax.set_xlabel("Flights (current snapshot)")
    ax.set_ylabel("Country")
    ax.set_title("Top 30 Countries by Active Flights")
    ax.invert_yaxis()  # Largest at top
    st.pyplot(fig)

    # ---------- Plot Flight Scatter Map ----------
    st.subheader("🌐 Flight Positions (Scatter Map)")
    df_map = df.dropna(subset=["latitude", "longitude"])

    if df_map.empty:
        st.warning("No geolocation data available for mapping.")
    else:
        fig2, ax2 = plt.subplots(figsize=(12, 6))
        ax2.scatter(df_map["longitude"], df_map["latitude"], s=2, alpha=0.5)
        ax2.set_title("Global Flight Positions")
        ax2.set_xlabel("Longitude")
        ax2.set_ylabel("Latitude")
        st.pyplot(fig2)

    with st.expander("Raw Country Data"):
        st.dataframe(summary)

else:
    st.info("Click 'Fetch Live Flights' to view global snapshot.")

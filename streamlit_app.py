# streamlit_app.py

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from fetchapi import fetch_opensky_snapshot, fetch_rdu_departures

st.set_page_config(page_title="Flight Volume by Country (OpenSky)", layout="wide")
st.title("🌍 Global Flight Snapshot (via OpenSky Network)")

st.caption("Showing a snapshot of the most recent ~1,800 aircraft globally. Data is live and limited by OpenSky’s API.")

run = st.button("Fetch Live Flights")

# ---------- Main ----------
if run:
    st.info("Fetching live data from OpenSky…")
    try:
        df = fetch_opensky_snapshot()
    except Exception as e:
        st.error(f"Failed to fetch data: {type(e).__name__} -> {e}")
        st.stop()

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


    ############# Omkar's Code #############
    st.subheader("📊 Other Analyses (OpenSky)")

    col1, col2, col3 = st.columns(3)

    # 1. Flights by Altitude Band
    with col1:
        if "baro_altitude" in df.columns:
            # Convert meters to feet
            df["alt_ft"] = df["baro_altitude"] * 3.28084  

            bins = [-1000, 10000, 20000, 30000, 60000]   # feet
            labels = ["<10k", "10–20k", "20–30k", "30k+"]
            df["alt_band"] = pd.cut(df["alt_ft"], bins=bins, labels=labels)

            alt_counts = df["alt_band"].value_counts().reindex(labels, fill_value=0)

            fig_alt, ax_alt = plt.subplots(figsize=(4,3))
            ax_alt.bar(alt_counts.index, alt_counts.values, color="mediumseagreen", alpha=0.8)
            ax_alt.set_title("Flights by Altitude Band (feet)")
            ax_alt.set_xlabel("Altitude band")
            ax_alt.set_ylabel("Aircraft")
            st.pyplot(fig_alt, use_container_width=False)


    # 2. Top Airlines by Callsign Prefix
    with col2:
        if "callsign" in df.columns:
            # Clean callsigns
            cs = df["callsign"].astype(str).str.upper().str.strip()

            # Extract exactly 3 leading letters (ICAO airline code)
            prefix = cs.str.extract(r'^([A-Z]{3})', expand=False)

            # Tag N-registered private aircraft
            n_reg_mask = prefix.isna() & cs.str.match(r'^N[0-9A-Z]+', na=False)
            prefix = prefix.where(~n_reg_mask, "Private/GA")

            # Fill remaining blanks
            prefix = prefix.fillna("No Name")

            # Map common airline codes → names
            airline_map = {
                "AAL": "American Airlines",
                "DAL": "Delta Air Lines",
                "UAL": "United Airlines",
                "SWA": "Southwest Airlines",
                "JBU": "Jet Blue Airways",
                "FFT": "Frontier Airlines",
                "NKS": "Spirit Airlines",
                "ASA": "Alaska Airlines",
                "UPS": "UPS Airlines",
                "FDX": "Fed Ex Express",
                "BAW": "British Airways",
                "DLH": "Lufthansa",
                "AFR": "Air France",
                "KLM": "KLM Royal Dutch Airlines",
                "UAE": "Emirates",
                "Private/GA": "Private/GA",
                "No Name": "No Name",
            }

            # Replace codes with names where possible
            airline_name = prefix.map(airline_map).fillna(prefix)

            airline_counts = airline_name.value_counts().head(15)

            fig_airline, ax_airline = plt.subplots(figsize=(8, 6))
            ax_airline.barh(airline_counts.index, airline_counts.values, color="slateblue", alpha=0.85)
            ax_airline.set_title("Top 15 Airlines by Callsign")
            ax_airline.set_xlabel("Aircraft")
            ax_airline.invert_yaxis()
            st.pyplot(fig_airline, use_container_width=False)


    # 3. Flights by Broad Region (Pie)
    with col3:
        if {"latitude","longitude"}.issubset(df.columns):
            df["region"] = pd.cut(
                df["longitude"],
                bins=[-180, -30, 60, 180],
                labels=["Americas", "Europe/Africa", "Asia-Pacific"]
            )
            region_counts = df["region"].value_counts()

            fig_region, ax_region = plt.subplots(figsize=(3.5,3.5))
            ax_region.pie(region_counts.values, labels=region_counts.index, autopct="%1.0f%%")
            ax_region.set_title("Regions")
            st.pyplot(fig_region, use_container_width=False)



=======

else:
    st.info("Click 'Fetch Live Flights' to view global snapshot.")



## ---------- RDU Specific Analysis ---------- ##
st.header("🛫 Raleigh-Durham (RDU) Airport Stats")
run_rdu = st.button("Fetch RDU Stats")

if run_rdu:
    with st.spinner("Fetching RDU-specific flight data..."):
        df_departures = fetch_rdu_departures(hours=6)
    
    st.metric("Departures (last 6h)", len(df_departures))

    if not df_departures.empty:
        # ---- Top Airlines ----
        def airline_from_callsign(callsign):
            if not callsign or len(callsign) < 3:
                return "Unknown"
            prefix = callsign[:3].upper()
            mapping = {
                "AAL": "American Airlines",
                "DAL": "Delta",
                "UAL": "United",
                "SWA": "Southwest",
                "JBU": "JetBlue",
                "FDX": "FedEx",
                "UPS": "UPS",
                "NKS": "Spirit",
                "ASA": "Alaska",
                "FFT": "Frontier"
            }
            return mapping.get(prefix, prefix)
        
        df_departures["Airline"] = df_departures["callsign"].apply(airline_from_callsign)
        top_airlines = df_departures["Airline"].value_counts().head(10).reset_index()
        top_airlines.columns = ["Airline", "Flights"]
        st.subheader("🏢 Top 10 Airlines from RDU (last 6h)")
        st.bar_chart(top_airlines.set_index("Airline"))


# streamlit_app.py

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from fetchapi import fetch_opensky_snapshot, fetch_rdu_departures, fetch_aviation_API_airlines_endpoint
import requests

import os

# always read the .env next to this file
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*a, **k): pass

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

@st.cache_data(ttl=600)
def _get_counts_cached(icao: str):
    return hourly_counts_for_previous_day(icao.strip().upper())



    u = os.getenv("OPENSKY_USER", "")
    p = os.getenv("OPENSKY_PASS", "")
    # Show safely without revealing actual secrets
    st.write({
        "has_user": bool(u),
        "has_pass": bool(p),
        "user_repr": repr(u[:3] + "***"),  # mask
        "pass_len": len(p)
    })
    # Check latin-1 encodability
    try:
        u.encode("latin-1"); p.encode("latin-1")
        st.write({"latin1_ok": True})
    except UnicodeEncodeError:
        st.error("OPENSKY_USER / OPENSKY_PASS contain non-Latin-1 characters. Please use ASCII only.")


# --- Compatibility wrapper: DO NOT modify teammate's code below ---
# This replaces the imported function with a safe wrapper that always returns {"data": list}
try:
    _orig_fetch_airlines = fetch_aviation_API_airlines_endpoint  # imported from fetchapi.py
except Exception:
    _orig_fetch_airlines = None

if _orig_fetch_airlines is not None:
    def fetch_aviation_API_airlines_endpoint(*args, **kwargs):
        """
        Safe wrapper around the original function.
        Always normalizes the payload to {"data": <list>}.
        Never raises if the upstream returns an unexpected shape.
        """
        try:
            payload = _orig_fetch_airlines(*args, **kwargs)
        except Exception as e:
            # Soft-fail: surface info to the UI but keep the app running
            try:
                import streamlit as st  # guard: in case this module is imported elsewhere
                st.info(f"Aviation API error: {type(e).__name__}: {e}")
            except Exception:
                pass
            return {"data": []}

        # Normalize common shapes → {"data": list}
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload
            for alt in ("results", "airlines", "items"):
                if isinstance(payload.get(alt), list):
                    return {"data": payload[alt]}
            # If it's a dict-of-dicts, convert values to a list
            if payload and all(isinstance(v, dict) for v in payload.values()):
                return {"data": list(payload.values())}
            return {"data": []}
        if isinstance(payload, list):
            return {"data": payload}
        # Anything else → empty dataset
        return {"data": []}
        


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
    st.header("📊 Other Analyses (OpenSky)")

    col1, col2, col3 = st.columns(3)

    # 1. Flights by Altitude Band
    st.subheader("Flights by Altitude Band")
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
    st.subheader("Top Airlines by Callsign Prefix")
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
    st.subheader("Flights by Broad Region")
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

# ============== >>> RDU HOURLY HEATMAP START >>> ==============
# ---------- RDU Previous-Day Hourly Heatmap (OpenSky) ----------
st.header("🔥 RDU Hourly Arrivals/Departures — Previous Day")

# Optional: one-click to clear cache
if st.button("♻️ Clear RDU cache"):
    st.cache_data.clear()
    st.success("Cache cleared.")

colA, colB = st.columns([1, 1])
with colA:
    # ICAO code; KRDU is Raleigh–Durham
    airport_icao = st.text_input("Airport ICAO", value=DEFAULT_AIRPORT, help="KRDU = Raleigh–Durham")
with colB:
    # Trigger to fetch and render the heatmap
    go_heatmap = st.button("Generate RDU Heatmap")

if go_heatmap:
    with st.spinner("Fetching previous-day arrivals & departures from OpenSky..."):
        counts_df, prev_day = _get_counts_cached(airport_icao)

    # Show the day and timezone for clarity
    st.caption(f"Local day: {prev_day.isoformat()} · Timezone: America/New_York")

    # Display the raw hourly table
    st.dataframe(counts_df, use_container_width=True)

    # Diagnostics: totals + last OpenSky HTTP status histogram
    st.write({
        "total_arrivals": int(counts_df['arrivals'].sum()),
        "total_departures": int(counts_df['departures'].sum()),
        "opensky_status_hist": get_last_status_hist()  # e.g., {200: 24} / {429: 6} / {401: 4}
    })

    # Build a 2x24 matrix for heatmap: row0=Arrivals, row1=Departures
    data = [counts_df['arrivals'].tolist(), counts_df['departures'].tolist()]

    # Draw heatmap using matplotlib (no custom colors per your constraints)
    fig, ax = plt.subplots(figsize=(12, 2.8))
    im = ax.imshow(data, aspect="auto")

    # Axis labels and ticks
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Arrivals", "Departures"])
    ax.set_xticks(range(24))
    ax.set_xticklabels([str(h) for h in range(24)])
    ax.set_xlabel("Hour of Day (Local)")
    ax.set_title(f"{airport_icao.strip().upper()} — Hourly Arrivals/Departures on {prev_day.isoformat()}")

    # Optional: annotate cell counts
    for r in range(2):
        for c in range(24):
            ax.text(c, r, str(data[r][c]), ha="center", va="center", fontsize=8)

    # Colorbar and render
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    st.pyplot(fig)
# ============== <<< RDU HOURLY HEATMAP END <<< ==============



#### ----------- Airline Profile Comparison (AviationStack API - Ethan Dominic's Code) ----------- ####
airline_data = fetch_aviation_API_airlines_endpoint()
if isinstance(airline_data, list):
    airline_data = {"data": airline_data}
elif isinstance(airline_data, dict):
    if not isinstance(airline_data.get("data"), list):
        # Try common alternate keys from APIs
        for alt in ("results", "airlines", "items"):
            if isinstance(airline_data.get(alt), list):
                airline_data = {"data": airline_data[alt]}
                break
        else:
            # Fallback: empty dataset if no suitable list found
            airline_data = {"data": []}
else:
    airline_data = {"data": []}

def get_airline_feature_dict(feature_type, cast_type):
    """
    Return a dictionary of airline names along with their values for the specified feature type.
    
    Parameters:
    - feature_type (str): The specified feature type to extract (e.g., "fleet_size", "fleet_average_age", "date_founded").
    - cast_type (str): The type to cast the feature value to ("int", "float", or "str")
    
    Returns:
    - dict: A dictionary whose keys are airline names and values are the corresponding feature values.
    """
    airline_feature_dict = {}
    for i in range(len(airline_data["data"])):
        airline_name = airline_data["data"][i]["airline_name"]
        if airline_data["data"][i][feature_type] is not None and airline_data["data"][i][feature_type] != "":
            if cast_type == "int":
                airline_feature_value = int(airline_data["data"][i][feature_type])
            elif cast_type == "str":
                airline_feature_value = str(airline_data["data"][i][feature_type])
            else:
                airline_feature_value = float(airline_data["data"][i][feature_type])
        airline_feature_dict[airline_name] = airline_feature_value
    return airline_feature_dict

def plot_bar_graph(feature_series, title, ylabel, bottom_ylim=0):
    """
    Plot a bar graph for the given feature Series.
    
    Parameters:
    - feature_series (pd.Series): A pandas Series where the index is airline names and the values are the feature values.
    - title (str): The desired title of the graph.
    - ylabel (str): The desired label for the y-axis.
    - bottom_ylim (int, optional): The minimum limit for the y-axis. Defaults to 0.

    Returns:
    - None: Displays the bar graph using Streamlit.
    """
    fig, ax = plt.subplots()
    bars = ax.bar(feature_series.index.astype(str), feature_series.values)
    ax.set_title(title)
    ax.set_xlabel("Airline")
    ax.set_ylabel(ylabel)
    ax.bar(feature_series.index, feature_series.values)
    ax.bar_label(bars, padding=3)
    plt.xticks(rotation=90)
    plt.ylim(bottom=bottom_ylim)
    st.pyplot(fig)

# Main Program Execution
st.title("Airline Profile Comparison")

comparison_option = st.radio(
    "Pick the type of comparison you would like to see: ",
    ("Fleet Size", "Fleet Average Age", "Founding Year")
)
# --- Final guard: ensure airline_data has a "data" list right before use ---
if not isinstance(airline_data, dict):
    airline_data = {}
airline_data.setdefault("data", [])
countries_of_origin = pd.Series(get_airline_feature_dict("country_name", "str"))
country_filters = countries_of_origin.unique().tolist()
country_filters.append("All Countries") # Add option for user to see all countries
country_filter_option = st.radio(
    "Pick a country of origin to filter by: ",
    (country_filters)
)

if country_filter_option == "All Countries":
    if comparison_option == "Fleet Size":
        fleet_sizes = (pd.Series(get_airline_feature_dict("fleet_size", "int"))).dropna() # Remove airlines with no fleet size data
        sorted_fleet_sizes = fleet_sizes.sort_values(ascending=True)
        top10_sorted_fleet_sizes = sorted_fleet_sizes.tail(10) # Get the top 10 largest airlines by fleet size
        plot_bar_graph(top10_sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = (pd.Series(get_airline_feature_dict("fleet_average_age", "float"))).dropna() # Remove airlines with no fleet average age data
        sorted_fleet_avg_ages = fleet_avg_ages.sort_values(ascending=True)
        top10_sorted_fleet_avg_ages = sorted_fleet_avg_ages.head(10) # Get the top 10 youngest airlines by fleet average age
        plot_bar_graph(top10_sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = (pd.Series(get_airline_feature_dict("date_founded", "int"))).dropna() # Remove airlines with no founding year data
        sorted_founding_years = founding_years.sort_values(ascending=True)
        top10_sorted_founding_years = sorted_founding_years.head(10) # Get the top 10 oldest airlines by founding year
        plot_bar_graph(top10_sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900) # Set y-axis minimum so years before 1900 since no airlines were founded before then
else:
    if comparison_option == "Fleet Size":
        fleet_sizes = (pd.Series(get_airline_feature_dict("fleet_size", "int"))).dropna() # Remove airlines with no fleet size data
        filtered_fleet_sizes = fleet_sizes[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_fleet_sizes = filtered_fleet_sizes.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_sizes, "Airline Fleet Sizes", "Fleet Size")
    elif comparison_option == "Fleet Average Age":
        fleet_avg_ages = (pd.Series(get_airline_feature_dict("fleet_average_age", "float"))).dropna() # Remove airlines with no fleet average age data
        filtered_fleet_avg_ages = fleet_avg_ages[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_fleet_avg_ages = filtered_fleet_avg_ages.sort_values(ascending=True)
        plot_bar_graph(sorted_fleet_avg_ages, "Airline Fleet Average Ages", "Fleet Average Age")
    elif comparison_option == "Founding Year":
        founding_years = (pd.Series(get_airline_feature_dict("date_founded", "int"))).dropna() # Remove airlines with no founding year data
        filtered_founding_years = founding_years[countries_of_origin == country_filter_option] # Ensure only airlines from the selected country are included
        sorted_founding_years = filtered_founding_years.sort_values(ascending=True)
        plot_bar_graph(sorted_founding_years, "Airline Founding Years", "Founding Year", bottom_ylim=1900) # Set y-axis minimum so years before 1900 since no airlines were founded before then

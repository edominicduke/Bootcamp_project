# rdu_hourly.py
# Utilities to fetch previous-day arrivals/departures for an airport (KRDU by default)
# and aggregate counts per local hour using OpenSky public API.

import os
import time
import requests
import pandas as pd

OPENSKY_BASE = "https://opensky-network.org/api"
DEFAULT_AIRPORT = "KRDU"        # ICAO for Raleigh–Durham
LOCAL_TZ = "America/New_York"   # Use pandas' timezone utilities

def _opensky_auth():
    """Return (user, pass) tuple if OPENSKY_USER/OPENSKY_PASS are set; otherwise None."""
    u, p = os.getenv("OPENSKY_USER"), os.getenv("OPENSKY_PASS")
    return (u, p) if u and p else None

def previous_day_range_utc():
    """
    Compute the previous local calendar day [00:00, 24:00) in America/New_York,
    then convert to UTC UNIX timestamps (seconds).
    Returns: (begin_utc_ts, end_utc_ts, previous_day_date)
    """
    now_local = pd.Timestamp.now(tz=LOCAL_TZ)
    start_local = now_local.floor("D") - pd.Timedelta(days=1)  # yesterday 00:00 local
    end_local = start_local + pd.Timedelta(days=1)             # today 00:00 local
    start_utc = start_local.tz_convert("UTC").to_pydatetime().timestamp()
    end_utc = end_local.tz_convert("UTC").to_pydatetime().timestamp()
    return int(start_utc), int(end_utc), start_local.date()

def _fetch_flights(kind: str, airport: str, begin_ts: int, end_ts: int, window_sec: int = 2*3600):
    """
    Fetch flights in small windows to avoid OpenSky time range limits.
    kind: "arrival" or "departure".
    Returns: list of JSON objects from OpenSky.
    """
    assert kind in ("arrival", "departure")
    auth = _opensky_auth()
    all_rows, t0 = [], begin_ts

    while t0 < end_ts:
        t1 = min(t0 + window_sec, end_ts)
        url = f"{OPENSKY_BASE}/flights/{kind}"
        params = {"airport": airport, "begin": t0, "end": t1}

        # Simple retry for transient errors/rate limits
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, auth=auth, timeout=30)
                if r.status_code == 200:
                    all_rows += (r.json() or [])
                    break
                if r.status_code in (429, 502, 503):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                # 404 means no data for window; break retry loop
                break
            except requests.RequestException:
                time.sleep(1.5 * (attempt + 1))

        time.sleep(0.3)  # be gentle to the API
        t0 = t1

    # De-duplicate by (icao24, firstSeen, lastSeen)
    seen, uniq = set(), []
    for row in all_rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row)
            seen.add(key)
    return uniq

def _rows_to_df(rows: list, kind: str):
    """
    Convert OpenSky rows to DataFrame and derive local hour:
    - arrivals use lastSeen
    - departures use firstSeen
    """
    if not rows:
        return pd.DataFrame(columns=["hour", "callsign", "icao24", "ts_local", "estDepartureAirport", "estArrivalAirport"])
    df = pd.DataFrame(rows)
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    dt_local = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts_local"] = dt_local
    df["hour"] = df["ts_local"].dt.hour
    return df[["hour", "callsign", "icao24", "ts_local", "estDepartureAirport", "estArrivalAirport"]]

def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT):
    """
    Build a 24-hour table (index=0..23) with columns:
    - arrivals: count of arrivals in each local hour
    - departures: count of departures in each local hour
    Returns: (counts_df, previous_day_date)
    """
    begin_ts, end_ts, prev_day = previous_day_range_utc()
    arr = _rows_to_df(_fetch_flights("arrival", airport, begin_ts, end_ts), "arrival")
    dep = _rows_to_df(_fetch_flights("departure", airport, begin_ts, end_ts), "departure")
    idx = pd.Index(range(24), name="hour")
    arr_cnt = arr.groupby("hour").size().reindex(idx, fill_value=0)
    dep_cnt = dep.groupby("hour").size().reindex(idx, fill_value=0)
    return pd.DataFrame({"arrivals": arr_cnt, "departures": dep_cnt}), prev_day

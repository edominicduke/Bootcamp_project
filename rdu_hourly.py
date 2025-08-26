# rdu_hourly.py
# Utilities to fetch previous-day arrivals/departures for an airport (KRDU by default)
# and aggregate counts per local hour using OpenSky public API.
# - Larger time windows + gentle pacing to avoid rate limits
# - Robust credential handling (Latin-1 for HTTP Basic per RFC 7617)
# - Helpful diagnostics (HTTP status histogram) when the API returns no data

from __future__ import annotations

import os
import time
from collections import Counter
_LAST_STATUS_HIST = Counter()

def get_last_status_hist() -> dict:
    """Expose last run's status histogram to the app."""
    return dict(_LAST_STATUS_HIST)
from typing import List, Tuple, Optional, Dict, Any

import requests
import pandas as pd

# If the app runs inside Streamlit we use st.info()/st.error(); otherwise fallback to print.
def _st_info(msg: str) -> None:
    try:
        import streamlit as st  # imported lazily
        st.info(msg)
    except Exception:
        print(f"[INFO] {msg}")

def _st_error(msg: str) -> None:
    try:
        import streamlit as st
        st.error(msg)
    except Exception:
        print(f"[ERROR] {msg}")

OPENSKY_BASE = "https://opensky-network.org/api"
DEFAULT_AIRPORT = "KRDU"        # ICAO for Raleigh–Durham
LOCAL_TZ = "America/New_York"   # Use pandas timezone utilities


# ---------- Credentials handling ----------
def _opensky_auth() -> Optional[Tuple[str, str]]:
    """
    Read OpenSky creds from env and validate for HTTP Basic.
    - Strips BOM/zero-width chars and surrounding whitespace
    - Ensures Latin-1 encodability as required by RFC 7617 (requests uses latin-1)
    Env:
      OPENSKY_USER  (OpenSky website username; often an email, not display name)
      OPENSKY_PASS
    """
    def _clean(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        # strip whitespace + BOM + zero-width space
        return s.strip().replace("\ufeff", "").replace("\u200b", "")

    user = _clean(os.getenv("OPENSKY_USER"))
    pw   = _clean(os.getenv("OPENSKY_PASS"))

    if not user or not pw:
        # Missing credentials → fall back to anonymous; may hit rate limits
        return None

    # Validate latin-1 (HTTP Basic requirement)
    try:
        user.encode("latin-1")
        pw.encode("latin-1")
    except UnicodeEncodeError:
        _st_error(
            "OPENSKY_USER/OPENSKY_PASS contain non-Latin-1 characters. "
            "Please use ASCII/Latin-1 credentials. (Username must be your OpenSky *website username*, not nick/display name.)"
        )
        return None

    return (user, pw)


# ---------- Time helpers ----------
def previous_day_range_utc() -> Tuple[int, int, pd.Timestamp]:
    """
    Compute the previous *local* calendar day [00:00, 24:00) in LOCAL_TZ
    and return its corresponding UTC UNIX timestamps, plus the local date.
    Returns:
        (begin_utc_ts, end_utc_ts, prev_day_local_date_ts)
    """
    now_local = pd.Timestamp.now(tz=LOCAL_TZ)
    start_local = now_local.floor("D") - pd.Timedelta(days=1)  # yesterday 00:00 local
    end_local = start_local + pd.Timedelta(days=1)             # today 00:00 local
    start_utc = int(start_local.tz_convert("UTC").timestamp())
    end_utc = int(end_local.tz_convert("UTC").timestamp())
    return start_utc, end_utc, start_local  # start_local is tz-aware


# ---------- API fetching with diagnostics ----------
def _fetch_flights(
    kind: str,
    airport: str,
    begin_ts: int,
    end_ts: int,
    window_sec: int = 2 * 3600,
    sleep_between: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Fetch flights in multiple windows to avoid OpenSky time range/ratelimit issues.
    Args:
        kind: "arrival" or "departure"
        airport: ICAO code (e.g., "KRDU")
        begin_ts, end_ts: UTC UNIX seconds (closed-open interval [begin, end))
        window_sec: window size in seconds (default 6 hours)
        sleep_between: sleep seconds between window requests to be gentle to the API
    Returns:
        List of flight dicts (possibly empty). If empty, a status histogram will be shown.
    """
    assert kind in ("arrival", "departure")
    auth = _opensky_auth()
    all_rows: List[Dict[str, Any]] = []
    statuses: List[int] = []

    t0 = begin_ts
    while t0 < end_ts:
        t1 = min(t0 + window_sec, end_ts)
        url = f"{OPENSKY_BASE}/flights/{kind}"
        params = {"airport": airport, "begin": t0, "end": t1}

        # simple retries for transient errors
        for attempt in range(4):
            try:
                r = requests.get(url, params=params, auth=auth, timeout=30)
                statuses.append(r.status_code)

                if r.status_code == 200:
                    payload = r.json() or []
                    if isinstance(payload, list):
                        all_rows.extend(payload)
                    break

                # Transient: backoff then retry
                if r.status_code in (429, 502, 503):
                    time.sleep(1.5 * (attempt + 1))
                    continue

                # 401/403 (auth), 404 (no data) → don't spin retries for this window
                break

            except requests.RequestException:
                time.sleep(1.5 * (attempt + 1))

        time.sleep(sleep_between)
        t0 = t1

    # De-duplicate by (icao24, firstSeen, lastSeen)
    seen: set = set()
    uniq: List[Dict[str, Any]] = []
    for row in all_rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row)
            seen.add(key)

    # Helpful diagnostics when nothing returned
    if not uniq:
        hist = dict(Counter(statuses)) if statuses else {}
        hints = []
        if 401 in hist or 403 in hist:
            hints.append(
                "Auth error (401/403). Ensure OPENSKY_USER/OPENSKY_PASS are correct and OPENSKY_USER is your website username (often your email)."
            )
        if 429 in hist:
            hints.append("Rate limited (429). Try again later, increase window size, or reduce frequency.")
        if 404 in hist:
            hints.append("No data (404) for that window/airport.")
        if not hints and not hist:
            hints.append("No HTTP responses recorded; check network connectivity.")
        _st_info(f"OpenSky replies by status: {hist}. {' '.join(hints)}")

    return uniq
    global _LAST_STATUS_HIST
_LAST_STATUS_HIST = Counter(statuses)


def _rows_to_df(rows: List[Dict[str, Any]], kind: str) -> pd.DataFrame:
    """
    Convert OpenSky rows to a DataFrame and derive local hour.
    For arrivals we use 'lastSeen'; for departures we use 'firstSeen'.
    Returns columns: ['hour','callsign','icao24','ts_local','estDepartureAirport','estArrivalAirport']
    """
    if not rows:
        return pd.DataFrame(columns=["hour", "callsign", "icao24", "ts_local",
                                     "estDepartureAirport", "estArrivalAirport"])
    df = pd.DataFrame(rows)
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    # Convert to local tz
    dt_local = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts_local"] = dt_local
    df["hour"] = df["ts_local"].dt.hour
    cols = ["hour", "callsign", "icao24", "ts_local", "estDepartureAirport", "estArrivalAirport"]
    return df.reindex(columns=cols)


# ---------- Public API ----------
def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """
    Build a 24-hour table (index 0..23) with columns:
      - arrivals: count of arrivals per local hour
      - departures: count of departures per local hour
    Returns:
      (counts_df, previous_day_local_date_ts)
    """
    begin_ts, end_ts, prev_day_local = previous_day_range_utc()

    arrivals_rows = _fetch_flights("arrival", airport, begin_ts, end_ts)
    departures_rows = _fetch_flights("departure", airport, begin_ts, end_ts)

    arr_df = _rows_to_df(arrivals_rows, "arrival")
    dep_df = _rows_to_df(departures_rows, "departure")

    idx = pd.Index(range(24), name="hour")
    arr_cnt = (arr_df.groupby("hour").size() if not arr_df.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)
    dep_cnt = (dep_df.groupby("hour").size() if not dep_df.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)

    out = pd.DataFrame({"arrivals": arr_cnt.astype(int), "departures": dep_cnt.astype(int)})
    return out, prev_day_local.tz_localize(None)  # return local calendar date (naive)


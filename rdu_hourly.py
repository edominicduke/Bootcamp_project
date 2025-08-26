# rdu_hourly.py
# Utilities to fetch previous-day arrivals/departures for an airport (KRDU by default)
# and aggregate counts per local hour using the OpenSky REST API.
#
# Key features:
# - 1-hour windows (<= 2h limit for flights/arrival|departure endpoints)
# - Basic Auth if OPENSKY_USER/OPENSKY_PASS are present (ASCII/Latin-1 only)
# - Gentle pacing + backoff on 429/5xx, no spin on 401/403/404
# - Status histogram exposed for on-page diagnostics
# - Robust conversion to local time and hourly aggregation
#
# Code comments are in English per your request.

from __future__ import annotations

import os
import time
from typing import List, Tuple, Optional, Dict, Any
from collections import Counter

import requests
import pandas as pd

# --------------------------------------------------------------------
# Config
# --------------------------------------------------------------------
OPENSKY_BASE = "https://opensky-network.org/api"
DEFAULT_AIRPORT = "KRDU"               # ICAO for Raleigh–Durham
LOCAL_TZ = "America/New_York"          # Local timezone for hourly aggregation

# Last run's HTTP status histogram (exported via get_last_status_hist)
_LAST_STATUS_HIST: Counter[int] = Counter()


# --------------------------------------------------------------------
# Streamlit-safe notifiers (fallback to print if not running in Streamlit)
# --------------------------------------------------------------------
def _st_info(msg: str) -> None:
    try:
        import streamlit as st
        st.info(msg)
    except Exception:
        print(f"[INFO] {msg}")


def _st_error(msg: str) -> None:
    try:
        import streamlit as st
        st.error(msg)
    except Exception:
        print(f"[ERROR] {msg}")


def get_last_status_hist() -> dict:
    """Expose the last-run HTTP status histogram to the UI."""
    return dict(_LAST_STATUS_HIST)


# --------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------
def _opensky_auth() -> Optional[Tuple[str, str]]:
    """
    Read OpenSky creds from environment and validate for HTTP Basic (RFC 7617).
    - Strips BOM/zero-width chars and surrounding whitespace.
    - Ensures Latin-1 encodability (requests uses latin-1 for Basic Auth).
    Env vars:
      OPENSKY_USER  (OpenSky website username; can be an email)
      OPENSKY_PASS
    Returns:
      (user, pass) or None if missing/invalid (anonymous mode).
    """
    def _clean(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        return s.strip().replace("\ufeff", "").replace("\u200b", "")

    user = _clean(os.getenv("OPENSKY_USER"))
    pw   = _clean(os.getenv("OPENSKY_PASS"))

    if not user or not pw:
        return None

    try:
        user.encode("latin-1")
        pw.encode("latin-1")
    except UnicodeEncodeError:
        _st_error(
            "OPENSKY_USER/OPENSKY_PASS must be ASCII/Latin-1. "
            "Recreate your .env with plain ASCII. "
            "Tip: load_dotenv(override=True) and unset shell leftovers."
        )
        return None

    return (user, pw)


# --------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------
def previous_day_range_utc() -> Tuple[int, int, pd.Timestamp]:
    """
    Compute previous *local* calendar day [00:00, 24:00) in LOCAL_TZ
    and return its corresponding UTC unix timestamps, plus the local date (tz-aware).
    """
    now_local = pd.Timestamp.now(tz=LOCAL_TZ)
    start_local = now_local.floor("D") - pd.Timedelta(days=1)  # yesterday 00:00 local
    end_local = start_local + pd.Timedelta(days=1)             # today 00:00 local
    begin_utc = int(start_local.tz_convert("UTC").timestamp())
    end_utc = int(end_local.tz_convert("UTC").timestamp())
    return begin_utc, end_utc, start_local


# --------------------------------------------------------------------
# Core fetcher with robust pacing/backoff and diagnostics
# --------------------------------------------------------------------
def _fetch_flights(
    kind: str,
    airport: str,
    begin_ts: int,
    end_ts: int,
    window_sec: int = 1 * 3600,   # 1-hour windows (<= 2h limit)
    sleep_between: float = 2.0,   # base pacing between windows (when authed)
) -> List[Dict[str, Any]]:
    """
    Robust fetcher for OpenSky flights/{arrival|departure}.
    Splits the requested range into small windows, throttles, retries transient
    errors, and records status codes for diagnostics.

    Args:
      kind: "arrival" or "departure"
      airport: ICAO code (e.g., "KRDU")
      begin_ts: UTC unix seconds (inclusive)
      end_ts:   UTC unix seconds (exclusive)
      window_sec: window size per request (should be <= 2 hours)
      sleep_between: base sleep between windows (authed). Anonymous uses slower pacing.

    Returns:
      list of flight dicts (possibly empty). When empty, a status histogram is shown.
    """
    assert kind in ("arrival", "departure")

    auth = _opensky_auth()               # (user, pass) or None
    anon_mode = auth is None
    base_sleep = 11.0 if anon_mode else sleep_between  # anonymous must be much slower

    session = requests.Session()
    session.headers.update({"User-Agent": "Bootcamp-RDU-Heatmap/1.0"})

    all_rows: List[Dict[str, Any]] = []
    statuses: List[int] = []

    t0 = begin_ts
    while t0 < end_ts:
        t1 = min(t0 + window_sec, end_ts)
        url = f"{OPENSKY_BASE}/flights/{kind}"
        params = {"airport": airport, "begin": t0, "end": t1}

        # Up to 4 attempts per window. Backoff on 429/5xx, don't spin on 401/403/404.
        back = 1.5
        for attempt in range(4):
            try:
                r = session.get(url, params=params, auth=auth, timeout=30)
                statuses.append(r.status_code)

                if r.status_code == 200:
                    payload = r.json() or []
                    if isinstance(payload, list):
                        all_rows.extend(payload)
                    break

                if r.status_code in (429, 502, 503):
                    # Respect Retry-After header if present, else exponential backoff.
                    ra = r.headers.get("Retry-After")
                    try:
                        wait = float(ra) if ra is not None else back * (attempt + 1)
                    except ValueError:
                        wait = back * (attempt + 1)
                    time.sleep(max(wait, base_sleep))
                    continue

                # 401/403 (auth issue) or 404 (no data) → don't retry this window
                break

            except requests.RequestException:
                time.sleep(back * (attempt + 1))
                continue

        # Gentle pacing between windows
        time.sleep(base_sleep)
        t0 = t1

    # De-duplicate by (icao24, firstSeen, lastSeen)
    seen: set = set()
    uniq: List[Dict[str, Any]] = []
    for row in all_rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row)
            seen.add(key)

    # Export histogram for the UI
    global _LAST_STATUS_HIST
    _LAST_STATUS_HIST = Counter(statuses)

    # Helpful hints when nothing returned
    if not uniq:
        hints = []
        if _LAST_STATUS_HIST.get(401) or _LAST_STATUS_HIST.get(403):
            hints.append("Auth error (401/403): check OPENSKY_USER/OPENSKY_PASS and dotenv override.")
        if _LAST_STATUS_HIST.get(429):
            hints.append("Rate limited (429): try later; avoid repeated clicks; keep 1h windows.")
        if _LAST_STATUS_HIST.get(404):
            hints.append("No data (404) for this airport/time window.")
        _st_info(f"OpenSky replies by status: {dict(_LAST_STATUS_HIST)}. {' '.join(hints)}")

    return uniq


# --------------------------------------------------------------------
# Transform rows → DataFrame and aggregate by local hour
# --------------------------------------------------------------------
def _rows_to_df(rows: List[Dict[str, Any]], kind: str) -> pd.DataFrame:
    """
    Convert OpenSky rows to a DataFrame and derive local hour.
    For arrivals: use 'lastSeen'. For departures: use 'firstSeen'.
    Returns columns: ['hour','callsign','icao24','ts_local','estDepartureAirport','estArrivalAirport']
    """
    if not rows:
        return pd.DataFrame(columns=["hour", "callsign", "icao24", "ts_local",
                                     "estDepartureAirport", "estArrivalAirport"])
    df = pd.DataFrame(rows)
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"

    dt_local = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts_local"] = dt_local
    df["hour"] = df["ts_local"].dt.hour

    cols = ["hour", "callsign", "icao24", "ts_local", "estDepartureAirport", "estArrivalAirport"]
    return df.reindex(columns=cols)


# --------------------------------------------------------------------
# Public API: main function for the Streamlit app
# --------------------------------------------------------------------
def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """
    Build a 24-hour table (index 0..23) with columns:
      - arrivals:   count of arrivals per local hour
      - departures: count of departures per local hour
    Returns:
      (counts_df, previous_day_local_date) where the date is a tz-naive local date.
    """
    begin_ts, end_ts, prev_day_local = previous_day_range_utc()

    arrivals_rows   = _fetch_flights("arrival",   airport, begin_ts, end_ts)
    departures_rows = _fetch_flights("departure", airport, begin_ts, end_ts)

    arr_df = _rows_to_df(arrivals_rows, "arrival")
    dep_df = _rows_to_df(departures_rows, "departure")

    idx = pd.Index(range(24), name="hour")
    arr_cnt = (arr_df.groupby("hour").size() if not arr_df.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)
    dep_cnt = (dep_df.groupby("hour").size() if not dep_df.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)

    out = pd.DataFrame({"arrivals": arr_cnt.astype(int), "departures": dep_cnt.astype(int)})

    # Return local calendar date without tz (e.g., 2025-08-24)
    return out, prev_day_local.tz_localize(None)


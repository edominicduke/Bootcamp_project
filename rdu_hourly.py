# rdu_hourly.py  — keep it as simple as fetchapi.py style

import os
import time
import requests
import pandas as pd
# put this near the top of rdu_hourly.py
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*a, **k): pass

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)
# Minimal constants (like fetchapi.py)
OPENSKY_URL_ARR = "https://opensky-network.org/api/flights/arrival"
OPENSKY_URL_DEP = "https://opensky-network.org/api/flights/departure"

DEFAULT_AIRPORT = "KRDU"
LOCAL_TZ = "America/New_York"


def _maybe_auth():
    """Return (user, pass) if present; otherwise None (anonymous)."""
    u = os.getenv("OPENSKY_USER")
    p = os.getenv("OPENSKY_PASS")
    if u and p:
        return (u.strip(), p.strip())
    return None


def _yday_local_range_utc():
    """
    Previous local calendar day [00:00, 24:00) in LOCAL_TZ, returned as UTC seconds,
    plus the local tz-aware date (for labeling).
    """
    start_local = pd.Timestamp.now(tz=LOCAL_TZ).floor("D") - pd.Timedelta(days=1)
    end_local = start_local + pd.Timedelta(days=1)
    begin_utc = int(start_local.tz_convert("UTC").timestamp())
    end_utc   = int(end_local.tz_convert("UTC").timestamp())
    return begin_utc, end_utc, start_local


def _fetch_flights(kind: str, airport: str, begin_ts: int, end_ts: int) -> list:
    """
    Fetch flights/{arrival|departure} in 1h windows.
    Follows fetchapi.py style: plain GET + explicit status checks.
    Raises RuntimeError on non-success statuses (except 404 which means “no data”).
    """
    assert kind in ("arrival", "departure")
    url = OPENSKY_URL_ARR if kind == "arrival" else OPENSKY_URL_DEP
    auth = _maybe_auth()  # None (anonymous) or (user, pass)
    rows = []

    t0 = begin_ts
    while t0 < end_ts:
        t1 = min(t0 + 3600, end_ts)  # 1h window
        params = {"airport": airport, "begin": t0, "end": t1}
        r = requests.get(url, params=params, auth=auth, timeout=30)

        # Handle statuses exactly (like fetchapi.py does for /states/all)
        if r.status_code == 200:
            data = r.json() or []
            if isinstance(data, list):
                rows.extend(data)
        elif r.status_code == 404:
            # no data for this window; fine, move on
            pass
        else:
            # 401/403 (no/invalid auth), 429 (rate-limit), 5xx… → explicit error
            # Keep message short to mirror fetchapi.py style
            snippet = r.text[:200]
            raise RuntimeError(f"OpenSky {kind} {r.status_code} {r.reason} -> {snippet}")

        # Be gentle to the API; anonymous needs more delay to avoid 429
        time.sleep(1.5 if auth else 10.0)
        t0 = t1

    # Deduplicate by (icao24, firstSeen, lastSeen)
    seen, uniq = set(), []
    for row in rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row)
            seen.add(key)
    return uniq


def _rows_to_hours(rows: list, kind: str, tz: str) -> pd.DataFrame:
    """
    Convert rows to a single 'hour' column in local tz.
    For arrivals use 'lastSeen', for departures use 'firstSeen'.
    """
    if not rows:
        return pd.DataFrame(columns=["hour"])
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    df = pd.DataFrame(rows)
    df["ts_local"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(tz)
    df["hour"] = df["ts_local"].dt.hour
    return df[["hour"]]


def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT):
    """
    Public API for Streamlit: fetch previous-day arrivals & departures for `airport`,
    aggregate to a 24x2 table (arrivals/departures), and return (counts_df, local_date_naive).
    Raises RuntimeError on HTTP errors, same spirit as fetchapi.py.
    """
    begin_ts, end_ts, local_day = _yday_local_range_utc()

    arrivals = _fetch_flights("arrival", airport, begin_ts, end_ts)
    departures = _fetch_flights("departure", airport, begin_ts, end_ts)

    dfA = _rows_to_hours(arrivals, "arrival", LOCAL_TZ)
    dfD = _rows_to_hours(departures, "departure", LOCAL_TZ)

    idx = pd.Index(range(24), name="hour")
    sA = (dfA.groupby("hour").size() if not dfA.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)
    sD = (dfD.groupby("hour").size() if not dfD.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)

    out = pd.DataFrame({"arrivals": sA.astype(int), "departures": sD.astype(int)})
    return out, local_day.tz_localize(None)



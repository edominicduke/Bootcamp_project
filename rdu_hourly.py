# rdu_hourly.py — Robust previous-day hourly arrivals/departures for an airport (OpenSky)
# English comments, minimal deps (requests, pandas). Compatible with your fetchapi.py style.

from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple, Optional

import requests
import pandas as pd

# --- OAuth2 client-credentials (OpenSky API Client) ---
TOKEN_URL = os.getenv(
    "OPENSKY_TOKEN_URL",
    "https://auth.opensky-network.org/realms/opensky-network/protocol/openid-connect/token",
)
_token_cache = {"access_token": None, "exp": 0.0}

def _get_bearer_token():
    """Return a cached OAuth2 bearer token if OPENSKY_CLIENT_ID/SECRET are set; else None."""
    cid = os.getenv("OPENSKY_CLIENT_ID")
    cs  = os.getenv("OPENSKY_CLIENT_SECRET")
    if not cid or not cs:
        return None
    # valid cache?
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["exp"] - 60:
        return _token_cache["access_token"]
    # fetch new token
    try:
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": cs},
            timeout=30,
        )
        _bump_status(resp.status_code)
        if resp.status_code != 200:
            return None
        j = resp.json() or {}
        tok = j.get("access_token")
        if tok:
            _token_cache["access_token"] = tok
            _token_cache["exp"] = now + float(j.get("expires_in", 3600))
            return tok
    except requests.RequestException:
        return None
    return None


# -----------------------------
# Config & constants
# -----------------------------
DEFAULT_AIRPORT = "KRDU"
LOCAL_TZ = "America/New_York"

OPENSKY_URL_ARR = "https://opensky-network.org/api/flights/arrival"
OPENSKY_URL_DEP = "https://opensky-network.org/api/flights/departure"
OPENSKY_URL_ALL = "https://opensky-network.org/api/flights/all"

# Slice sizes (OpenSky prefers small windows)
ARR_DEP_WINDOW_SEC = 3600   # 1 hour slices
ALL_WINDOW_SEC     = 1800   # 30 min slices (when using flights/all fallback)

# Gentle throttling (anonymous calls need longer delays)
AUTH_SLEEP_SEC = 1.5
ANON_SLEEP_SEC = 10.0

# If True and credentials are missing / non Latin-1, we still proceed anonymously (will likely yield empty)
REQUIRE_AUTH = False  # keep False to avoid crashing UI; your page can show status histogram


# -----------------------------
# .env loader (bulletproof; no hard dependency on python-dotenv)
# -----------------------------
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*a, **k):  # no-op if library not installed
        pass

from pathlib import Path

def _load_env_bulletproof() -> Optional[Path]:
    """
    Load .env from common locations (same dir, project root, CWD).
    Returns the path that was used, or None.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        here / ".env",           # alongside rdu_hourly.py
        here.parent / ".env",    # project root
        Path.cwd() / ".env",     # current working dir
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p, override=True)
            return p
    load_dotenv(override=True)  # best-effort default search
    return None

_LOADED_ENV_PATH = _load_env_bulletproof()


# -----------------------------
# Status histogram for diagnostics
# -----------------------------
_STATUS_HIST: Dict[int, int] = {}

def _bump_status(code: int) -> None:
    _STATUS_HIST[code] = _STATUS_HIST.get(code, 0) + 1

def get_last_status_hist() -> Dict[int, int]:
    """Return a shallow copy of the accumulated HTTP status code histogram."""
    return dict(_STATUS_HIST)

def reset_status_hist() -> None:
    _STATUS_HIST.clear()


# -----------------------------
# Auth & request helpers
# -----------------------------
def _maybe_auth() -> Optional[Tuple[str, str]]:
    """
    Return (user, pass) if present & Latin-1 encodable; else None (anonymous).
    We don't raise by default to keep the UI smooth; status histogram will tell if 401/403 happens.
    """
    u = (os.getenv("OPENSKY_USER") or "").strip()
    p = (os.getenv("OPENSKY_PASS") or "").strip()
    if not u or not p:
        return None
    try:
        u.encode("latin-1"); p.encode("latin-1")
    except UnicodeEncodeError:
        # Credentials contain non Latin-1 characters; requests' HTTPBasicAuth would crash.
        return None
    return (u, p)

def _do_get(url: str, params: Dict, auth: Optional[Tuple[str, str]], timeout: int = 30) -> requests.Response:
    headers = {}
    bearer = _get_bearer_token()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
        auth = None  # use OAuth2 instead of Basic
    r = requests.get(url, params=params, auth=auth, headers=headers, timeout=timeout)
    _bump_status(r.status_code)
    return r



# -----------------------------
# Time helpers
# -----------------------------
def _previous_local_day_utc_range() -> Tuple[int, int, pd.Timestamp]:
    """
    Previous local calendar day [00:00, 24:00) in LOCAL_TZ, as (begin_utc, end_utc, local_day_start).
    local_day_start is tz-aware; we return naive at the end for Streamlit label.
    """
    start_local = pd.Timestamp.now(tz=LOCAL_TZ).floor("D") - pd.Timedelta(days=1)
    end_local = start_local + pd.Timedelta(days=1)
    begin_utc = int(start_local.tz_convert("UTC").timestamp())
    end_utc   = int(end_local.tz_convert("UTC").timestamp())
    return begin_utc, end_utc, start_local


# -----------------------------
# Fetchers
# -----------------------------
def _fetch_flights(kind: str, airport: str, begin_ts: int, end_ts: int) -> List[dict]:
    """
    Fetch flights/{arrival|departure} in 1-hour windows. Collects items across slices.
    Non-200 and non-404 are just recorded in histogram; we move on (to keep UI resilient).
    """
    assert kind in ("arrival", "departure")
    url = OPENSKY_URL_ARR if kind == "arrival" else OPENSKY_URL_DEP
    auth = _maybe_auth()
    rows: List[dict] = []

    t0 = begin_ts
    while t0 < end_ts:
        t1 = min(t0 + ARR_DEP_WINDOW_SEC, end_ts)
        params = {"airport": airport, "begin": t0, "end": t1}
        try:
            r = _do_get(url, params=params, auth=auth)
            if r.status_code == 200:
                data = r.json() or []
                if isinstance(data, list):
                    rows.extend(data)
            elif r.status_code == 404:
                # No data for this slice; fine
                pass
            else:
                # 401/403/429/5xx... we just record & move on (so the app doesn't hard-fail)
                pass
        except requests.RequestException:
            # transient network error; skip this slice
            pass

        time.sleep(AUTH_SLEEP_SEC if auth else ANON_SLEEP_SEC)
        t0 = t1

    return _dedup_rows(rows)


def _fetch_flights_all(begin_ts: int, end_ts: int) -> List[dict]:
    """
    Fallback: fetch flights/all in 30-min windows with Basic Auth if present (highly recommended).
    Caller will filter by estArrivalAirport / estDepartureAirport.
    """
    auth = _maybe_auth()
    rows: List[dict] = []
    t0 = begin_ts
    while t0 < end_ts:
        t1 = min(t0 + ALL_WINDOW_SEC, end_ts)
        params = {"begin": t0, "end": t1}
        try:
            r = _do_get(OPENSKY_URL_ALL, params=params, auth=auth)
            if r.status_code == 200:
                data = r.json() or []
                if isinstance(data, list):
                    rows.extend(data)
            elif r.status_code == 404:
                pass
            else:
                pass
        except requests.RequestException:
            pass

        time.sleep(AUTH_SLEEP_SEC if auth else ANON_SLEEP_SEC)
        t0 = t1

    return _dedup_rows(rows)


def _dedup_rows(rows: List[dict]) -> List[dict]:
    """Deduplicate by (icao24, firstSeen, lastSeen)."""
    uniq: List[dict] = []
    seen = set()
    for r in rows:
        key = (r.get("icao24"), r.get("firstSeen"), r.get("lastSeen"))
        if key not in seen:
            uniq.append(r)
            seen.add(key)
    return uniq


# -----------------------------
# Transform
# -----------------------------
def _rows_to_hours(rows: List[dict], kind: str, tz_name: str) -> pd.DataFrame:
    """
    Map rows → hour-of-day in the given timezone.
    For arrivals use 'lastSeen', for departures use 'firstSeen'.
    Returns a DataFrame with a single 'hour' column (0..23).
    """
    if not rows:
        return pd.DataFrame(columns=["hour"])
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    df = pd.DataFrame(rows)
    # Convert epoch secs → tz-aware, then extract hour
    df["ts_local"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(tz_name)
    df["hour"] = df["ts_local"].dt.hour
    return df[["hour"]]


# -----------------------------
# Public API
# -----------------------------
def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT) -> Tuple[pd.DataFrame, pd.Timestamp]:
    """
    Build a 24×2 table of arrivals & departures per hour for the previous local day.
    Strategy:
      1) Try flights/arrival + flights/departure (1h slices).
      2) If both empty, fallback to flights/all (30m slices) and filter by airport.
    Returns (counts_df, used_local_date_naive).
    """
    begin_ts, end_ts, local_day = _previous_local_day_utc_range()

    # First attempt: arrival + departure endpoints
    arr_rows = _fetch_flights("arrival", airport, begin_ts, end_ts)
    dep_rows = _fetch_flights("departure", airport, begin_ts, end_ts)

    # Fallback if both sides empty: use flights/all and filter locally
    if not arr_rows and not dep_rows:
        all_rows = _fetch_flights_all(begin_ts, end_ts)
        if all_rows:
            arr_rows = [r for r in all_rows if r.get("estArrivalAirport") == airport]
            dep_rows = [r for r in all_rows if r.get("estDepartureAirport") == airport]

    # Aggregate to hourly counts
    df_arr = _rows_to_hours(arr_rows, "arrival", LOCAL_TZ)
    df_dep = _rows_to_hours(dep_rows, "departure", LOCAL_TZ)

    idx = pd.Index(range(24), name="hour")
    sA = (df_arr.groupby("hour").size() if not df_arr.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)
    sD = (df_dep.groupby("hour").size() if not df_dep.empty else pd.Series(dtype="int64")).reindex(idx, fill_value=0)

    out = pd.DataFrame({"arrivals": sA.astype(int), "departures": sD.astype(int)})

    # Return date as naive TS (for Streamlit labeling)
    return out, local_day.tz_localize(None)

    return out, local_day.tz_localize(None)



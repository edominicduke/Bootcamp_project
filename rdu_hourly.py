# rdu_hourly.py
import os, time, requests, pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

OPENSKY_BASE = "https://opensky-network.org/api"
LOCAL_TZ = ZoneInfo("America/New_York")
DEFAULT_AIRPORT = "KRDU"

def _opensky_auth():
    u, p = os.getenv("OPENSKY_USER"), os.getenv("OPENSKY_PASS")
    return (u, p) if u and p else None

def previous_day_range_utc(tz: ZoneInfo = LOCAL_TZ):
    now_local = datetime.now(tz)
    prev_day = now_local.date() - timedelta(days=1)
    start_local = datetime.combine(prev_day, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return int(start_local.astimezone(timezone.utc).timestamp()), int(end_local.astimezone(timezone.utc).timestamp()), prev_day

def _fetch_flights(kind: str, airport: str, begin_ts: int, end_ts: int, window_sec: int = 2*3600):
    assert kind in ("arrival", "departure")
    auth = _opensky_auth()
    all_rows, t0 = [], begin_ts
    while t0 < end_ts:
        t1 = min(t0 + window_sec, end_ts)
        url = f"{OPENSKY_BASE}/flights/{kind}"
        params = {"airport": airport, "begin": t0, "end": t1}
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, auth=auth, timeout=30)
                if r.status_code == 200:
                    all_rows += (r.json() or [])
                    break
                if r.status_code in (429, 502, 503):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except requests.RequestException:
                time.sleep(1.5 * (attempt + 1))
        time.sleep(0.3)
        t0 = t1
    seen, uniq = set(), []
    for row in all_rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row); seen.add(key)
    return uniq

def _rows_to_df(rows: list, kind: str):
    import pandas as pd
    if not rows:
        return pd.DataFrame(columns=["hour","callsign","icao24","ts_local","estDepartureAirport","estArrivalAirport"])
    df = pd.DataFrame(rows)
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    dt_local = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts_local"] = dt_local; df["hour"] = df["ts_local"].dt.hour
    keep = ["hour","callsign","icao24","ts_local","estDepartureAirport","estArrivalAirport"]
    return df[keep]

def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT):
    import pandas as pd
    begin_ts, end_ts, prev_day = previous_day_range_utc(LOCAL_TZ)
    arr = _rows_to_df(_fetch_flights("arrival", airport, begin_ts, end_ts), "arrival")
    dep = _rows_to_df(_fetch_flights("departure", airport, begin_ts, end_ts), "departure")
    idx = pd.Index(range(24), name="hour")
    arr_cnt = arr.groupby("hour").size().reindex(idx, fill_value=0)
    dep_cnt = dep.groupby("hour").size().reindex(idx, fill_value=0)
    return pd.DataFrame({"arrivals": arr_cnt, "departures": dep_cnt}), prev_day

# rdu_hourly.py
import os, time, requests, pandas as pd
from datetime import timedelta

OPENSKY_BASE = "https://opensky-network.org/api"
DEFAULT_AIRPORT = "KRDU"
LOCAL_TZ = "America/New_York"

def _opensky_auth():
    u, p = os.getenv("OPENSKY_USER"), os.getenv("OPENSKY_PASS")
    return (u, p) if u and p else None

def previous_day_range_utc():
    """
    计算“上一天”的本地自然日[00:00, 24:00)（America/New_York），再转 UTC 秒级时间戳。
    返回: (begin_ts_utc, end_ts_utc, prev_day_date)
    """
    now_local = pd.Timestamp.now(tz=LOCAL_TZ)
    start_local = now_local.floor("D") - pd.Timedelta(days=1)  # 昨天 00:00（本地时区）
    end_local = start_local + pd.Timedelta(days=1)             # 今天 00:00（本地时区）
    start_utc = start_local.tz_convert("UTC").to_pydatetime().timestamp()
    end_utc = end_local.tz_convert("UTC").to_pydatetime().timestamp()
    return int(start_utc), int(end_utc), start_local.date()

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
                    time.sleep(1.5 * (attempt + 1)); continue
                break
            except requests.RequestException:
                time.sleep(1.5 * (attempt + 1))
        time.sleep(0.3)
        t0 = t1
    # 去重
    seen, uniq = set(), []
    for row in all_rows:
        key = (row.get("icao24"), row.get("firstSeen"), row.get("lastSeen"))
        if key not in seen:
            uniq.append(row); seen.add(key)
    return uniq

def _rows_to_df(rows: list, kind: str):
    if not rows:
        return pd.DataFrame(columns=["hour","callsign","icao24","ts_local","estDepartureAirport","estArrivalAirport"])
    df = pd.DataFrame(rows)
    ts_col = "lastSeen" if kind == "arrival" else "firstSeen"
    dt_local = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(LOCAL_TZ)
    df["ts_local"] = dt_local
    df["hour"] = df["ts_local"].dt.hour
    return df[["hour","callsign","icao24","ts_local","estDepartureAirport","estArrivalAirport"]]

def hourly_counts_for_previous_day(airport: str = DEFAULT_AIRPORT):
    """
    返回 (counts_df, prev_day_date)
    counts_df: index=0..23, columns=['arrivals','departures']
    """
    begin_ts, end_ts, prev_day = previous_day_range_utc()
    arr = _rows_to_df(_fetch_flights("arrival", airport, begin_ts, end_ts), "arrival")
    dep = _rows_to_df(_fetch_flights("departure", airport, begin_ts, end_ts), "departure")
    idx = pd.Index(range(24), name="hour")
    arr_cnt = arr.groupby("hour").size().reindex(idx, fill_value=0)
    dep_cnt = dep.groupby("hour").size().reindex(idx, fill_value=0)
    return pd.DataFrame({"arrivals": arr_cnt, "departures": dep_cnt}), prev_day

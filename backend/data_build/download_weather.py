#!/usr/bin/env python3
"""Task A1: download past airport weather and official forecasts (TAF) for Florida.

Source: Iowa Environmental Mesonet (IEM), https://mesonet.agron.iastate.edu/request/download.phtml
  - ASOS reports (routine hourly reports plus "special" reports issued when weather changes)
  - TAF archive (the official airport forecast, used as a baseline the model must beat)

Run from the repo root:
    python backend/data_build/download_weather.py                # every station, all of 2019-2024
    python backend/data_build/download_weather.py --stations KTPA KMCO --years 2024
    python backend/data_build/download_weather.py --months 6 9   # only June to September
    python backend/data_build/download_weather.py --force        # download again even if present

Output goes to data/raw/ (gitignored): asos/<ICAO>_<year>.csv and taf/<ICAO>_<year>.csv.
The script is safe to re-run: files already on disk are skipped (use --force after
changing --months). Standard library only. The full download is about 500 MB.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATIONS_CSV = REPO / "data" / "seeds" / "stations.csv"
RAW = REPO / "data" / "raw"
USER_AGENT = "car-or-air-hackathon/0.1 (student project)"
ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
TAF_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py"
PAUSE_S = 1.0  # be polite to a free public service


def all_stations() -> list[str]:
    with open(STATIONS_CSV, newline="") as f:
        return [r["icao"] for r in csv.DictReader(f)]


def fetch(url: str, tries: int = 4) -> str:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"    retry in {wait}s ({err})", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def asos_url(icao: str, year: int, m1: int, m2: int) -> str:
    # IEM uses the 3-letter id for U.S. stations (KTPA -> TPA). Month m2 is inclusive.
    end_year, end_month = (year, m2 + 1) if m2 < 12 else (year + 1, 1)
    params = [
        ("station", icao[1:]), ("data", "all"),
        ("year1", year), ("month1", m1), ("day1", 1),
        ("year2", end_year), ("month2", end_month), ("day2", 1),
        ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "no"), ("elev", "no"),
        ("missing", "M"), ("trace", "T"), ("direct", "no"),
        ("report_type", 3), ("report_type", 4),  # 3 = routine, 4 = special
    ]
    return ASOS_URL + "?" + urllib.parse.urlencode(params)


def taf_url(icao: str, year: int, m1: int, m2: int) -> str:
    end_year, end_month = (year, m2 + 1) if m2 < 12 else (year + 1, 1)
    params = {"station": icao, "sts": f"{year}-{m1:02d}-01T00:00Z",
              "ets": f"{end_year}-{end_month:02d}-01T00:00Z", "fmt": "csv"}
    return TAF_URL + "?" + urllib.parse.urlencode(params)


def rows_in(text: str) -> int:
    return max(0, sum(1 for line in text.splitlines() if line.strip()) - 1)


def download(kind: str, url: str, dest: Path, header_start: str, force: bool) -> int:
    if dest.exists() and not force:
        return rows_in(dest.read_text(encoding="utf-8"))
    text = fetch(url)
    if not text.startswith(header_start):
        raise RuntimeError(f"{kind}: unexpected answer for {dest.name}: {text[:120]!r}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(dest)  # a half-written file never looks finished
    time.sleep(PAUSE_S)
    return rows_in(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stations", nargs="*", default=None, help="ICAO ids; default: all in stations.csv")
    ap.add_argument("--years", nargs="*", type=int, default=list(range(2019, 2025)))
    ap.add_argument("--months", nargs=2, type=int, default=[1, 12], metavar=("FIRST", "LAST"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    stations = args.stations or all_stations()
    m1, m2 = args.months

    print(f"{'station':8} {'year':5} {'weather reports':>16} {'forecast rows':>14}")
    total_obs = total_taf = 0
    for icao in stations:
        for year in args.years:
            n_obs = download("asos", asos_url(icao, year, m1, m2),
                             RAW / "asos" / f"{icao}_{year}.csv", "station,valid", args.force)
            n_taf = download("taf", taf_url(icao, year, m1, m2),
                             RAW / "taf" / f"{icao}_{year}.csv", "station,valid", args.force)
            total_obs += n_obs
            total_taf += n_taf
            print(f"{icao:8} {year:<5} {n_obs:>16,} {n_taf:>14,}", flush=True)
    print(f"{'TOTAL':14} {total_obs:>16,} {total_taf:>14,}")
    print(f"Saved under {RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

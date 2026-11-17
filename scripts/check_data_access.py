#!/usr/bin/env python3
"""Day-1 check: can this machine reach every data source the plan relies on?

Run:  python3 scripts/check_data_access.py
Uses only the Python standard library. No keys needed. Safe to run repeatedly.
Share the printed table with your teammate so you both know what works.
"""
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "fl-aam-hackathon-check/1.0"
TIMEOUT = 25

OVERPASS_QUERY = '[out:json][timeout:20];nwr["aeroway"="helipad"](27.9,-82.55,28.0,-82.4);out count;'

# (name, url, optional POST body, what a good answer contains)
CHECKS = [
    ("Aviation Weather (METAR)", "https://aviationweather.gov/api/data/metar?ids=KMCO&format=json", None, "icaoId"),
    ("NWS API (point)", "https://api.weather.gov/points/28.43,-81.31", None, "gridId"),
    ("IEM hourly history", "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=MCO&data=metar&year1=2024&month1=7&day1=15&year2=2024&month2=7&day2=16&tz=UTC&format=onlycomma", None, "station"),
    ("IEM forecast (TAF) archive", "https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py?station=KMCO&sts=2024-07-15T00:00Z&ets=2024-07-16T00:00Z&fmt=csv", None, "station"),
    ("OSRM route", "https://router.project-osrm.org/route/v1/driving/-82.4572,27.9506;-81.3792,28.5383?overview=false", None, "routes"),
    ("OpenStreetMap Overpass", "https://overpass-api.de/api/interpreter", "data=" + urllib.parse.quote(OVERPASS_QUERY), "elements"),
    ("HRRR on AWS (list)", "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/?list-type=2&max-keys=1", None, "ListBucketResult"),
    ("MRMS radar on AWS", "https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&max-keys=1", None, "ListBucketResult"),
    ("GOES-19 lightning on AWS", "https://noaa-goes19.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/2026/&max-keys=1", None, "ListBucketResult"),
    ("FAA 28-day data page", "https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/2026-10-29/", None, "APT"),
    ("FAA data download host", "https://nfdc.faa.gov/webContent/28DaySub/TXT_to_CSV_Mapping.pdf", None, None),
    ("Florida DOH trauma page", "https://www.floridahealth.gov/licensing-regulations/trauma-system/trauma-center-designation/", None, "Trauma"),
    ("Census API (needs a free key)", "https://api.census.gov/data/2022/acs/acs5?get=NAME&for=state:12", None, None),
    ("FAWN weather stations", "https://fawn.ifas.ufl.edu/controller.php/today/", None, None),
    ("FAA wildlife strikes", "https://wildlife.faa.gov/", None, None),
    ("USGS aerial imagery service", "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer?f=pjson", None, "serviceDescription"),
    ("FL511 (key needed for API)", "https://fl511.com/", None, None),
    ("Orlando open data portal", "https://data.cityoforlando.net/", None, None),
    ("Joby technology page", "https://www.jobyaviation.com/technology", None, "passenger"),
    ("Beta aircraft page", "https://beta.team/aircraft", None, "Passenger"),
]


def check(name, url, body, needle):
    start = time.time()
    try:
        data = body.encode() if body else None
        req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            text = resp.read(200_000).decode("utf-8", errors="ignore")
            status = resp.status
        ok = status == 200 and (needle is None or needle in text)
        note = "ok" if ok else ("reachable, unexpected content" if status == 200 else f"HTTP {status}")
    except urllib.error.HTTPError as err:
        ok, note = False, f"HTTP {err.code}"
    except (urllib.error.URLError, socket.timeout, ConnectionError) as err:
        ok, note = False, f"failed: {getattr(err, 'reason', err)}"
    return ok, note, time.time() - start


def main():
    print(f"{'Source':34} {'Result':8} {'Time':>6}  Note")
    print("-" * 78)
    failures = 0
    for name, url, body, needle in CHECKS:
        ok, note, secs = check(name, url, body, needle)
        failures += 0 if ok else 1
        print(f"{name:34} {'OK' if ok else 'CHECK':8} {secs:5.1f}s  {note}")
    print("-" * 78)
    print(f"{len(CHECKS) - failures} of {len(CHECKS)} fully OK. "
          "'CHECK' means: look at it manually, it may need a key or a different URL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

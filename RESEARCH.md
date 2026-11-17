# Research notes: "Car or Air"

Last updated 2026-11-17. This is everything we learned before building. Every claim has a confidence tag, and anything we could not confirm is listed in section 10.

**Confidence tags**

- **[official]** comes from a primary source (the manufacturer's own site, a government site, or the FAA database).
- **[reported]** comes from news or secondary sources. Treat it as likely, not certain.
- **[estimate]** is an unofficial number from an analysis.
- **[assumption]** is ours. Every assumption must be visible in the app and easy to change.
- **[verify]** means we could not confirm it. Check it before relying on it.

---

## 1. Where air taxis stand (Nov 2026)

- No US air taxi has FAA approval (a "type certificate") yet. [reported]
- Joby and Archer both pushed first passenger service to 2027. [reported]
- Joby is in the final stage of certification testing. Sources disagree on whether that is stage 4 or 5. [reported]
- Archer closed phase 3 and is in phase 4 testing. As of Aug 2026 it had not yet done its first piloted hover-to-forward-flight transition. [reported]
- Beta's runway-based CX300 is flying. The company says it expects approval around the end of 2026. [reported]
- Electra's EL9 is a hybrid-electric, 9-seat plane. First airframes are expected in 2027. [reported]
- Lilium and Overair shut down. Supernal paused development. CityAirbus and Textron's Nexus were halted. Volocopter's status is disputed. [reported]
- EHang's EH216-S (2 seats, no pilot) is the only one certified, and only by China's regulator. [reported]

**What this means for us:** no real air taxi can be dispatched today. Our demo uses a clearly labeled *simulated* aircraft profile.

## 2. Aircraft specs we can use

| Aircraft | Seats / payload | Speed | Range | Charge / other | Confidence |
|---|---|---|---|---|---|
| **Joby S4** (vertical takeoff) | Pilot + 4 passengers, 4 carry-on bags | Up to 200 mph (174 kt) | **Not published on Joby's site.** About 100 mi incl. reserves is widely reported; 150 mi is reported as unloaded | Max gross weight 5,300 lb; service ceiling 10,000 ft; 6 tilting propellers, 4 battery packs; transition at 45 to 90 kt; noise 45 dBA cruise (from 1,640 ft) and 65 dBA landing (from 330 ft) | Weight, speed, seats, noise [official]; range [reported]; battery about 160 kWh [estimate]; some analyses say up to 200 kWh |
| **Archer Midnight** (vertical takeoff) | Pilot + 4 passengers, over 1,000 lb payload | About 150 mph cruise | About 100 mi max, designed for back-to-back hops of about 20 mi | About 10 min charge between hops claimed; takeoff weight reported at 6,500 to 7,000 lb; noise about 45 dBA cruise design target | 2022 launch claims [reported] |
| **Beta Alia CX300** (needs a runway) | 5 passengers, 200 cubic feet of cargo | Max 153 kt | Max demonstrated 336 nautical miles | **35 min** optimized charge time; wingspan 50 ft; lands at airports only | [official] |
| **Beta Alia A250** (vertical takeoff) | Same airframe and capacity | Max 153 kt | Design target 250 nm | 35 min charge; airports and vertiports | [official] (shares page with CX300) |
| **Electra EL9** (about 150 ft runway, hybrid) | 9 passengers or about 3,000 lb cargo | About 175 kt (about 200 mph) | About 380 mi (330 nm) | Hybrid-electric (battery plus turbine generator) | [reported] |

Other Beta facts:

- Beta claims **$28 per hour** in energy cost versus $311 per hour for a Bell 407 helicopter (84% less). That is a marketing claim. [official claim]
- Beta's customers include Metro Aviation (up to 20 Alia 250 for emergency response and intra-hospital transport) and New Zealand Air Ambulance (2 for 2028). [reported]
- Beta and United Therapeutics flew an FAA-program organ-transport test from Virginia to Maryland in July 2026. [reported]

**Never found:** wind or gust limits, or hot-weather limits, for Joby or Archer. A stretcher or patient-carrying configuration for Joby or Archer. Official battery sizes.

## 3. What is happening in Florida right now

- **The FAA program:** Florida is one of eight state projects in the FAA's eVTOL Integration Pilot Program (eIPP), announced March 2026. It is a 3-year program. FDOT leads, with Archer, Beta, Electra and Joby as partners. [reported]
- **Phases:** cargo delivery, passenger transport, automation, and medical response. No named Florida hospital partners were found. [reported]
- **Flights so far:**
  - Joby began piloted flights Oct 30, 2026: St. Petersburg to Tampa International, then Orlando International (a new pad near Terminal C), then Kennedy Space Center. [reported]
  - Beta flew 14 flights (about 700 nm) with its CX300 in the Tampa and Orlando regions. [reported]
  - Archer is targeting Miami to West Palm Beach, with a wider network connecting Miami, Fort Lauderdale and Palm Beach airports. A reported one-way fare of up to $200. [reported]
- **Network plans:** phase 1 is the I-4 corridor (Tampa to Orlando, Space Coast, and the SunTrax test site in Auburndale, which has one pad built and one under construction). Other proposed routes: Tampa to Naples, Miami to Key West, Pensacola to Tallahassee. FDOT screened 239,000 parcels and identified 30+ pad sites. These are proposals, and no operator has a binding agreement. [reported]
- **Florida HB 1093:**
  - Signed April 20, 2026, effective July 1, 2026.
  - FDOT may pay up to 100% of public vertiport costs when no federal money is available, or up to 80% of the non-federal share when it is.
  - No dollar figure was attached.
  - Adds vertiports to public-private partnership rules and adds sales tax exemptions for eVTOL aircraft, batteries and training.
  - The final version covers public vertiports only. [reported]
- **Orlando International** has proposed a "vertistop" at Surface Lot Atlantis, subject to approvals. [reported]
- The commercial launch target of December 2026 is described as a goal, not a schedule. [reported]

## 4. Medical facts

**Time limits** (secondary sources, so verify with clinical guidelines before real use):

| Condition | Target |
|---|---|
| Stroke, clot-busting drug | Door to needle under 60 min |
| Stroke, clot removal | Door to puncture under 90 min |
| Stroke, clot removal window | Up to 24 hours from symptoms for selected patients |
| Heart attack (STEMI) | Door to balloon within 90 min is linked to better outcomes |
| Trauma "golden hour" | No solid trauma-specific window found. Do not hard-code. |

| Organ | Rough window on ice |
|---|---|
| Heart | 4 to 6 hours |
| Lungs | 6 to 8 hours (some say 4 to 8) |
| Liver | 8 to 12 hours (some say up to 24) |
| Pancreas | 12 to 18 hours |
| Intestine | 6 to 12 hours |
| Kidney | 24 to 36 hours |

These are guidelines, not hard cutoffs. Machine perfusion extends them. [reported]

**Air versus ground:**

- A Swiss study of 645 heart and stroke transfers found helicopters faster above **51.3 km (about 32 miles)** of road distance. The median total mission time was about 60 min. It covers one country and one provider. [reported]
- Typical helicopter launch delay: median **9 min** in Montana (lift-off), mean 9.1 min in Iran (activation), call-to-activation median 7 min in a Sweden-area study. Definitions differ. [reported]
- A Finland study found **20%** of air ambulance missions could not fly because of weather. That is an icing-prone northern region, so do not apply it to Florida. [reported]

**Florida hospitals and pads:**

- The FAA database (Oct 29, 2026 cycle) lists **387 Florida heliports**, 386 private-use. About **207 have hospital or medical-style names** (a rough name match, not verified). Examples: Advent Health Altamonte Springs, DeSoto Memorial (Arcadia), Barton Regional (Bartow), Lakeside Medical Center (Belle Glade). [official data, our filter]
- Florida had **36 trauma centers** on May 1, 2026: 11 Level I, 22 Level II, 3 standalone pediatric. Level I names seen in a 2025 state list include Broward Health Medical Center, Delray Medical Center, HCA Florida Kendall, Jackson Memorial, Orlando Regional Medical Center, St. Mary's Medical Center, Tampa General, UF Health Jacksonville, UF Health Shands, with Ascension Sacred Heart Pensacola provisional. Lakeland Regional became Level I in June 2026. [reported] **The full current list needs to be hand-built from the state's trauma system page.**
- Florida's stroke center designations are Acute Stroke Ready, Primary and Comprehensive. We could not retrieve a current inventory. [verify]

## 5. Police and public safety

- **Drone first responder (DFR) is the real air response today:**
  - **Orlando:** approved $6.83M for 11 drones at 9 rooftop docks, targeting under 3 min. That is a goal, not a result.
  - **Jacksonville, St. Cloud and Clearwater** run pilots.
  - **Chula Vista, California** is the best benchmark: 25,000+ missions, drone arrived first on 17,170, average **96.98 s** when first. An older release said about 21% of calls were closed without a ground unit. Another outlet reports 4 to 5 min for drones vs 6 to 9 for officers, so the definition of "response time" must be explicit. [reported]
- **Manned electric aircraft:** Florida Poly campus police have a single-seat Jetson ONE ("Astro"): about 20 min flight, 63 mph, $148K. It was still waiting on FAA authorization for police missions. Spain's national police are testing an EHang. A North Carolina county runs an EMS proof of concept with ultralight eVTOLs. [reported]
- **Florida law (s. 934.50):** law enforcement generally cannot use drones to collect evidence or information. Exceptions: a warrant; imminent danger or missing person; crowds of 50 or more (with written policy); a federal terrorism determination. Evidence collected in violation is inadmissible. Section numbers and wording vary across versions, so check the current text. [reported]
- **Open police data:** Orlando's portal has hosted police calls for service historically. Miami-Dade does not publish it. We found nothing for Tampa. [verify]

**What this means for us:** police mode compares three options: patrol car, drone, and air taxi (for moving people). The tool compares arrival times only. No surveillance, no crime prediction, no tactics.

## 6. Rules

- **FAA powered-lift rule** ([Federal Register](https://www.federalregister.gov/documents/2024/11/21/2024-24886/integration-of-powered-lift-pilot-certification-and-operations-miscellaneous-amendments-related-to)): published Nov 21, 2024, effective Jan 21, 2025, with a ten-year special rule (SFAR 120).
  - Aircraft that can land vertically along the whole route may use a **20-minute energy reserve**. The proposal was 45 min. [official]
  - Pilot hours for the pilot in command dropped from 50 to 35. [reported]
  - Helicopter-style visual-flight minimums may apply to aircraft that can land vertically. [reported]
- **Air ambulance weather minimums** (14 CFR 135.609): a ceiling and visibility table by day or night and local or non-local area. **The table is an image, and we could not read the values.** Look it up on the eCFR before using it. [verify]
- **Academic air taxi studies** used a 3 statute mile visibility minimum and about 20 kt (10 m/s) wind. Use these as *labeled defaults*, not as limits for any real aircraft. [reported]

## 7. Data sources we tested (from our research sandbox, 2026-11-17)

| Source | Result |
|---|---|
| Aviation Weather Center API (current airport weather and forecasts) | **Works.** JSON with wind, gust, visibility, clouds. Tested KMCO, KTPA, KMIA. |
| National Weather Service API | **Works.** Grid forecasts, hourly forecast URL, active alerts. No key. |
| Iowa Environmental Mesonet: hourly airport history | **Works.** 24 hourly rows/day for Orlando. |
| IEM: forecast (TAF) archive | **Works.** Gives the forecast baseline to beat. |
| OSRM public demo router | **Works.** Tampa to Orlando: 97 min, 135 km. Free-flow, no traffic, not for heavy use. |
| NOAA HRRR model on AWS | **Works.** One surface forecast file is about 150 MB, but the index lets you download only the needed variables with byte ranges. |
| NOAA MRMS radar and GOES-19 lightning on AWS | Reachable. |
| FAA 28-day airport data (CSV) | **Works.** 19,434 US facilities. Florida: 481 airports, 387 heliports. |
| Census API | Needs a free key. |
| OpenStreetMap Overpass | **Failed here** (connection reset). Test from your own machines. |
| FL511 live traffic, Florida crash data | Not available here. FL511 needs a key; crash data is restricted. |
| FAWN wind stations | API exists (`controller.php/today/obs/{id}`); field meanings unconfirmed. |
| FAA Wildlife Strike Database | Public download at wildlife.faa.gov; URL may have changed. |
| USGS aerial imagery service | Public domain; export parameters unconfirmed. |

Python libraries available (pip): herbie-data, xarray, cfgrib, eccodes, ortools, fastapi, duckdb, scikit-learn, lightgbm. The `eccodes` binary may need system setup. [verify]

**The big gap: real road travel times.** No free public Florida live or historical speed data. The federal probe-data set (HERE-based, 1-minute) is free to state DOTs and planning offices, and others can request it through FDOT. FDOT licenses INRIX. **Plan:** request data from FDOT now, and model road times meanwhile (labeled as modeled).

## 8. Battery, heat and wind

- No official wind or temperature limits for Joby or Archer. [verify]
- Joby flew near Dubai at up to 43 C (110 F). A commonly cited battery operating ceiling is 35 C, and Joby reportedly pre-chills the pack with coolant (secondhand). [reported]
- A simulation found seasonal range up to 22% lower than spring because of heating and cooling needs. [reported]
- A route study found slower air taxis can see flight times vary up to 40% because of wind. [reported]
- One analysis puts hover at about 581 kW, so hovering for about 16 min would drain a 160 kWh pack. Low confidence. [estimate]
- A German study found some legal visual-conditions flights cannot be done by all-electric fixed-wing air taxis while keeping the required reserve. [reported]

## 9. Prior art (what we are not first at)

- A defibrillator-drone dispatch study (Peel Region, Ontario) used machine learning to cut median response from 5.8 to 3.9 min. It covers drone vs ambulance, not helicopters.
- A preprint compares ground and helicopter travel times with gradient boosting.
- A St John New Zealand poster predicts whether an incident needs a helicopter.
- USF's Smart Urban Mobility Lab (for FDOT) has a platform for designing AAM networks. A simulator called VertiSim models wind-resilient AAM networks. A 2021 paper designs Tampa Bay vertiport networks.
- Wisk uses a "flyability matrix" of lost flight hours by city.

We could not find a tool that compares car, drone and air taxi per incident with weather reliability and cited receipts. We make no strong novelty claim.

## 10. Unresolved (check these on day 1)

1. Hackathon rules, rubric, deadline, allowed APIs. A search found no page for this event.
2. FDOT road-speed data (request pending).
3. The 135.609 weather minimums table.
4. The current trauma center list with coordinates (hand-build from floridahealth.gov).
5. Stroke center inventory (AHCA).
6. OpenStreetMap access (Overpass or a bulk download).
7. FAWN field meanings and station IDs.
8. Wildlife strike database URL.
9. USGS imagery export parameters.
10. HRRR archive depth (how far back it goes).
11. eccodes install on both machines.
12. Official range, battery and wind limits for any real aircraft (not published).

## Sources

- [Joby technology page](https://www.jobyaviation.com/technology)
- [Beta aircraft page](https://beta.team/aircraft)
- [Joby noise tests with NASA](https://ainonline.com/aviation-news/business-aviation/2022-05-10/joby-nasa-test-flights-prove-evtols-low-noise-levels)
- [Archer Midnight unveiling](https://investors.archer.com/news/news-details/2022/Archer-Unveils-its-Production-Aircraft-Midnight/default.aspx)
- [Joby, Archer pushed to 2027](https://avweb.com/aviation-news/joby-archer-initial-passenger-ops-2027/)
- [Certification tracker](https://futurewatchlog.com/evtol-certification-tracker/)
- [Joby and Beta Florida flights](https://www.ainonline.com/aviation-news/futureflight/2026-10-30/joby-and-beta-kick-florida-eipp-flights)
- [Beta 14 Florida flights](https://generalaviationnews.com/2026/11/03/beta-completes-14-electric-flights-across-florida/)
- [FAA eIPP](https://www.faa.gov/aam/eipp)
- [Archer Florida selection](https://www.businesswire.com/news/home/20260309508005/en/Archers-US-Air-Taxi-Operations-Take-Major-Step-Forward-as-Florida-New-York-and-Texas-Selected-for-White-House-Pilot-Program)
- [Metro Aviation order](https://www.flyingmag.com/air-ambulance-service-metro-aviation-orders-20-beta-electric-vtol-aircraft/)
- [FAA organ transport milestone](https://www.faa.gov/newsroom/faa-announces-major-milestone-evtol-technology-use)
- [Electra EL9](https://electra.aero/news/electra-reveals-design-for-el9-ultra-short-hybrid-electric-aircraft)
- [Florida HB 1093 analysis](https://flsenate.gov/Session/Bill/2026/1093/Analyses/h1093z1.EIS.PDF)
- [Florida AAM planning (WFSU)](https://news.wfsu.org/state-news/2026-01-18/florida-is-planning-for-the-age-of-flying-cars)
- [Swiss helicopter transfer study](https://boris.unibe.ch/162775/1/s13049-021-00981-4.pdf)
- [Montana helicopter launch times](https://www.jems.com/ems-operations/role-of-rotor-wing-helicopter-montana/)
- [Finland weather study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6373056/)
- [Time-sensitive emergencies (JEMS)](https://www.jems.com/ems-management/improving-systems-of-care-in-time-sensitive-emergencies/)
- [Organ windows (LifeSource)](https://www.life-source.org/latest/how-long-can-an-organ-be-outside-the-body-before-transplant/)
- [FAA airport data](https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/2026-10-29/)
- [Florida trauma designation](https://www.floridahealth.gov/licensing-regulations/trauma-system/trauma-center-designation/)
- [Florida Trauma 2030](https://floridacot.org/sites/default/files/Final%20-%20Florida%20Trauma%202030%20%2806.03.2026%29.pdf)
- [Orlando drone program](https://fox35orlando.com/news/orlando-approves-drone-program-speed-up-emergency-response)
- [Chula Vista milestone](https://dronexl.co/2026/05/15/chula-vista-pd-dfr-drone-program-25000/)
- [Florida Poly police Jetson ONE](https://www.wftv.com/news/local/florida-poly-unveils-flying-police-vehicle-awaits-faa-approval/UBBUG6LUFFFSLI5WLW6G5NWNUA/)
- [Florida Statute 934.50](https://florida.public.law/statutes/fla._stat._934.50)
- [FAA powered-lift final rule](https://www.federalregister.gov/documents/2024/11/21/2024-24886/integration-of-powered-lift-pilot-certification-and-operations-miscellaneous-amendments-related-to)
- [14 CFR 135.609](https://www.law.cornell.edu/cfr/text/14/135.609)
- [Seasonal range study](https://www.eurekalert.org/news-releases/1150523)
- [Joby hot-weather testing](https://aerospaceamerica.aiaa.org/uae-desert-might-pose-a-challenge-for-electric-air-taxis/)
- [Joby energy analysis](https://riskpremiumresearch.substack.com/i/168191383/segment-level-cruise)
- [Wisk weather flyability](https://aerospaceamerica.aiaa.org/wisk-assesses-flyability-of-key-markets-based-on-weather/)
- [VertiSim wind-resilient networks](https://ar5iv.labs.arxiv.org/html/2405.11118)
- [USF air taxi research](https://www.usf.edu/news/2026/usf-powering-florida-research-on-air-taxis.aspx)
- [ML dispatch of drone defibrillators](https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_proquest_miscellaneous_2494296841)
- [USGS imagery service](https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer)
- [FAA wildlife strike data](https://www.faa.gov/airports/airport_safety/wildlife)
- [FAWN data access](https://www.fawn.ifas.ufl.edu/data)
- [Prompt injection testing tools](https://www.promptfoo.dev/docs/red-team/owasp-llm-top-10/)

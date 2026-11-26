import { useEffect, useState } from "react";
import { getFacilities, placeName, type Facility } from "./api";
import CaseScreen from "./CaseScreen";
import TimeMachine from "./TimeMachine";
import EvidenceScreen from "./EvidenceScreen";

const HOSPITAL_WORDS = /HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT/i;
const TABS = [
  { id: "case", label: "New case" },
  { id: "replay", label: "Time Machine" },
  { id: "evidence", label: "Evidence" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function tabFromHash(): TabId {
  const id = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === id) ? (id as TabId) : "case";
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash);
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getFacilities()
      .then((all) => setFacilities(
        all.filter((f) => f.trauma_level || HOSPITAL_WORDS.test(f.name))
          .sort((a, b) => placeName(a).localeCompare(placeName(b)))))
      .catch((e: Error) => setError(e.message));
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="app">
      <div className="banner" role="note">
        <strong>PROTOTYPE.</strong> Not for real dispatch. Aircraft are simulated. Road times are modeled.
      </div>
      <header className="top">
        <div>
          <h1>Car or Air</h1>
          <p>Should this urgent hospital trip go by road or by air, and how sure are we?</p>
        </div>
        <nav aria-label="Screens">
          {TABS.map((t) => (
            <a key={t.id} href={`#${t.id}`} className={tab === t.id ? "tab active" : "tab"}
               aria-current={tab === t.id ? "page" : undefined}>{t.label}</a>
          ))}
        </nav>
      </header>
      {error && <p className="error" role="alert">Could not load the hospital list: {error}</p>}
      {/* Screens stay mounted so a case in progress is not lost when you look at another tab. */}
      <div hidden={tab !== "case"}><CaseScreen facilities={facilities} /></div>
      <div hidden={tab !== "replay"}><TimeMachine facilities={facilities} active={tab === "replay"} /></div>
      <div hidden={tab !== "evidence"}><EvidenceScreen active={tab === "evidence"} /></div>
    </div>
  );
}

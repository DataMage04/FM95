"""Download pinned StatsBomb open events and retain reproducible match summaries.

Run from the repository root. Raw events are cached locally, not committed.
Data attribution: StatsBomb (https://github.com/hudl/open-data).
"""
import concurrent.futures
import hashlib
import json
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
import urllib.request

REVISION = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
BASE = f"https://raw.githubusercontent.com/hudl/open-data/{REVISION}/"
CACHE = Path(".calibration-cache")


def download(path):
    dest = CACHE / path
    if dest.exists():
        raw = dest.read_bytes()
        try:
            json.loads(raw)
            return raw
        except ValueError:
            dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(BASE + path, timeout=40).read()
            json.loads(raw)
            dest.write_bytes(raw)
            return raw
        except (OSError, ValueError):
            if attempt == 3:
                raise


def summarize(meta):
    path = f"data/events/{meta['match_id']}.json"
    raw = download(path)
    events = [e for e in json.loads(raw) if e["period"] in (1, 2)]
    counts = dict.fromkeys(("goals", "shots", "shots_on_target", "passes_attempted",
                           "passes_completed", "fouls_committed", "yellow_cards",
                           "red_cards", "corners_taken", "penalties_taken",
                           "penalties_scored", "woodwork_contacts", "shots_blocked"), 0)
    counts["goals"] = meta["home_score"] + meta["away_score"]
    for e in events:
        kind = e["type"]["name"]
        if kind == "Pass":
            # FM95 has separate cross counters; compare ordinary passes only.
            if not e["pass"].get("cross", False):
                counts["passes_attempted"] += 1
                counts["passes_completed"] += "outcome" not in e["pass"]
            counts["corners_taken"] += e["pass"].get("type", {}).get("name") == "Corner"
        if kind == "Shot":
            shot = e["shot"]
            outcome = shot["outcome"]["name"]
            counts["shots"] += 1
            counts["shots_on_target"] += outcome in ("Goal", "Saved", "Saved to Post")
            counts["woodwork_contacts"] += outcome in ("Post", "Saved to Post")
            counts["shots_blocked"] += outcome == "Blocked"
            counts["corners_taken"] += shot.get("type", {}).get("name") == "Corner"
            if shot.get("type", {}).get("name") == "Penalty":
                counts["penalties_taken"] += 1
                counts["penalties_scored"] += outcome == "Goal"
        if kind == "Foul Committed":
            counts["fouls_committed"] += 1
        for field in ("foul_committed", "bad_behaviour"):
            card = e.get(field, {}).get("card", {}).get("name")
            counts["yellow_cards"] += card in ("Yellow Card", "Second Yellow")
            counts["red_cards"] += card in ("Red Card", "Second Yellow")
    return {"match_id": meta["match_id"], "date": meta["match_date"],
            "event_sha256": hashlib.sha256(raw).hexdigest(), "totals": counts}


def main():
    matches = json.loads(download("data/matches/2/27.json"))
    matches.sort(key=lambda m: (m["match_date"], m["kick_off"], m["match_id"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        rows = []
        for i, result in enumerate(pool.map(summarize, matches), 1):
            rows.append(result)
            if i % 25 == 0:
                print(f"Summarized {i}/{len(matches)} matches", flush=True)
    result = {"source": "StatsBomb Open Data", "repository": "https://github.com/hudl/open-data",
              "revision": REVISION, "competition": "Premier League", "season": "2015/2016",
              "split": "First 280 matches train; final 100 matches holdout, ordered date/kickoff/id",
              "matches": rows}
    (CACHE / "summaries.json").write_text(json.dumps(result, indent=2) + "\n")
    groups = {}
    for name, group in (("train", rows[:280]), ("holdout", rows[280:])):
        metrics = {}
        for key in group[0]["totals"]:
            values = [r["totals"][key] for r in group]
            average = mean(values)
            se = stdev(values)/sqrt(len(values))
            metrics[key] = {"mean": average, "se": se,
                            "ci95": [max(0, average-1.96*se), average+1.96*se]}
        metrics["pass_completion"] = sum(r["totals"]["passes_completed"] for r in group)/sum(r["totals"]["passes_attempted"] for r in group)
        groups[name] = {"matches": len(group), "start": group[0]["date"], "end": group[-1]["date"], "metrics": metrics}
    result.pop("matches")
    result["groups"] = groups
    result["manifest"] = [{k: r[k] for k in ("match_id", "date", "event_sha256")} for r in rows]
    Path("data/calibration/targets.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

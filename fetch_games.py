#!/usr/bin/env python3
"""
fetch_games.py — pulls today's active games for several sports from
Polymarket's public Gamma API and writes one combined games.json.

Meant to be run on a schedule (see .github/workflows/update.yml) so the
output file always reflects the current day's listed games.

Requires: pip install requests
"""

import json
import sys
from datetime import datetime, timezone
import requests

GAMMA_BASE = "https://gamma-api.polymarket.com"

# Sports to pull each run. Edit this list to add/remove sports.
SPORTS_TO_FETCH = ["baseball", "football", "basketball", "hockey", "soccer", "esports"]

# Polymarket's /sports endpoint returns individual LEAGUES, not broad sport
# categories, each tagged with a short internal "sport" code (e.g. "mlb",
# "nfl", "bkseria", "mlbb"). Matching on league NAME substrings is unreliable
# because e.g. British soccer leagues are literally called "Football League",
# which false-matches the word "football". So: for single-league US sports we
# match the exact code; for categories that span many leagues (soccer,
# esports) we aggregate every matching league instead of taking the first hit.

# Exact "sport" code match, single league expected.
EXACT_CODE = {
    "baseball": "mlb",
    "football": "nfl",
    "basketball": "nba",
    "hockey": "nhl",
}

# Categories that span many leagues: match by exact code OR name keyword,
# and aggregate ALL matches (not just the first).
MULTI_LEAGUE = {
    "soccer": {
        "codes": {"epl", "laliga", "seriea", "bundesliga", "ligue1", "mls", "ucl", "uefa"},
        "keywords": ["premier league", "la liga", "serie a", "bundesliga", "ligue 1", "champions league", "world cup", " mls"],
    },
    "esports": {
        "codes": {"mlbb", "lol", "csgo", "cs2", "valorant", "dota", "dota2", "ow", "ow2", "r6", "cod", "rl"},
        "keywords": ["esports", "league of legends", "mobile legends", "counter-strike", "dota", "valorant", "overwatch", "call of duty", "rocket league"],
    },
}


def find_matches(sport_key, sports_meta):
    """Returns a list of (tag_id, league_name) tuples for this sport category."""
    key = sport_key.lower()
    matches = []

    if key in EXACT_CODE:
        target_code = EXACT_CODE[key]
        for entry in sports_meta:
            code = str(entry.get("sport", "")).lower()
            name = str(entry.get("name", "")).lower()
            if code == target_code or name == target_code:
                tag_id = entry.get("primaryTagId")
                if tag_id is None:
                    tags_str = str(entry.get("tags", ""))
                    tag_id = tags_str.split(",")[0] if tags_str else entry.get("id")
                if tag_id is not None:
                    matches.append((tag_id, entry.get("name", key)))
                break  # single league expected, first exact hit is enough
        return matches

    if key in MULTI_LEAGUE:
        codes = MULTI_LEAGUE[key]["codes"]
        keywords = MULTI_LEAGUE[key]["keywords"]
        for entry in sports_meta:
            code = str(entry.get("sport", "")).lower()
            name = str(entry.get("name", "")).lower()
            if code in codes or any(kw in name for kw in keywords):
                tag_id = entry.get("primaryTagId")
                if tag_id is None:
                    tags_str = str(entry.get("tags", ""))
                    tag_id = tags_str.split(",")[0] if tags_str else entry.get("id")
                if tag_id is not None:
                    matches.append((tag_id, entry.get("name", key)))
        return matches

    # Fallback for anything not explicitly configured above.
    for entry in sports_meta:
        name = str(entry.get("name", "")).lower()
        if key in name:
            tag_id = entry.get("primaryTagId") or entry.get("id")
            if tag_id is not None:
                matches.append((tag_id, entry.get("name", key)))
    return matches


def fetch_events(tag_id, limit=50):
    params = {"tag_id": tag_id, "active": "true", "closed": "false", "limit": limit}
    resp = requests.get(f"{GAMMA_BASE}/events", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def main():
    resp = requests.get(f"{GAMMA_BASE}/sports", timeout=20)
    resp.raise_for_status()
    sports_meta = resp.json()

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sports": {},
    }

    for sport in SPORTS_TO_FETCH:
        matches = find_matches(sport, sports_meta)
        if not matches:
            print(f"warning: no league matched for '{sport}', skipping", file=sys.stderr)
            output["sports"][sport] = []
            continue

        seen_ids = set()
        combined = []
        league_names = []
        for tag_id, league_name in matches:
            league_names.append(league_name)
            try:
                events = fetch_events(tag_id)
            except requests.RequestException as e:
                print(f"warning: fetch failed for '{sport}' league '{league_name}' (tag {tag_id}): {e}", file=sys.stderr)
                continue
            for ev in events:
                eid = ev.get("id")
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    combined.append(ev)

        output["sports"][sport] = combined
        print(f"{sport}: {len(combined)} active event(s) across {len(matches)} league(s) [{', '.join(league_names)}]")

    with open("games.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nwrote games.json")


if __name__ == "__main__":
    main()

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

SPORT_ALIASES = {
    "baseball": ["mlb", "baseball"],
    "football": ["nfl", "football"],
    "basketball": ["nba", "basketball"],
    "hockey": ["nhl", "hockey"],
    "soccer": ["soccer", "premier league", "champions league", "mls", "uefa"],
    "esports": ["esports", "league of legends", "csgo", "cs2", "valorant", "dota"],
}


def find_tag_id(sport_key, sports_meta):
    aliases = SPORT_ALIASES.get(sport_key.lower(), [sport_key.lower()])
    for entry in sports_meta:
        label = str(entry.get("label", "") or entry.get("name", "")).lower()
        if any(alias in label for alias in aliases):
            tag_id = entry.get("tagId") or entry.get("tag_id") or entry.get("id")
            if tag_id is not None:
                return tag_id
    return None


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
        tag_id = find_tag_id(sport, sports_meta)
        if tag_id is None:
            print(f"warning: no tag found for '{sport}', skipping", file=sys.stderr)
            output["sports"][sport] = []
            continue
        try:
            events = fetch_events(tag_id)
            output["sports"][sport] = events
            print(f"{sport}: {len(events)} active event(s)")
        except requests.RequestException as e:
            print(f"warning: fetch failed for '{sport}': {e}", file=sys.stderr)
            output["sports"][sport] = []

    with open("games.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nwrote games.json")


if __name__ == "__main__":
    main()

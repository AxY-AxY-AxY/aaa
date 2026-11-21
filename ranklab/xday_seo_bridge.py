#!/usr/bin/env python3
"""Read-only RankLab SEO topic input for the existing XDAY production Coordinator.

This module NEVER creates upload jobs, runs a worker, or modifies any delivery ledger.
Use it inside the existing topic/metadata selection step only.
"""
from __future__ import annotations
from datetime import datetime, timezone
import argparse
import json
import re
import sys
import urllib.request
from typing import Any, Iterable

FEED_URL = "https://raw.githubusercontent.com/AxY-AxY-AxY/aaa/main/ranklab/seo-feed.json"
SCHEMA = "xday.ranklab.seo-feed.v1"
MAX_BYTES = 2_000_000
MAX_AGE_HOURS = 72
PRIORITIES = {"this_week": 0, "build_long_term": 1}

def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().casefold()

def validate_and_select(
    doc: dict[str, Any], *,
    market: str | None = None,
    product: str | None = None,
    existing_topics: Iterable[str] = (),
    limit: int = 6,
    now: datetime | None = None,
    max_age_hours: int = MAX_AGE_HOURS,
) -> list[dict[str, Any]]:
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("Unexpected RankLab feed schema")
    if doc.get("mode") != "metadata_suggestions_only":
        raise ValueError("RankLab feed cannot control the posting queue")
    raw_date = doc.get("generated_at")
    if not isinstance(raw_date, str):
        raise ValueError("Missing source timestamp")
    date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Source timestamp is missing timezone")
    if now is None:
        now = datetime.now(timezone.utc)
    age_hours = (now - date).total_seconds() / 3600
    if age_hours < -0.5 or age_hours > max_age_hours:
        raise ValueError(f"Stale or future SEO feed: {age_hours:.1f}h")
    actions = doc.get("actions")
    if not isinstance(actions, list) or len(actions) > 500:
        raise ValueError("Invalid SEO recommendations")
    seen = {normalized(x) for x in existing_topics}
    result = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        keyword = action.get("keyword")
        region = action.get("market")
        if not isinstance(keyword, str) or not (1 <= len(keyword) <= 150):
            continue
        if region not in {"JP", "US", "KR"}:
            continue
        if action.get("priority") not in PRIORITIES:
            continue
        if market and region != market:
            continue
        if product and product != "all" and action.get("product") != product:
            continue
        key = normalized(keyword)
        if key in seen:
            continue
        seen.add(key)
        ev = action.get("evidence") or {}
        if not isinstance(ev, dict) or ev.get("autocomplete_confirmed") is not True:
            continue
        trials, hits = ev.get("suggestion_probes"), ev.get("suggestion_hits")
        count = ev.get("competitor_sample")
        if (not isinstance(trials, int) or trials < 1 or
            not isinstance(hits, int) or hits < 1 or
            not isinstance(count, int) or count < 5 or
            not isinstance(ev.get("competitor_strength"), (int, float))):
            continue
        result.append({
            "id": str(action.get("id", ""))[:80],
            "keyword": keyword,
            "market": region,
            "product": str(action.get("product", ""))[:40],
            "intent": str(action.get("intent", ""))[:40],
            "proposed_title": str(action.get("proposed_title", ""))[:190],
            "priority": action["priority"],
            "priority_proxy": action.get("opportunity_score_proxy"),
            "evidence": ev,
            "source": "RankLab SEO metadata proposal; not approved or scheduled",
        })
    result.sort(key=lambda x: (
        PRIORITIES[x["priority"]], -(x["priority_proxy"] or 0),
        x["market"], normalized(x["keyword"])
    ))
    return result[:max(0, min(limit, 50))]

def get_recommendations(*, url: str = FEED_URL, **filters: Any) -> list[dict[str, Any]]:
    if not url.startswith("https://raw.githubusercontent.com/AxY-AxY-AxY/aaa/main/ranklab/"):
        raise ValueError("Only the approved read-only RankLab feed is accepted")
    req = urllib.request.Request(url, headers={
        "User-Agent": "XDAY-RankLab-SEO-Bridge/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=8) as res:
        payload = res.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("SEO feed exceeds byte limit")
    return validate_and_select(json.loads(payload.decode("utf-8")), **filters)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--market", choices=["JP", "US", "KR"])
    p.add_argument("--product")
    p.add_argument("--limit", type=int, default=6)
    p.add_argument("--input-json", help="Read a local fixture instead of fetching")
    p.add_argument("--existing-titles-json", help="JSON array of topics already queued or published")
    a = p.parse_args()
    previous = []
    if a.existing_titles_json:
        with open(a.existing_titles_json, "r", encoding="utf-8") as f:
            previous = json.load(f)
        if not isinstance(previous, list):
            raise SystemExit("Existing titles must be a JSON list")
    filters = dict(market=a.market, product=a.product, limit=a.limit, existing_topics=previous)
    try:
        if a.input_json:
            with open(a.input_json, "r", encoding="utf-8") as f:
                recs = validate_and_select(json.load(f), **filters)
        else:
            recs = get_recommendations(**filters)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"RankLab SEO unavailable: {exc}", file=sys.stderr)
        print("[]")
        return
    print(json.dumps(recs, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

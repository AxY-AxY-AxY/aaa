#!/usr/bin/env python3
"""Read-only RankLab keywords for SEO metadata of EXISTING XDAY videos.

Not a topic planner. Does not write metadata, upload videos, or change posting queues.
Pass the CURRENT video's product and market explicitly; unrelated keywords are excluded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import re
import sys
from typing import Any, Iterable
import urllib.request

FEED_URL = "https://raw.githubusercontent.com/AxY-AxY-AxY/aaa/main/ranklab/seo-feed.json"
SCHEMA = "xday.ranklab.keyword-feed.v1"
MAX_BYTES = 2_000_000
MAX_AGE_HOURS = 72
PRODUCTS = {"VALORANT", "Fortnite", "APEX", "Spoofer", "Colorbot"}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().casefold())

def select_keywords(
    feed: dict[str, Any],
    *,
    market: str | None = None,
    product: str | None = None,
    exclude_keywords: Iterable[str] = (),
    limit: int = 8,
    verified_only: bool = True,
    now: datetime | None = None,
    max_age_hours: int = MAX_AGE_HOURS,
) -> list[str]:
    """Read keyword terms only. Never infer or overwrite a video's theme."""
    if not isinstance(feed, dict) or feed.get("schema") != SCHEMA or feed.get("mode") != "keywords_only":
        raise ValueError("Invalid RankLab keyword feed version or mode")
    rules=feed.get("constraints") or {}
    if any(rules.get(k) is not False for k in ("theme_selection","video_generation","posting","schedule_changes")):
        raise ValueError("Feed must have no production permissions")
    stamp=feed.get("generated_at")
    if not isinstance(stamp,str):
        raise ValueError("Missing feed timestamp")
    generated=datetime.fromisoformat(stamp.replace("Z","+00:00"))
    if generated.tzinfo is None:
        raise ValueError("Feed timestamp must include timezone")
    now=now or datetime.now(timezone.utc)
    hours=(now-generated).total_seconds()/3600
    if not (-0.5 <= hours <= max_age_hours):
        raise ValueError("SEO feed is outdated")
    if market is not None and market not in ("JP","US","KR"):
        raise ValueError("Invalid language/market")
    if product is not None and product not in PRODUCTS:
        raise ValueError("Unsupported product")
    rows=feed.get("keywords")
    if not isinstance(rows,list) or len(rows)>1000:
        raise ValueError("Invalid keyword list")
    seen={norm(word) for word in exclude_keywords}
    result=[]
    for row in rows:
        if not isinstance(row,dict): continue
        kw=row.get("keyword")
        if not isinstance(kw,str) or not 1<=len(kw.strip())<=150: continue
        if row.get("market") not in ("JP","US","KR"): continue
        if market and row["market"]!=market: continue
        if product and row.get("product")!=product: continue
        if verified_only and row.get("status")!="verified": continue
        evidence=row.get("evidence")
        if verified_only and (
            not isinstance(evidence,dict)
            or not isinstance(evidence.get("autocomplete_hits"),int)
            or evidence["autocomplete_hits"]<1
            or not isinstance(evidence.get("competitor_sample"),int)
            or evidence["competitor_sample"]<5
            or not isinstance(evidence.get("competitor_strength"),(int,float))
            or not math.isfinite(evidence["competitor_strength"])
        ): continue
        key=norm(kw)
        if key in seen: continue
        seen.add(key)
        result.append(kw.strip())
        if len(result)>=max(0,min(50,int(limit))):break
    return result

def fetch_keywords(*,url:str=FEED_URL,**filters:Any)->list[str]:
    if url != FEED_URL:
        raise ValueError("Only the approved read-only RankLab URL can be used")
    req=urllib.request.Request(url,headers={
        "User-Agent":"XDAY-RankLab-SEO-Keywords/2.0",
        "Accept":"application/json"
    })
    with urllib.request.urlopen(req,timeout=8) as response:
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("RankLab data exceeds limit")
    return select_keywords(json.loads(raw.decode("utf-8")),**filters)

def main():
    parser=argparse.ArgumentParser(description="Keyword-only SEO feed for already-produced videos")
    parser.add_argument("--market",choices=["JP","US","KR"],required=True)
    parser.add_argument("--product",choices=sorted(PRODUCTS),required=True)
    parser.add_argument("--limit",type=int,default=8)
    parser.add_argument("--include-unverified",action="store_true",help="For manual research only")
    parser.add_argument("--input-json",help="Local keyword feed for tests")
    parser.add_argument("--exclude-keywords-json",help="JSON list of already-used keywords")
    args=parser.parse_args()
    excluded=[]
    if args.exclude_keywords_json:
        with open(args.exclude_keywords_json,"r",encoding="utf-8") as stream:
            excluded=json.load(stream)
        if not isinstance(excluded,list):raise SystemExit("exclude-keywords-json must contain a JSON list")
    filters={"market":args.market,"product":args.product,"limit":args.limit,
             "exclude_keywords":excluded,"verified_only":not args.include_unverified}
    try:
        if args.input_json:
            with open(args.input_json,"r",encoding="utf-8") as stream:
                result=select_keywords(json.load(stream),**filters)
        else:
            result=fetch_keywords(**filters)
    except (ValueError,OSError,json.JSONDecodeError) as error:
        print(f"RankLab keywords unavailable: {error}",file=sys.stderr)
        result=[]
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

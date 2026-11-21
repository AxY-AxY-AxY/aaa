#!/usr/bin/env python3
"""RankLab SEO keyword feed, not a video idea/theme/production plan."""
from __future__ import annotations
import datetime as dt
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOW = dt.datetime.now(dt.timezone.utc)

def classify(term: str) -> str:
    t = str(term).casefold()
    if any(x in t for x in ("colorbot","カラーボット","色認識","컬러봇","색상 인식")): return "Colorbot"
    if any(x in t for x in ("spoofer","hwid","スプーファー","스푸퍼")): return "Spoofer"
    if any(x in t for x in ("valorant","ヴァロラント","バロラント","발로란트")): return "VALORANT"
    if any(x in t for x in ("fortnite","フォートナイト","포트나이트")): return "Fortnite"
    if any(x in t for x in ("apex","エーペックス","에이펙스")): return "APEX"
    return "Other"

def calc(row: dict) -> dict | None:
    kw=str(row.get("keyword","")).strip()
    market=str(row.get("region",""))
    if not kw or market not in ("JP","US","KR"): return None
    suggest=row.get("suggestion") or {}
    comp=row.get("competition") or {}
    probes=max(0,int(suggest.get("checked") or 0))
    hits=max(0,int(suggest.get("hits") or 0))
    samples=max(0,int(comp.get("sample") or 0))
    strength=comp.get("strength")
    comp_ok=samples>=5 and isinstance(strength,(int,float)) and math.isfinite(float(strength))
    observed=probes>0 and hits>0
    measured=observed and comp_ok
    score=None
    if measured:
        best=max(1,min(11,int(suggest.get("bestRank") or 11)))
        suggest_proxy=min(100,48+22*hits/max(probes,1)+2*(11-best))
        score=round(.55*suggest_proxy+.45*(100-float(strength)))
    return {
        "keyword":kw,
        "market":market,
        "product":classify(kw),
        "status":"verified" if measured else "investigate",
        "score_proxy":score,
        "evidence":{
          "autocomplete_hits":hits,
          "autocomplete_probes":probes,
          "autocomplete_best_rank":suggest.get("bestRank"),
          "competitor_sample":samples,
          "competitor_strength":round(float(strength),1) if comp_ok else None,
          "competitor_median_views":comp.get("medianViews") if comp_ok else None,
          "checked_at":row.get("checkedAt")
        }
    }

def build():
    source=json.loads((ROOT/"research-data.json").read_text(encoding="utf-8"))
    rows=[calc(r) for r in source.get("entries",[]) if isinstance(r,dict)]
    rows=[r for r in rows if r is not None]
    unique={}
    for r in rows:
        key=(r["market"],re.sub(r"\s+"," ",r["keyword"].casefold()))
        prev=unique.get(key)
        if prev is None or (r["score_proxy"] or -1)>(prev["score_proxy"] or -1):
            unique[key]=r
    rows=list(unique.values())
    rows.sort(key=lambda r: (
      0 if r["status"]=="verified" else 1,
      -(r["score_proxy"] or 0),
      r["evidence"]["competitor_strength"] if r["evidence"]["competitor_strength"] is not None else 101,
      r["market"],r["keyword"].casefold()
    ))
    for i,row in enumerate(rows,1): row["rank"]=i
    payload={
      "schema":"xday.ranklab.keyword-feed.v1",
      "mode":"keywords_only",
      "generated_at":NOW.isoformat(timespec="seconds"),
      "source_snapshot_at":source.get("generatedAt"),
      "purpose":"Choose relevant SEO keywords for EXISTING video content; not video topics.",
      "methodology":"Autocomplete appearances are relative evidence, not monthly search volumes. Competitor strength is derived from a small public video sample.",
      "constraints":{"theme_selection":False,"title_generation":False,"video_generation":False,"posting":False,"schedule_changes":False},
      "counts":{"all":len(rows),"verified":sum(r["status"]=="verified" for r in rows),"investigate":sum(r["status"]!="verified" for r in rows)},
      "keywords":rows
    }
    (ROOT/"seo-feed.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("RankLab SEO keyword feed:",payload["counts"])

if __name__=="__main__":build()

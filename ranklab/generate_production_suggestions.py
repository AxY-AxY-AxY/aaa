#!/usr/bin/env python3
"""Convert measured RankLab evidence into *proposal-only* production suggestions.

No absolute search volume, no upload, no delivery-ledger mutation.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NOW=dt.datetime.now(dt.timezone.utc)
def norm(s):
    return " ".join(str(s).casefold().split())
def focus(term):
    k=norm(term)
    if any(x in k for x in ("colorbot","カラーボット","色認識","컬러봇")): return "Colorbot"
    if any(x in k for x in ("spoofer","hwid","スプーファー","스푸퍼")): return "Spoofer"
    if any(x in k for x in ("valorant","ヴァロラント","발로란트")): return "VALORANT"
    if any(x in k for x in ("fortnite","フォートナイト","포트나이트")): return "Fortnite"
    if any(x in k for x in ("apex","エーペックス","에이펙스")): return "APEX"
    return "Other"
def intent(term):
    k=norm(term)
    if any(x in k for x in ("購入","販売","値段","料金","価格","buy","price","purchase","구매")): return "purchase"
    if any(x in k for x in ("比較","レビュー","おすすめ","compare","review","vs","추천")): return "comparison"
    if any(x in k for x in ("設定","導入","使い方","tutorial","setup","settings","how to")): return "setup"
    if any(x in k for x in ("ban","エラー","解除","原因","fix")): return "troubleshooting"
    return "overview"
def proposal(rec):
    kw=str(rec["keyword"]).strip();region=rec["region"]
    s=rec.get("suggestion") or {};c=rec.get("competition") or {}
    checked=int(s.get("checked") or 0);hits=int(s.get("hits") or 0)
    sample=int(c.get("sample") or 0);strength=c.get("strength")
    observed=checked>0 and hits>0;comp_ok=sample>=5 and strength is not None
    try:
        timestamp=dt.datetime.fromisoformat(str(rec["checkedAt"]).replace("Z","+00:00"))
        age=(NOW-timestamp).total_seconds()/86400
    except (ValueError,KeyError):
        age=9999
    stage="measure_first";score=None
    if observed and comp_ok and -1<=age<=21:
        stage="this_week" if float(strength)<=58 else "build_long_term"
        best=max(1,min(11,int(s.get("bestRank") or 11)))
        demand=min(100,48+22*hits/checked+2*(11-best))
        fit={"purchase":88,"comparison":82,"setup":80,"troubleshooting":85,"overview":70}[intent(kw)]
        score=round(.42*demand+.43*(100-float(strength))+.15*fit)
    suffix={"purchase":"機能と価格を整理","comparison":"比較と選び方","setup":"導入の流れ","troubleshooting":"原因と仕組みを解説","overview":"特徴・操作感を紹介"}[intent(kw)]
    return {"proposal_id":"ranklab-"+hashlib.sha256((region+"|"+norm(kw)).encode()).hexdigest()[:12],
        "stage":"proposal","priority_group":stage,"keyword":kw,"region":region,"product":focus(kw),
        "intent":intent(kw),"suggested_title":kw+"｜"+suffix,"suggested_package":{"long":1,"shorts":2},
        "target_channel_profile":None,"priority_proxy":score,
        "reason":("検索候補と競合を計測済み" if stage=="this_week" else
                  "検索候補を確認、競合強め" if stage=="build_long_term" else
                  "検索候補・競合を追加計測"),
        "evidence":{"autocomplete_confirmed":observed,"suggestion_hits":hits,"suggestion_probes":checked,
            "competitor_sample":sample,"competitor_strength":strength if comp_ok else None,
            "median_competitor_views":c.get("medianViews") if comp_ok else None,
            "checked_at":rec.get("checkedAt"),"age_days":round(age,1) if age!=9999 else None}}
def main():
    source=json.loads((ROOT/"research-data.json").read_text(encoding="utf-8"))
    records=source.get("entries",[])
    cards=[];seen=set()
    for x in records:
        if not isinstance(x,dict) or not x.get("keyword") or not x.get("region"): continue
        p=proposal(x)
        if p["proposal_id"] not in seen:cards.append(p);seen.add(p["proposal_id"])
    groups={}
    order={"this_week":0,"build_long_term":1,"measure_first":2}
    for p in cards: groups.setdefault(p["region"],[]).append(p)
    for region,rows in groups.items():
        rows.sort(key=lambda x:(order[x["priority_group"]],-(x["priority_proxy"] or -1),x["evidence"]["competitor_strength"] or 999,norm(x["keyword"])))
        for i,p in enumerate(rows,1):p["market_rank"]=i
    data={"schema":"xday.ranklab.production-proposals.v1","generated_at":NOW.isoformat(timespec="seconds"),
        "source_snapshot_at":source.get("generatedAt"),
        "note":"Autocompletion is a relative discoverability signal, NOT monthly search volume.",
        "status":"research_only_not_published",
        "handoff":{"coordinator":"tools/xday_daily_supply.py","qc":"tools/xday_daily_batch_qc.py",
            "publisher":"tools/xday_daily_publisher.py","profiles":["4","5"],"profile_assignment_required":True,
            "daily_caps":{"long":1,"shorts":2},"no_direct_delivery_ledger_writes":True},
        "counts":{name:sum(p["priority_group"]==name for p in cards) for name in order},
        "markets":{k:groups[k] for k in sorted(groups)}}
    (ROOT/"production-suggestions.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Stable, read-only metadata feed consumed by the existing XDAY Coordinator.
    # This is not a new posting queue or a publishing command.
    actions=[]
    for region,rows in sorted(groups.items()):
        for p in rows:
            if p["priority_group"] == "measure_first":
                continue
            actions.append({
                "id": p["proposal_id"], "keyword": p["keyword"], "market": region,
                "product": p["product"], "intent": p["intent"],
                "priority": p["priority_group"], "market_rank": p["market_rank"],
                "proposed_title": p["suggested_title"],
                "opportunity_score_proxy": p["priority_proxy"],
                "evidence": p["evidence"],
                "use": "SEO topic/title/description input for Coordinator only",
            })
    feed={
      "schema": "xday.ranklab.seo-feed.v1",
      "generated_at": data["generated_at"],
      "source_snapshot_at": data["source_snapshot_at"],
      "source": "Google YouTube autocomplete and public competitor video samples",
      "caveat": "Autocomplete appearances are not YouTube monthly search volumes.",
      "mode": "metadata_suggestions_only",
      "actions": sorted(actions,key=lambda p:(
          {"this_week":0,"build_long_term":1}.get(p["priority"],2),
          -(p["opportunity_score_proxy"] or 0),p["market"],p["market_rank"])),
      "control": {
          "keep_existing_coordinator": True, "keep_existing_workers": True,
          "keep_existing_daily_upload_caps": True,
          "keep_own_channel_profile_and_QC": True,
          "never_write_delivery_ledger_from_feed": True,
          "deduplicate_before_any_production": True,
          "skip_when_data_stale_or_network_fails": True
      }
    }
    (ROOT/"seo-feed.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    print("RankLab SEO feed actions:",len(feed["actions"]))
    print("RankLab production suggestions:",len(cards),data["counts"])
if __name__=="__main__":main()

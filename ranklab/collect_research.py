#!/usr/bin/env python3
"""Read-only discovery of real YouTube autocomplete and competitor video signals.
Values here are NOT monthly search volume or official YouTube search ranks.
"""
from __future__ import annotations
import concurrent.futures,datetime as dt,json,math,re,urllib.request,urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HTML=ROOT/"index.html"; OUT=ROOT/"research-data.json"
NOW=dt.datetime.now(dt.timezone.utc)
STAMP=NOW.isoformat(timespec="seconds")
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36","Accept":"application/json"}
CORE=[("JP","ヴァロラント チート"),("JP","フォートナイト チート"),("JP","APEX チート"),("JP","HWID スプーファー"),("JP","VALORANT カラーボット"),("US","valorant cheat"),("US","fortnite cheat"),("US","apex legends cheat"),("US","hwid spoofer"),("US","valorant colorbot"),("KR","발로란트 치트"),("KR","포트나이트 핵")]

def norm(s):
    return " ".join(str(s).casefold().split())

def request_json(url, timeout=12):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        if resp.status != 200: raise RuntimeError("HTTP "+str(resp.status))
        return json.loads(resp.read(500000).decode("utf-8","replace"))

def suggest(q,region):
    lang={"JP":"ja","US":"en","KR":"ko"}[region]
    args={"client":"firefox","ds":"yt","hl":lang,"gl":region,"q":q}
    data=request_json("https://suggestqueries.google.com/complete/search?"+urllib.parse.urlencode(args))
    if not isinstance(data,list) or len(data)<2 or not isinstance(data[1],list): raise RuntimeError("no results")
    return [str(v[0] if isinstance(v,list) else v).strip() for v in data[1] if v]

def search(q,region):
    params=urllib.parse.urlencode({"q":q,"type":"video","region":region})
    errors=[]
    for base in ["https://yt.chocolatemoo53.com","https://invidious.nerdvpn.de"]:
        try:
            data=request_json(base+"/api/v1/search?"+params,11)
            if not isinstance(data,list):raise RuntimeError("invalid response")
            videos=[v for v in data if isinstance(v,dict) and v.get("type")=="video" and re.fullmatch(r"[A-Za-z0-9_-]{11}",str(v.get("videoId","")))][:20]
            if videos:return videos,base.split("//")[-1]
        except Exception as e: errors.append(type(e).__name__)
    raise RuntimeError("search services unavailable: "+"/".join(errors))

def region_of(seed):
    return {"jp":"JP","kr":"KR"}.get(seed.get("lang"),"US")

def focus_of(seed):
    k=norm(seed["keyword"])
    if any(s in k for s in ["colorbot","カラーボット","色認識","컬러봇"]):return "Colorbot"
    if any(s in k for s in ["spoofer","hwid","スプーファー","스푸퍼"]):return "Spoofer"
    return seed.get("focus") or seed.get("game") or "Other"

def choose():
    text=HTML.read_text(encoding="utf-8")
    match=re.search(r"const SEEDS=(\[.*?\]);",text,re.S)
    if not match:raise RuntimeError("Cannot read embedded keyword seeds")
    seeds=json.loads(match.group(1))
    buckets={}
    for seed in seeds:
        k=str(seed.get("keyword","")).strip()
        if k: buckets.setdefault((focus_of(seed),region_of(seed)),[]).append((region_of(seed),k))
    candidates=list(CORE)
    day=NOW.timetuple().tm_yday
    # Broad and long-tail terms are sampled across every product and market;
    # editorial sales-intent scores are not used to fabricate search demand.
    for round_number in range(10):
        for key in sorted(buckets):
            group=buckets[key]
            if group:
                candidates.append(group[(day*3+round_number*7)%len(group)])
    seen=set(); chosen=[]
    for region,k in candidates:
        identity=(region,norm(k))
        if identity not in seen and len(chosen)<52:
            chosen.append((region,k));seen.add(identity)
    return chosen

def checks(k):
    terms=k.strip().split();result=[]
    if len(terms)>1: result.append(" ".join(terms[:-1]))
    if len(k)>5:result.append(k[:-2])
    if not result:result.append(k[:-1])
    return list(dict.fromkeys(x for x in result if len(x)>=3))[:2]

def competitor_stat(videos,k,provider):
    top=[v for v in videos[:10] if isinstance(v.get("viewCount"),(int,float)) and v["viewCount"]>=0]
    if len(top)<5:return {"sample":len(top),"strength":None,"medianViews":None,"source":provider}
    med=sorted(int(v["viewCount"]) for v in top)[len(top)//2]
    tokens=[x for x in norm(k).split() if len(x)>=2]
    exact=sum(bool(tokens) and all(t in norm(v.get("title","")) for t in tokens) for v in top)/len(top)
    recent=sum(isinstance(v.get("published"),(int,float)) and 0<=NOW.timestamp()-v["published"]<=180*86400 for v in top)/len(top)
    unique=len(set(norm(v.get("author","")) for v in top))
    strength=round(max(0,min(100,9*math.log10(med+1)+24*exact+11*recent+min(12,unique*1.2))))
    return {"sample":len(top),"strength":strength,"medianViews":med,"exactRate":round(exact,3),"recentRate":round(recent,3),"uniqueChannels":unique,"source":provider}

def collect(item):
    region,k=item;checked=0;hits=0;best=None;related=0;errors=[]
    prefixes=checks(k)
    for prefix in prefixes:
        try:
            phrases=suggest(prefix,region);checked+=1;related+=len(phrases)
            positions=[i+1 for i,p in enumerate(phrases) if norm(p)==norm(k)]
            if positions:
                hits+=1;rank=min(positions);best=rank if best is None else min(best,rank)
        except Exception as e:errors.append("suggest:"+type(e).__name__)
    comp={"sample":0,"strength":None,"medianViews":None,"source":"Invidious"}
    try:
        videos,provider=search(k,region);comp=competitor_stat(videos,k,provider)
    except Exception as e:errors.append("search:"+type(e).__name__)
    return {"keyword":k,"region":region,"checkedAt":STAMP,
            "suggestion":{"checked":checked,"hits":hits,"bestRank":best,"relatedCount":related,"source":"Google YouTube Search autocomplete","prefixes":prefixes},
            "competition":comp,"errors":errors}

def main():
    old={}
    if OUT.exists():
        try:
            for e in json.loads(OUT.read_text(encoding="utf-8")).get("entries",[]):
                old[(e["region"],norm(e["keyword"]))]=e
        except Exception as e:print("Existing cache unreadable:",e,flush=True)
    queue=choose()
    print("Monitoring",len(queue),"keywords",flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        pending=[pool.submit(collect,x) for x in queue]
        for i,f in enumerate(concurrent.futures.as_completed(pending),1):
            e=f.result()
            key=(e["region"],norm(e["keyword"]))
            prev=old.get(key)
            if prev:
                if e["suggestion"]["checked"]==0 and prev.get("suggestion",{}).get("checked",0)>0:e["suggestion"]=prev["suggestion"]
                if e["competition"]["sample"]<5 and prev.get("competition",{}).get("sample",0)>=5:e["competition"]=prev["competition"]
                if e["suggestion"]["checked"]==0 or e["competition"]["sample"]<5:e["checkedAt"]=prev.get("checkedAt",STAMP)
            old[key]=e
            print(str(i)+"/"+str(len(queue)),e["region"],e["keyword"],"suggest",e["suggestion"]["hits"],"/",e["suggestion"]["checked"],"competition",e["competition"]["sample"],flush=True)
    data=[]
    for e in old.values():
        try:
            d=dt.datetime.fromisoformat(e["checkedAt"])
            if (NOW-d).days>12:continue
        except Exception:continue
        data.append(e)
    data.sort(key=lambda e:(e["region"],norm(e["keyword"])))
    complete=sum(e["suggestion"]["checked"]>0 and e["competition"]["sample"]>=5 for e in data)
    print("Finished",len(data),"pairs",complete,"measured",flush=True)
    if complete==0:raise RuntimeError("No complete measurements, retain previous data")
    result={"schema":"ranklab-research-v1","generatedAt":STAMP,
            "method":"Autocomplete positions and Invidious top-10 video views. Not official search volume or rank.",
            "entries":data,"coverage":{"pairs":len(data),"complete":complete}}
    OUT.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Snapshot bytes",OUT.stat().st_size,flush=True)

if __name__=="__main__":
    main()

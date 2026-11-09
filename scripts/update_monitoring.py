#!/usr/bin/env python3
"""Public legal-news index. Discovery only; no legal conclusions."""
import json, os, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT=Path("data/monitoring.json")
QUERIES={
 "Prawo budowlane": 'site:gov.pl/web/gunb OR site:gov.pl/web/rozwoj-technologia "prawo budowlane"',
 "Umowy o roboty": 'site:sn.pl "roboty budowlane" OR site:gov.pl "umowa o roboty budowlane"',
 "Prawo deweloperskie": 'site:uokik.gov.pl deweloper OR site:gov.pl "ustawa deweloperska"',
 "Wspólnoty mieszkaniowe": 'site:gov.pl "wspólnoty mieszkaniowe" OR site:sn.pl "wspólnota mieszkaniowa"',
}
def load():
 try:
  obj=json.loads(OUT.read_text(encoding="utf-8"))
  return obj.get("items",[]) if isinstance(obj.get("items"),list) else []
 except (OSError,ValueError):return []
def fetch(q):
 url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":"pl","gl":"PL","ceid":"PL:pl"})
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 LegalMonitor/1.0"})
 with urllib.request.urlopen(req,timeout=25) as res: return ET.fromstring(res.read(2_000_000))
def main():
 cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).date().isoformat()\n existing=load(); by_id={x["id"]:x for x in existing if isinstance(x,dict) and x.get("id") and x.get("date","")>=cutoff}
 successes=0
 for area,q in QUERIES.items():
  try:
   root=fetch(q);successes+=1
   for item in root.findall("./channel/item")[:30]:
    title=(item.findtext("title") or "").strip()
    link=(item.findtext("link") or "").strip()
    if not title or not link.startswith("https://"):continue\n    low=title.lower()\n    relevant=any(t in low for t in ("budowlan","budow","deweloper","wspólnot","wspolnot","roboty budowlane","nieruchomo","pozwolen","wykonawc","inwestycj","orzeczen","wyrok","uchwał","uchwal","ustaw","rozporządzen","rozporzadzen","nadzór budowlany","nadzor budowlany"))\n    if not relevant:continue
    rawdate=item.findtext("pubDate") or ""
    try: date=parsedate_to_datetime(rawdate).date().isoformat()
    except (ValueError,TypeError):date=""\n    if not date or date<cutoff:continue
    import hashlib
    ident=hashlib.sha256((area+"|"+link).encode()).hexdigest()[:24]
    if ident not in by_id:
     by_id[ident]={"id":ident,"title":title[:300],"area":area,"type":"Wiadomość do weryfikacji","date":date,"effective":"","priority":"Nieoceniona","status":"Do weryfikacji","source":link,"impact":"","action":"Otwórz źródło pierwotne i zweryfikuj treść, datę oraz znaczenie prawne.","discovery":"Google News RSS (indeks źródeł; link może prowadzić przez agregator)"}
  except Exception as exc: print(f"ERROR {area}: {exc}")
 if not successes:
  raise SystemExit("No sources accessible; leaving existing data unchanged")
 ordered=sorted(by_id.values(),key=lambda x:x.get("date",""),reverse=True)[:500]
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),"notice":"Automatyczny indeks wiadomości. Nie jest analizą prawną ani zweryfikowanym wykazem zmian.","items":ordered},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(f"Saved {len(ordered)} entries; {successes}/{len(QUERIES)} feeds accessible")
if __name__=="__main__":main()

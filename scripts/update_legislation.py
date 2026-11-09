#!/usr/bin/env python3
"""Discover legislative publications; never infer legal force from search snippets."""
import hashlib,json,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT=Path("data/legislation.json")
SEARCHES={
 "Prawo budowlane": ['site:gov.pl "prawo budowlane" nowelizacja','site:legislacja.rcl.gov.pl "prawo budowlane"','site:eli.gov.pl "prawo budowlane"'],
 "Prawo deweloperskie": ['site:gov.pl "ustawa deweloperska" zmiany','site:legislacja.rcl.gov.pl deweloperska','site:eli.gov.pl deweloper'],
 "Wspólnoty mieszkaniowe": ['site:gov.pl "własności lokali" nowelizacja','site:legislacja.rcl.gov.pl "własności lokali"','site:eli.gov.pl "własności lokali"'],
 "Umowy o roboty": ['site:gov.pl "zamówienia publiczne" nowelizacja roboty','site:legislacja.rcl.gov.pl "roboty budowlane"','site:eli.gov.pl "zamówień publicznych"'],
}
def get(url):
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (public legal research index)"})
 with urllib.request.urlopen(req,timeout=15) as r:return r.read(1200000)
def main():
 today=datetime.now(timezone.utc).date()
 cutoff=(today-timedelta(days=30)).isoformat()
 existing={}
 try:
  data=json.loads(OUT.read_text(encoding="utf-8"))
  existing={x["id"]:x for x in data.get("items",[]) if cutoff<=x.get("published","")<=today.isoformat()}
 except (OSError,ValueError,KeyError,TypeError):pass
 ok=0
 for area,queries in SEARCHES.items():
  for q in queries:
   url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q+" when:30d","hl":"pl","gl":"PL","ceid":"PL:pl"})
   try:
    root=ET.fromstring(get(url));ok+=1
    for item in root.findall("./channel/item")[:25]:
     title=(item.findtext("title") or "").strip()
     link=(item.findtext("link") or "").strip()
     if not title or not link.startswith("https://"):continue
     try:published=parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
     except (ValueError,TypeError):continue
     if not cutoff<=published<=today.isoformat():continue
     if not any(k in title.lower() for k in ("ustaw","rozporządzen","rozporzadzen","projekt","nowelizac","zmian","przepis","prawo budowlan","deweloper","własności lokali","zamówień publicznych")):continue
     ident=hashlib.sha256((area+"|"+link).encode()).hexdigest()[:24]
     existing[ident]={"id":ident,"title":title[:300],"area":area,"published":published,
      "discovery_url":link,"stage":"Nieustalony — wymaga sprawdzenia dokumentu",
      "effective_date":None,"official_document_url":None,
      "verification":"Wynik wyszukiwania; niezweryfikowany akt lub projekt",
      "action":"Ustal numer aktu lub projektu, etap procedury, tekst źródłowy i datę wejścia w życie."}
   except Exception as e:print("Feed unavailable:",area,str(e)[:140])
 if not ok:raise SystemExit("Brak dostępnych źródeł indeksu legislacyjnego; zachowano wcześniejsze dane")
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),
 "notice":"Indeks potencjalnych zmian legislacyjnych, nie rejestr zweryfikowanych aktów. Status i daty wymagają sprawdzenia w RCL, Sejmie lub ELI/Dz.U.",
 "items":sorted(existing.values(),key=lambda x:x["published"],reverse=True)[:150]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Legislation discovery:",len(existing),"items from",ok,"feeds")
if __name__=="__main__":main()

#!/usr/bin/env python3
"""Discover legislative publications; never infer legal force from search snippets."""
import hashlib,json,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT=Path("data/legislation.json")
SEARCHES={
 "Prawo budowlane": ['"prawo budowlane" (ustawa OR projekt OR nowelizacja OR rozporządzenie)','"warunki techniczne" (projekt OR rozporządzenie OR zmiany)','"nadzór budowlany" (ustawa OR projekt OR zmiany)'],
 "Nieruchomości": ['"gospodarka nieruchomościami" (ustawa OR projekt OR nowelizacja)','"własność lokali" (ustawa OR projekt OR nowelizacja)','"planowanie przestrzenne" (ustawa OR projekt OR nowelizacja)','"księgi wieczyste" (ustawa OR projekt OR nowelizacja)'],
 "Prawo deweloperskie": ['deweloper (ustawa OR projekt OR nowelizacja OR rozporządzenie)','"deweloperski fundusz gwarancyjny" (ustawa OR zmiany)','"ochrona praw nabywcy" (ustawa OR nowelizacja)'],
}
TOPIC={
 "Prawo budowlane": ("prawo budowlane","prawa budowlanego","budowlanych","warunki techniczne","warunków technicznych","pozwolenie na budowę","nadzór budowlany","nadzoru budowlanego"),
 "Nieruchomości": ("nieruchomościami","nieruchomości","własności lokali","własność lokali","planowanie przestrzenne","planowaniu przestrzennym","zagospodarowaniu przestrzennym","księgi wieczyste","księgach wieczystych"),
 "Prawo deweloperskie": ("deweloper","dewelopersk","deweloperski fundusz gwarancyjny","mieszkaniowy rachunek powierniczy"),
}
LEGAL=("ustaw","rozporządzen","rozporzadzen","nowelizac","zmian","projekt","wejście w życie","wchodzi w życie","uchwalono","legislac","przepisy")
EXCLUDE=("opis przedmiotu zamówienia","zapraszamy na szkolenie","przetarg","ogłoszenie o zamówieniu","oferta pracy","szkolenie","webinar","konferencja","przetargi")
def relevant(title,area):
 t=title.lower()
 return area in TOPIC and any(k in t for k in TOPIC[area]) and any(k in t for k in LEGAL) and not any(k in t for k in EXCLUDE)

# Confirmed acts and future effective dates must remain visible beyond a 30-day news window.
CONFIRMED=[
 {"id":"confirmed-ckob-2032","title":"Przesunięcie terminu obowiązkowego przejścia na cyfrową książkę obiektu budowlanego (c-KOB)","area":"Prawo budowlane","published":"2025-12-23","stage":"Ustawa ogłoszona; zmiana obowiązuje","effective_date":"2026-01-07","deadline":"2032-01-01","official_document_url":"https://eli.gov.pl/eli/DU/2025/1847/ogl","discovery_url":"https://e-budownictwo.gunb.gov.pl/pytania-i-odpowiedzi/","verification":"Potwierdzone: Dz.U. 2025 poz. 1847 oraz wyjaśnienia GUNB","action":"Weryfikuj, które istniejące książki papierowe można prowadzić do 31.12.2031; odróżnij nowe obiekty i wyjątki ustawowe."},
 {"id":"confirmed-developer-prices-2026","title":"Nowelizacja ustawy deweloperskiej — elektroniczne przekazywanie danych o cenach (art. 19b)","area":"Prawo deweloperskie","published":"2026-08-10","stage":"Ustawa ogłoszona; oczekuje na wejście w życie","effective_date":"2026-11-11","deadline":"2026-11-11","official_document_url":"https://eli.gov.pl/eli/DU/2026/1077/ogl","discovery_url":"https://ppiop.rcl.gov.pl/index.php?id_akt_prawny=306629&r=skorowidz%2Faktprawnydetail","verification":"Potwierdzone: Dz.U. 2026 poz. 1077, data wejścia w życie 11.11.2026","action":"Zweryfikuj obowiązki przekazywania danych cenowych, strukturę danych i procedury publikowania informacji."}
]

def get(url):
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (public legal research index)"})
 with urllib.request.urlopen(req,timeout=15) as r:return r.read(1200000)
def main():
 today=datetime.now(timezone.utc).date()
 cutoff=(today-timedelta(days=30)).isoformat()
 existing={}
 try:
  data=json.loads(OUT.read_text(encoding="utf-8"))
  existing={x["id"]:x for x in data.get("items",[]) if x.get("area") in SEARCHES and cutoff<=x.get("published","")<=today.isoformat() and relevant(x.get("title",""),x["area"])}
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
     if not relevant(title,area):continue
     ident=hashlib.sha256((area+"|"+link).encode()).hexdigest()[:24]
     existing[ident]={"id":ident,"title":title[:300],"area":area,"published":published,
      "discovery_url":link,"stage":"Nieustalony — wymaga sprawdzenia dokumentu",
      "effective_date":None,"official_document_url":None,
      "verification":"Wynik wyszukiwania; niezweryfikowany akt lub projekt",
      "action":"Ustal numer aktu lub projektu, etap procedury, tekst źródłowy i datę wejścia w życie."}
   except Exception as e:print("Feed unavailable:",area,str(e)[:140])
 for record in CONFIRMED:
  # Retain enacted acts with upcoming operational deadlines independently of publication date.
  if record["deadline"] >= today.isoformat():
   existing[record["id"]]=record
 if not ok and not existing:raise SystemExit("Brak dostępnych źródeł indeksu legislacyjnego; zachowano wcześniejsze dane")
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),
 "notice":"Indeks potencjalnych zmian legislacyjnych, nie rejestr zweryfikowanych aktów. Status i daty wymagają sprawdzenia w RCL, Sejmie lub ELI/Dz.U.",
 "items":sorted(existing.values(),key=lambda x:(x.get("verification","").startswith("Potwierdzone"),x.get("deadline",""),x["published"]),reverse=True)[:150]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Legislation discovery:",len(existing),"items from",ok,"feeds")
if __name__=="__main__":main()

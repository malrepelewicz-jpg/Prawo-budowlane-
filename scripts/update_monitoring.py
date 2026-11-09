#!/usr/bin/env python3
"""Weekly public-source legal monitoring; conservative, evidence-first triage."""
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("data/monitoring.json")
QUERIES = {
    "Prawo budowlane": 'site:gov.pl/web/gunb "prawo budowlane" OR "pozwolenie na budowę"',
    "Umowy o roboty": 'site:sn.pl "roboty budowlane" OR site:gov.pl "umowa o roboty budowlane"',
    "Prawo deweloperskie": 'site:uokik.gov.pl deweloper OR site:gov.pl "ustawa deweloperska"',
    "Wspólnoty mieszkaniowe": 'site:gov.pl "wspólnoty mieszkaniowe" OR site:sn.pl "wspólnota mieszkaniowa"',
}
OFFICIAL = ("gov.pl", "sn.pl", "nsa.gov.pl", "orzeczenia.nsa.gov.pl", "isap.sejm.gov.pl", "dziennikustaw.gov.pl", "uokik.gov.pl", "rcl.gov.pl")
KEYWORDS = ("budowlan", "budow", "deweloper", "wspólnot", "wspolnot", "nieruchomo", "pozwolen", "wykonawc", "inwestycj", "orzeczen", "wyrok", "uchwał", "uchwal", "ustaw", "rozporządzen", "rozporzadzen", "nadzór budowlany")
EXCLUDE = ("dzień przedsiębiorcy", "życzenia", "konkurs", "webinar", "szkolenie", "zapraszamy", "relacja z konferencji", "piknik", "nagrody", "jubileusz")

class Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer") and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def official(url):
    try:
        p = urllib.parse.urlparse(url)
        host = (p.hostname or "").lower()
        return p.scheme == "https" and any(host == d or host.endswith("." + d) for d in OFFICIAL)
    except ValueError:
        return False

def get(url, limit=700000):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (legal-monitor; public source review)"})
    with urllib.request.urlopen(req, timeout=12) as res:
        final = res.geturl()
        content_type = res.headers.get("Content-Type", "")
        body = res.read(limit)
    return final, content_type, body

def review_source(url, area):
    """Only inspect a directly accessible official HTML page; never treat Google News as primary evidence."""
    if not official(url):
        return {"verification": "Brak weryfikacji źródła pierwotnego", "source_excerpt": "", "recommendation": "Odszukaj i sprawdź oryginalny dokument na stronie organu."}
    try:
        final, content_type, body = get(url)
        if not official(final) or "html" not in content_type.lower():
            raise ValueError("Brak bezpośredniej strony HTML źródła urzędowego")
        parser = Extract()
        parser.feed(body.decode("utf-8", errors="replace"))
        content = re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
        if len(content) < 250:
            raise ValueError("Za mało tekstu do weryfikacji")
        excerpt = content[:1100]
        return {"verification": "Odczytano stronę urzędową — wymaga analizy prawnika",
                "source_excerpt": excerpt,
                "recommendation": "Sprawdź pełną treść dokumentu, jego status i daty. Oceń wpływ na " + area.lower() + "; ustal, czy potrzebna jest zmiana wzorów umów lub informacja dla klientów.",
                "primary_source": final}
    except Exception:
        return {"verification": "Nie udało się odczytać źródła pierwotnego", "source_excerpt": "", "recommendation": "Otwórz oryginalny dokument i sprawdź jego treść przed wyciągnięciem wniosków."}

def classify(title):
    t = title.lower()
    if any(s in t for s in EXCLUDE):
        return "Pozostałe"
    if any(s in t for s in ("wchodzi w życie", "weszła w życie", "wejdzie w życie", "nowelizacja", "zmiana ustawy", "wyrok sn", "wyrok nsa", "uchwała siedmiu sędziów")):
        return "Priorytet wysoki"
    if any(s in t for s in ("wyrok", "orzeczenie", "uchwała", "interpretacja", "stanowisko", "decyzja", "rozporządzenie", "projekt ustawy", "projekt rozporządzenia")):
        return "Do analizy"
    return "Pozostałe"

def load():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data.get("items"), list) else []
    except (OSError, ValueError):
        return []

def main():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    old = load()
    retention_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    by_id = {x["id"]: x for x in old if isinstance(x, dict) and x.get("id") and retention_cutoff <= x.get("date", "") <= datetime.now(timezone.utc).date().isoformat()}
    for entry in by_id.values():
        entry["selection"] = classify(entry.get("title", ""))
        entry.setdefault("verification", "Archiwalny wpis — niezweryfikowany")
        entry.setdefault("source_excerpt", "")
        entry.setdefault("recommendation", "Sprawdź oryginalne źródło i ustal konsekwencje prawne.")
    successes = 0
    for area, query in QUERIES.items():
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "pl", "gl": "PL", "ceid": "PL:pl"})
        try:
            _, _, raw = get(url)
            root = ET.fromstring(raw)
            successes += 1
            for item in root.findall("./channel/item")[:30]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if not title or not link.startswith("https://") or not any(k in title.lower() for k in KEYWORDS):
                    continue
                try:
                    date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
                except (ValueError, TypeError):
                    continue
                if date < cutoff:
                    continue
                ident = hashlib.sha256((area + "|" + link).encode()).hexdigest()[:24]
                if ident in by_id:
                    continue
                source = item.find("source")
                source_url = source.get("url", "") if source is not None else ""
                # The RSS item link is typically an aggregator redirect, not a primary source.
                evidence = review_source(source_url, area) if official(source_url) else review_source(link, area)
                by_id[ident] = {
                    "id": ident, "title": title[:300], "area": area,
                    "type": "Materiał do weryfikacji", "date": date, "effective": "",
                    "priority": "Nieoceniona", "status": "Do weryfikacji",
                    "source": link, "selection": classify(title),
                    "impact": "", "action": evidence["recommendation"],
                    "discovery": "Google News RSS", **evidence
                }
        except Exception as exc:
            print("ERROR", area, str(exc))
    if successes == 0:
        raise SystemExit("Nie udało się odczytać żadnego źródła. Zachowano stare dane.")
    ordered = sorted(by_id.values(), key=lambda x: x.get("date", ""), reverse=True)[:2000]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notice": "Automatyczna selekcja i próba odczytu źródła. Nie jest opinią prawną; materiały wymagają weryfikacji.",
        "items": ordered
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Saved", len(ordered), "entries; feeds:", successes, "/", len(QUERIES))

if __name__ == "__main__":
    main()

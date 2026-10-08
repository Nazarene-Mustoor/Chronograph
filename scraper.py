"""
ChronoGraph Production Scraper & Backfill Engine
CLI tool for ingesting on-demand articles requested via the Pit Wall Backfill Queue.
Supports direct URL scraping and automatic metadata formatting.
"""

import os
import re
import argparse
from datetime import datetime
import requests
from bs4 import BeautifulSoup

RAW_DIR = os.path.join("data", "raw_news")
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def clean_slug(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", text.lower())
    slug = re.sub(r"_+", "_", slug)[:max_len].strip("_")
    return slug

def scrape_url(url: str, custom_event: str | None = None, season: str | None = None) -> bool:
    """Scrapes an F1 article from a given URL and formats it with ChronoGraph metadata headers."""
    print(f"🌐 Fetching: {url}...")
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"❌ Failed to fetch. HTTP {res.status_code}")
            return False

        soup = BeautifulSoup(res.content, "html.parser")

        # 1. Headline Extraction
        headline_tag = soup.find("h1")
        headline = headline_tag.get_text().strip() if headline_tag else "F1 Technical Update"

        # 2. Date Extraction (fall back to today if not found)
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            pub_date = time_tag.get("datetime")[:10]
        else:
            pub_date = datetime.now().strftime("%Y-%m-%d")

        inferred_season = season or pub_date.split("-")[0]
        event_name = custom_event or "Grand Prix Investigation"

        # 3. Extract Body Paragraphs
        paragraphs = []
        for p in soup.find_all("p"):
            txt = p.get_text().strip()
            if len(txt) > 40 and not txt.startswith("Photo by") and not txt.startswith("©"):
                paragraphs.append(txt)

        if not paragraphs:
            print(f"⚠️ No substantial paragraph text found at {url}")
            return False

        # 4. Format Content with ChronoGraph Schema
        header = (
            f"PUBLICATION_DATE: {pub_date}\n"
            f"SEASON: {inferred_season}\n"
            f"EVENT: {event_name}\n"
            f"HEADLINE: {headline}\n"
            f"SOURCE_URL: {url}\n\n"
        )
        content = header + "\n\n".join(paragraphs)

        filename = f"{pub_date}_{clean_slug(headline)}.txt"
        dest_path = os.path.join(RAW_DIR, filename)

        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ Ingested into raw queue: {filename} ({len(paragraphs)} paragraphs)")
        return True

    except Exception as e:
        print(f"❌ Scraping exception: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="ChronoGraph Backfill Scraper - Ingest articles into data/raw_news/"
    )
    parser.add_argument("--url", type=str, help="Direct URL of the article to ingest")
    parser.add_argument("--event", type=str, default="Backfill Investigation", help="Associated Grand Prix or event name")
    parser.add_argument("--season", type=str, default=None, help="Championship season (e.g. 2024)")

    args = parser.parse_args()

    if args.url:
        scrape_url(args.url, custom_event=args.event, season=args.season)
        print("\n💡 Run `python ingestion_pipeline.py` to index the newly scraped article.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
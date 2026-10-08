import os
import re
from datetime import datetime
from difflib import SequenceMatcher
import feedparser
import requests
from bs4 import BeautifulSoup

# --- DIRECTORY CONFIGURATION ---
DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw_news")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed_news")
HISTORY_FILE = os.path.join(DATA_DIR, "scraped_history.txt")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

RSS_FEEDS = {
    "autosport": "https://www.autosport.com/rss/feed/f1",
    "bbc": "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
    "the_race": "https://the-race.com/feed/",
}


def slugify(text: str) -> str:
    """Converts a headline string into a clean, filesystem-safe filename."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text).strip("_")


def get_history() -> set:
    """Loads all previously scraped URLs to avoid redundant fetches."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def append_history(url: str):
    """Appends a newly scraped article URL to the history log."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def normalize_title(title: str) -> str:
    """Normalizes headline by removing non-alphanumeric chars and generic F1 filler words."""
    cleaned = title.lower()
    # Strip common filler tokens that artificially inflate similarity across different F1 stories
    fillers = [
        "formula 1",
        "formula-1",
        "f1",
        "grand prix",
        "gp",
        "reveals",
        "admits",
        "explains",
        "says",
        "claims",
    ]
    for w in fillers:
        cleaned = re.sub(rf"\b{w}\b", "", cleaned)
    return re.sub(r"[^\w\s]", "", cleaned).strip()


def is_duplicate_story(
    candidate_title: str, candidate_date: str, accepted_targets: list[dict]
) -> bool:
    """Checks if a story covering the same event has already been queued."""
    norm_cand = normalize_title(candidate_title)
    if not norm_cand:
        return False

    for target in accepted_targets:
        # Only compare stories published within the same 48h timeframe
        if target["pub_date"] == candidate_date:
            norm_target = normalize_title(target["title"])
            similarity = SequenceMatcher(
                None, norm_cand, norm_target
            ).ratio()
            # If 55%+ overlap in core headline keywords, consider it the same story
            if similarity > 0.55:
                return True
    return False


def discover_article_targets(per_source_limit: int = 5) -> list[dict]:
    """Pulls candidate F1 articles across RSS feeds with cross-source deduplication."""
    seen_urls = get_history()
    collected_by_source = {src: [] for src in RSS_FEEDS}

    # Also inspect existing files in raw_news to avoid re-scraping across script restarts
    # Check BOTH raw_news and processed_news so you never re-fetch past stories
    existing_headlines = []
    for folder in [RAW_DIR, PROCESSED_DIR]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                if fname.endswith(".txt"):
                    try:
                        with open(
                            os.path.join(folder, fname), "r", encoding="utf-8"
                        ) as f:
                            lines = [f.readline() for _ in range(3)]
                            p_date = ""
                            h_line = ""
                            for l in lines:
                                if l.startswith("PUBLICATION_DATE:"):
                                    p_date = l.split(":", 1)[1].strip()
                                elif l.startswith("HEADLINE:"):
                                    h_line = l.split(":", 1)[1].strip()
                            if h_line and p_date:
                                existing_headlines.append(
                                    {"title": h_line, "pub_date": p_date}
                                )
                    except Exception:
                        pass

    # Global pool of accepted items to prevent duplicates across different outlets
    global_accepted = list(existing_headlines)

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = entry.get("link", "").split("?")[0].strip()
                title = entry.get("title", "").strip()

                if not link or link in seen_urls:
                    continue

                # Filter out paywalled Autosport Plus articles and media hubs
                if any(
                    bad in link.lower()
                    for bad in [
                        "autosport-plus",
                        "/plus/",
                        "/video/",
                        "/podcast/",
                        "/live/",
                    ]
                ):
                    continue

                # Filter out non-F1 articles on motorsport-wide feeds
                if source_name == "the_race" and not any(
                    k in link.lower() or k in title.lower()
                    for k in ["f1", "formula-1", "grand-prix"]
                ):
                    continue

                # Extract publication date
                pub_date = datetime.now().strftime("%Y-%m-%d")
                if (
                    hasattr(entry, "published_parsed")
                    and entry.published_parsed
                ):
                    pub_date = datetime(*entry.published_parsed[:6]).strftime(
                        "%Y-%m-%d"
                    )

                # Check if this breaking story has already been accepted from another outlet
                if is_duplicate_story(title, pub_date, global_accepted):
                    continue

                item = {"url": link, "title": title, "pub_date": pub_date}
                collected_by_source[source_name].append(item)
                global_accepted.append(item)

                if len(collected_by_source[source_name]) >= per_source_limit:
                    break
        except Exception as e:
            print(f"⚠️ RSS read error ({source_name}): {e}")

    # Interleave sources in balanced round-robin order
    balanced = []
    for i in range(per_source_limit):
        for src in RSS_FEEDS:
            if i < len(collected_by_source[src]):
                balanced.append(collected_by_source[src][i])

    return balanced


def fetch_and_save_article(target: dict) -> bool:
    """Fetches full article body and writes an annotated raw text file."""
    url = target["url"]
    pub_date = target["pub_date"]

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return False

        soup = BeautifulSoup(res.content, "html.parser")

        # Fallback to headline tag if feed title is empty
        h1 = soup.find("h1")
        headline = (
            h1.get_text().strip()
            if h1
            else target["title"] or url.split("/")[-1]
        )

        # Extract article body paragraphs
        paragraphs = []
        for p in soup.find_all("p"):
            txt = p.get_text().strip()
            if (
                len(txt) > 30
                and not txt.startswith("©")
                and "cookie" not in txt.lower()
            ):
                paragraphs.append(txt)

        body_text = "\n\n".join(paragraphs)

        # Discard stubs or paywall blocks
        if len(body_text) < 400:
            return False

        full_content = (
            f"PUBLICATION_DATE: {pub_date}\n"
            f"HEADLINE: {headline}\n"
            f"SOURCE: {url}\n\n"
            f"{body_text}"
        )

        filename = f"{slugify(headline)[:60]}.txt"
        file_path = os.path.join(RAW_DIR, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        append_history(url)
        print(f"💾 Saved [{pub_date}]: {headline[:45]}...")
        return True

    except Exception as e:
        print(f"⚠️ Failed to fetch {url}: {e}")
        return False


def run_ingestion_pipeline(max_articles: int = 10):
    print("🏎️ Chronograph Web Ingestion Engine Active.")
    targets = discover_article_targets(per_source_limit=4)
    print(f"📡 Found {len(targets)} unique candidate targets across RSS feeds.")

    saved = 0
    for target in targets[:max_articles]:
        if fetch_and_save_article(target):
            saved += 1

    print(f"\n🏁 Complete! Added {saved} unique articles into '{RAW_DIR}'.")


if __name__ == "__main__":
    run_ingestion_pipeline()
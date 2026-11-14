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


def get_history() -> tuple[set, list[dict]]:
    """Loads all previously scraped URLs and headlines (supports both old URL-only and new pipe-delimited formats)."""
    seen_urls = set()
    seen_headlines = []
    if not os.path.exists(HISTORY_FILE):
        return seen_urls, seen_headlines

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            seen_urls.add(parts[0])
            if len(parts) >= 3:
                seen_headlines.append({"pub_date": parts[1], "title": parts[2]})
    return seen_urls, seen_headlines


def append_history(url: str, pub_date: str = "", title: str = ""):
    """Appends a newly scraped article URL, date, and title to the persistent history log."""
    clean_title = title.replace("|", "-").replace("\n", " ").strip()
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        if pub_date and clean_title:
            f.write(f"{url} | {pub_date} | {clean_title}\n")
        else:
            f.write(f"{url}\n")


def normalize_title(title: str) -> str:
    """Normalizes headline by removing non-alphanumeric chars and generic F1 filler words."""
    cleaned = title.lower()
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
        if target["pub_date"] == candidate_date:
            norm_target = normalize_title(target["title"])
            similarity = SequenceMatcher(None, norm_cand, norm_target).ratio()
            if similarity > 0.55:
                return True
    return False


def discover_article_targets(per_source_limit: int = 3) -> list[dict]:
    """Pulls candidate F1 articles across RSS feeds with cross-source deduplication."""
    seen_urls, existing_headlines = get_history()
    collected_by_source = {src: [] for src in RSS_FEEDS}

    for folder in [RAW_DIR, PROCESSED_DIR]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                if fname.endswith(".txt"):
                    try:
                        with open(os.path.join(folder, fname), "r", encoding="utf-8") as f:
                            lines = [f.readline() for _ in range(3)]
                            p_date, h_line = "", ""
                            for l in lines:
                                if l.startswith("PUBLICATION_DATE:"):
                                    p_date = l.split(":", 1)[1].strip()
                                elif l.startswith("HEADLINE:"):
                                    h_line = l.split(":", 1)[1].strip()
                            if h_line and p_date:
                                existing_headlines.append({"title": h_line, "pub_date": p_date})
                    except Exception:
                        pass

    global_accepted = list(existing_headlines)

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = entry.get("link", "").split("?")[0].strip()
                title = entry.get("title", "").strip()

                if not link or link in seen_urls:
                    continue

                # Filter out paywalled articles, live blogs, and non-technical fluff
                if any(
                    bad in link.lower() or bad in title.lower()
                    for bad in [
                        "autosport-plus",
                        "/plus/",
                        "/video/",
                        "/podcast/",
                        "/live/",
                        "quiz",
                        "f1 24",
                        "f1 25",
                        "watch live",
                        "start time",
                        "tv schedule",
                        "weather forecast",
                    ]
                ):
                    continue

                if source_name == "the_race" and not any(
                    k in link.lower() or k in title.lower()
                    for k in ["f1", "formula-1", "grand-prix"]
                ):
                    continue

                pub_date = datetime.now().strftime("%Y-%m-%d")
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")

                if is_duplicate_story(title, pub_date, global_accepted):
                    continue

                item = {"url": link, "title": title, "pub_date": pub_date}
                collected_by_source[source_name].append(item)
                global_accepted.append(item)

                if len(collected_by_source[source_name]) >= per_source_limit:
                    break
        except Exception as e:
            print(f"⚠️ RSS read error ({source_name}): {e}")

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
        h1 = soup.find("h1")
        headline = h1.get_text().strip() if h1 else target["title"] or url.split("/")[-1]

        paragraphs = []
        for p in soup.find_all("p"):
            txt = p.get_text().strip()
            if len(txt) > 30 and not txt.startswith("©") and "cookie" not in txt.lower():
                paragraphs.append(txt)

        body_text = "\n\n".join(paragraphs)

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

        append_history(url, pub_date, headline)
        print(f"💾 Saved [{pub_date}]: {headline[:45]}...")
        return True

    except Exception as e:
        print(f"⚠️ Failed to fetch {url}: {e}")
        return False


def run_ingestion_pipeline(max_articles: int = 6):
    print("🏎️ Chronograph Web Ingestion Engine Active.")
    targets = discover_article_targets(per_source_limit=3)
    print(f"📡 Found {len(targets)} unique candidate targets across RSS feeds.")

    saved = 0
    for target in targets[:max_articles]:
        if fetch_and_save_article(target):
            saved += 1

    print(f"\n🏁 Complete! Added {saved} unique articles into '{RAW_DIR}'.")


if __name__ == "__main__":
    run_ingestion_pipeline()
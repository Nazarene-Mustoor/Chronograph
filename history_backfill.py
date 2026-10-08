"""
ChronoGraph Historical Archive Seeder
Consolidates all foundational milestone articles across F1 regulatory eras (2018-2026).
Extracts clean editorial text, injects temporal anchor headers, and saves to data/raw_news/.
"""

import os
import re
import time
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

# 31 Curated Ground-Truth Milestones across 2018-2026
ARCHIVE_TARGETS = [
    # --- ERA 1: 2018-2020 Transition & Driver Market Catalysts ---
    {
        "url": "https://www.autosport.com/f1/news/carlos-sainz-jr-to-replace-fernando-alonso-at-mclaren-f1-team-in-2019-5301828/5301828/",
        "pub_date": "2018-08-16",
        "season": "2018",
        "event": "Driver Market",
        "headline": "Carlos Sainz Jr to replace Fernando Alonso at McLaren F1 team in 2019"
    },
    {
        "url": "https://www.autosport.com/f1/news/f1-news-sebastian-vettel-set-to-leave-ferrari-at-end-of-2020-4982686/4982686/",
        "pub_date": "2020-05-12",
        "season": "2020",
        "event": "Driver Market",
        "headline": "Sebastian Vettel set to leave Ferrari at end of 2020"
    },
    # --- ERA 2: 2021 Championship Clashes & Technical Pivot ---
    {
        "url": "https://www.autosport.com/f1/news/f1-british-gp-hamilton-wins-despite-penalty-for-verstappen-crash/6633130/",
        "pub_date": "2021-07-18",
        "season": "2021",
        "event": "British Grand Prix",
        "headline": "F1 British GP: Hamilton wins despite penalty for Verstappen crash"
    },
    {
        "url": "https://www.autosport.com/f1/news/bottas-to-leave-mercedes-and-race-for-alfa-romeo-in-f1-2022/6661413/",
        "pub_date": "2021-09-06",
        "season": "2021",
        "event": "Driver Market",
        "headline": "Valtteri Bottas to leave Mercedes and race for Alfa Romeo in F1 2022"
    },
    {
        "url": "https://www.autosport.com/f1/news/f1-abu-dhabi-gp-verstappen-defeats-hamilton-to-win-title-in-controversial-last-lap-duel/6877931/",
        "pub_date": "2021-12-12",
        "season": "2021",
        "event": "Abu Dhabi Grand Prix",
        "headline": "F1 Abu Dhabi GP: Verstappen defeats Hamilton to win title in controversial last-lap duel"
    },
    # --- ERA 3: 2022 Ground-Effect Reset, Cost Cap, & CRB Disputes ---
    {
        "url": "https://www.autosport.com/f1/news/f1-rule-changes-whats-new-in-2022-and-how-have-rules-affected-racing/8407567/",
        "pub_date": "2022-02-22",
        "season": "2022",
        "event": "Technical Regulations Overview",
        "headline": "F1 rule changes: what's new in 2022 and how have rules affected racing?"
    },
    {
        "url": "https://www.autosport.com/f1/news/f1-bahrain-gp-leclerc-leads-ferrari-1-2-red-bull-challenge-implodes/9167868/",
        "pub_date": "2022-03-20",
        "season": "2022",
        "event": "Bahrain Grand Prix",
        "headline": "F1 Bahrain GP: Leclerc leads Ferrari 1-2, Red Bull challenge implodes"
    },
    {
        "url": "https://www.autosport.com/f1/news/szafnauer-wishes-piastri-had-a-bit-more-integrity/10358377/",
        "pub_date": "2022-08-08",
        "season": "2022",
        "event": "Driver Market & Contract Recognition Board",
        "headline": "Szafnauer wishes Piastri had a bit more integrity"
    },
    {
        "url": "https://www.autosport.com/f1/news/ricciardo-no-regrets-over-time-at-mclaren-despite-early-split/10357214/",
        "pub_date": "2022-08-24",
        "season": "2022",
        "event": "Driver Market",
        "headline": "Daniel Ricciardo confirms early split from McLaren at end of 2022"
    },
    {
        "url": "https://www.autosport.com/f1/news/fia-hands-red-bull-7m-fine-aero-testing-reduction-for-cost-cap-breach/10391599/",
        "pub_date": "2022-10-28",
        "season": "2022",
        "event": "Financial Regulations Ruling",
        "headline": "FIA hands Red Bull $7m fine, aero testing reduction for cost cap breach"
    },
    {
        "url": "https://www.autosport.com/f1/news/ferrari-announces-vasseur-as-new-formula-1-boss/10410795/",
        "pub_date": "2022-12-13",
        "season": "2023",
        "event": "Ferrari Leadership Restructuring",
        "headline": "Ferrari announces Vasseur as new Formula 1 boss"
    },
    {
        "url": "https://www.autosport.com/f1/news/wolff-no-f1-budget-cap-wouldnt-have-solved-mercedes-w13s-issues/10411976/",
        "pub_date": "2022-12-14",
        "season": "2022",
        "event": "Technical & Season Review",
        "headline": "Wolff: No F1 budget cap wouldn't have solved Mercedes W13's issues"
    },
    # --- ERA 4: 2023 Dominance, Upgrades, & Mid-Season Switches ---
    {
        "url": "https://www.autosport.com/f1/news/williams-announce-mercedes-strategist-vowles-as-new-f1-team-principal/10420356/",
        "pub_date": "2023-01-13",
        "season": "2023",
        "event": "Team Management Restructuring",
        "headline": "Williams announce Mercedes strategist Vowles as new F1 team principal"
    },
    {
        "url": "https://www.autosport.com/f1/news/horner-and-tost-praise-lawson-after-zandvoort-f1-debut/10513056/",
        "pub_date": "2023-08-28",
        "season": "2023",
        "event": "Dutch Grand Prix",
        "headline": "Horner and Tost praise Lawson after Zandvoort F1 debut"
    },
    {
        "url": "https://www.autosport.com/f1/news/alonso-aston-martin-deserved-f1-2023-win-more-than-anyone-else/10557123/",
        "pub_date": "2023-12-13",
        "season": "2023",
        "event": "Season Review",
        "headline": "Alonso reflects on Aston Martin eight podiums and 2023 season trajectory"
    },
    {
        "url": "https://www.autosport.com/f1/news/red-bull-20kg-weight-purge-for-cut-and-shut-rb19-was-key-to-f1-2023-dominance/10558140/",
        "pub_date": "2023-12-18",
        "season": "2023",
        "event": "Technical & Season Review",
        "headline": "Red Bull: 20kg weight purge for cut-and-shut RB19 was key to F1 2023 dominance"
    },
    # --- ERA 5: 2024 Paddock Shocks, Crashes, & Active Aero Blueprints ---
    {
        "url": "https://www.autosport.com/f1/news/mercedes-announces-hamilton-split-ahead-of-ferrari-move-for-f1-2025/10571402/",
        "pub_date": "2024-02-01",
        "season": "2024",
        "event": "Driver Market Announcement",
        "headline": "Mercedes announces Hamilton split ahead of Ferrari move for F1 2025"
    },
    {
        "url": "https://www.autosport.com/f1/news/ferrari-unveils-sf-24-car-for-2024-f1-season/10575305/",
        "pub_date": "2024-02-13",
        "season": "2024",
        "event": "Car Launch",
        "headline": "Ferrari reveals SF-24 targeting title challenge against Red Bull"
    },
    {
        "url": "https://www.autosport.com/f1/news/bearman-replaces-sainz-for-saudi-arabian-grand-prix/10584719/",
        "pub_date": "2024-03-08",
        "season": "2024",
        "event": "Saudi Arabian Grand Prix",
        "headline": "Bearman replaces Sainz at Ferrari for Saudi Arabian GP after appendicitis diagnosis"
    },
    {
        "url": "https://www.autosport.com/f1/news/f1-reveals-2026-regulations-active-aero-smaller-lighter-cars/10620027/",
        "pub_date": "2024-06-06",
        "season": "2024",
        "event": "Regulations",
        "headline": "FIA officially unveils 2026 F1 regulations with active aero and 50-50 hybrid split"
    },
    {
        "url": "https://www.motorsport.com/f1/news/verstappen-denies-aggression-moving-under-braking-in-in-norris-austria-crash/10629956/",
        "pub_date": "2024-07-01",
        "season": "2024",
        "event": "Austrian Grand Prix",
        "headline": "Verstappen penalised after Austrian GP clash with Norris opens door for Russell"
    },
    {
        "url": "https://www.autosport.com/f1/news/how-once-stung-williams-finally-got-its-man-for-2025-with-sainz-signing/10640352/",
        "pub_date": "2024-07-29",
        "season": "2024",
        "event": "Williams Driver Signing",
        "headline": "How once-stung Williams finally got its man for 2025 with Sainz signing"
    },
    {
        "url": "https://www.autosport.com/f1/news/adrian-newey-to-join-aston-martin-legendary-designers-f1-career-highlights/10605736/",
        "pub_date": "2024-09-10",
        "season": "2024",
        "event": "Technical Personnel & Aston Martin",
        "headline": "Adrian Newey to join Aston Martin: Legendary designer's F1 career highlights"
    },
    {
        "url": "https://www.autosport.com/f1/news/f1-abu-dhabi-gp-mclaren-clinches-constructors-title-as-norris-wins-race/10680663/",
        "pub_date": "2024-12-08",
        "season": "2024",
        "event": "Abu Dhabi Grand Prix & Constructors Championship",
        "headline": "F1 Abu Dhabi GP: McLaren clinches constructors' title as Norris wins race"
    },
    # --- ERA 6: 2025 Progressions & Pre-2026 Preparations ---
    {
        "url": "https://www.autosport.com/f1/news/what-progress-looks-like-for-williams-in-f1-2025/10697243/",
        "pub_date": "2025-02-14",
        "season": "2025",
        "event": "Williams 2025 Season Progress",
        "headline": "What progress looks like for Williams in F1 2025"
    },
    {
        "url": "https://www.autosport.com/f1/news/hamiltons-low-confidence-in-wet-made-ferrari-f1-debut-worse-than-expected/10703977/",
        "pub_date": "2025-03-16",
        "season": "2025",
        "event": "Australian Grand Prix & Ferrari Debut",
        "headline": "Hamilton's low confidence in wet made Ferrari F1 debut worse than expected"
    },
    {
        "url": "https://www.autosport.com/f1/news/lindblad-to-make-fp1-debut-at-f1-british-gp-says-marko/10735947/",
        "pub_date": "2025-06-25",
        "season": "2025",
        "event": "British Grand Prix & Red Bull Junior Program",
        "headline": "Lindblad to make FP1 debut at F1 British GP, says Marko"
    },
    {
        "url": "https://www.autosport.com/f1/news/hadjar-open-to-early-red-bull-test-ahead-of-f1-2026/10768009/",
        "pub_date": "2025-10-16",
        "season": "2025",
        "event": "Red Bull 2026 Promotion",
        "headline": "Hadjar open to early Red Bull test ahead of F1 2026"
    },
    # --- ERA 7: 2026 Crash Reports & Red Flag Incidents ---
    {
        "url": "https://www.autosport.com/f1/news/dutch-f1-grand-prix-red-flagged-after-huge-max-verstappen-crash/10848603/",
        "pub_date": "2026-08-23",
        "season": "2026",
        "event": "Dutch Grand Prix",
        "headline": "Dutch F1 Grand Prix red flagged after huge Max Verstappen crash"
    },
    {
        "url": "https://www.autosport.com/f1/news/what-caused-verstappens-f1-dutch-gp-crash/10848642/",
        "pub_date": "2026-08-23",
        "season": "2026",
        "event": "Dutch Grand Prix",
        "headline": "What caused Verstappen's F1 Dutch GP crash"
    },
    {
        "url": "https://www.motorsport.com/f1/news/it-made-no-sense-f1-drivers-question-safety-car-formation-lap-after-early-dutch-gp-chaos/10848751/",
        "pub_date": "2026-08-23",
        "season": "2026",
        "event": "Dutch Grand Prix",
        "headline": "F1 drivers question safety car formation lap after early Dutch GP chaos"
    }
]

def scrape_and_save_article(item: dict) -> bool:
    """Scrapes paragraph content from Motorsport Network / Autosport and writes markdown-ready raw text."""
    url = item["url"]
    pub_date = item["pub_date"]
    headline = item["headline"]

    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code} for: {url}")
            return False

        soup = BeautifulSoup(response.content, "html.parser")

        paragraphs = []
        for p in soup.find_all("p"):
            text = p.get_text().strip()
            # Filter ads, photo tags, and navigational snippets
            if len(text) > 40 and not text.startswith("Photo by") and not text.startswith("©"):
                paragraphs.append(text)

        if not paragraphs:
            print(f"⚠️ No readable text found for: {headline}")
            return False

        body_content = "\n\n".join(paragraphs)

        formatted_file_text = (
            f"PUBLICATION_DATE: {pub_date}\n"
            f"SEASON: {item['season']}\n"
            f"EVENT: {item['event']}\n"
            f"HEADLINE: {headline}\n"
            f"SOURCE_URL: {url}\n\n"
            f"{body_content}"
        )

        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", headline.lower())
        slug = re.sub(r"_+", "_", slug)[:50].strip("_")
        filename = f"{pub_date}_{slug}.txt"
        file_path = os.path.join(RAW_DIR, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted_file_text)

        print(f"✅ [{pub_date}] Saved: {filename} ({len(paragraphs)} paras)")
        return True

    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        return False

def main():
    print("=" * 60)
    print("🏁 CHRONOGRAPH: HISTORICAL CORPUS SEEDER (2018-2026)")
    print(f"📁 Destination: {RAW_DIR}")
    print(f"📄 Target Milestones: {len(ARCHIVE_TARGETS)}")
    print("=" * 60)

    success = 0
    for idx, item in enumerate(ARCHIVE_TARGETS, start=1):
        print(f"[{idx:02d}/{len(ARCHIVE_TARGETS)}] Scraping: {item['headline'][:50]}...")
        if scrape_and_save_article(item):
            success += 1
        time.sleep(1.0)  # Standard polite delay

    print("=" * 60)
    print(f"🎉 Seeding complete: {success}/{len(ARCHIVE_TARGETS)} historical files stored.")
    print("Next step: Run `python ingestion_pipeline.py` to populate Neo4j and vector embeddings.")

if __name__ == "__main__":
    main()
import os
import sys
import time
import subprocess

# Resolve base project directory dynamically to make cron execution bulletproof
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw_news")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed_news")
RETENTION_DAYS = 14


def cleanup_old_archives(retention_days: int = RETENTION_DAYS):
    """Purges archived .txt files older than the retention_days safely."""
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        return

    cutoff = time.time() - (retention_days * 86400)
    purged_count = 0

    for filename in os.listdir(PROCESSED_DIR):
        file_path = os.path.join(PROCESSED_DIR, filename)
        try:
            if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff:
                os.remove(file_path)
                purged_count += 1
        except (PermissionError, OSError) as e:
            print(f"⚠️ Could not delete locked file {filename}: {e}")

    if purged_count > 0:
        print(f"🧹 Cleaned up {purged_count} archived files older than {retention_days} days.")
    else:
        print(f"✨ Archive directory clean. No files older than {retention_days} days.")


def run_step(step_name: str, script_name: str, timeout_seconds: int = 900):
    """Executes a pipeline step synchronously with unbuffered real-time output and timeout protection."""
    print("\n" + "=" * 75)
    print(f"🚀 [STEP] {step_name}: Running {script_name}")
    print("=" * 75)

    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Missing script: {script_path}")

    try:
        # '-u' forces unbuffered stdout so your print statements and pause timers stream immediately
        result = subprocess.run(
            [sys.executable, "-u", script_path],
            cwd=BASE_DIR,
            capture_output=False,
            timeout=timeout_seconds
        )

        if result.returncode != 0:
            print(f"❌ Error encountered in {script_name} (Exit code: {result.returncode})")
            raise RuntimeError(f"Pipeline stopped at step: {step_name}")
        else:
            print(f"✅ {step_name} completed successfully.")

    except subprocess.TimeoutExpired:
        print(f"⏱️ Step '{step_name}' exceeded timeout of {timeout_seconds}s and was killed.")
        raise RuntimeError(f"Pipeline timed out at step: {step_name}")


def run_full_pipeline():
    """Main orchestrator lifecycle."""
    start_time = time.time()
    print(f"🏎️ Starting Chronograph Ingestion & Build Cycle at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}...")

    # Step 1: Ingestion & Scraping
    run_step("News Scraping & Ingestion", "ingestion_pipeline.py", timeout_seconds=180)

    # Guard: Check if any new raw articles were actually gathered
    raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith(".txt")] if os.path.exists(RAW_DIR) else []
    
    if not raw_files:
        print("\nℹ️ No new un-processed articles found in raw_news. Skipping Graph Extraction.")
    else:
        print(f"\n📦 Found {len(raw_files)} new articles queued for ingestion.")
        # Step 2: Knowledge Graph Extraction & Neo4j Ingestion (allow up to 40 mins for Groq rate limits)
        run_step("Graph Extraction & Ingestion", "build_knowledge_graph.py", timeout_seconds=2400)

    # Step 3: Maintenance & Archive Cleanup
    print("\n" + "=" * 45)
    print("🧹 [STEP] Running Storage Retention Maintenance")
    print("=" * 45)
    cleanup_old_archives()

    elapsed = round(time.time() - start_time, 2)
    print(f"\n🎉 Full cycle completed cleanly in {elapsed} seconds!")


if __name__ == "__main__":
    run_full_pipeline()
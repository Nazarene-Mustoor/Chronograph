# 🏎 ChronoGraph: Temporal GraphRAG for Formula 1

An end-to-end, production-grade **Temporal GraphRAG Intelligence Engine** designed to reconstruct complex Formula 1 technical regulations, controversial sporting incidents, and multi-year driver market lineages across ground-effect and hybrid eras.

Built with a custom hybrid architecture pairing **Neo4j graph traversals**, **semantic vector embeddings**, and **Gemini 3.8 Flash**, ChronoGraph solves LLM synthesis latency by streaming interactive telemetry timeline traces to the UI within seconds.

---

## 🚀 Project Vision

Standard LLMs struggle with Formula 1 history: they conflate mid-season driver swaps, aggregate synonymous penalties into non-existent multi-grid demotions, and hallucinate rules across regulatory transitions. 

**ChronoGraph** solves this by enforcing a grounded Knowledge Graph where temporal relationships, entity boundaries (single constructor rules), and regulatory technical directives are preserved as deterministic facts rather than probabilistic guesses.

---

## 🧠 Why Temporal GraphRAG?

F1 is an evolving technical ecosystem where answers depend on **when** an event happened:
* In standard RAG, retrieving a 2022 regulation about porpoising can contradict a 2024 active aero technical directive.
* With **Temporal GraphRAG**, facts are anchored by timestamp, regulatory epoch, and event lineage, enabling queries like *"Trace how the paddock debate over the 'Macarena wing' shifted from an aero gray area into formal FIA scrutiny."*

---

## 📦 Tech Stack

* **Neo4j (Aura / Local)** — Cypher graph traversal, vector indexing, multi-hop relationship extraction
* **Gemini 3.8 Flash (OpenAI API Layer)** — High-reasoning temporal synthesis and analytical editorial writing
* **Reflex** — Pure Python full-stack reactive framework for low-latency interactive dashboards
* **FastAPI & Uvicorn** — Asynchronous NDJSON streaming server for progressive payload delivery
* **BeautifulSoup4 & Requests** — Automated scraper and historical archive seeder
* **Docker & Docker Compose** — Containerized local orchestration

---

## 🏗️ Architecture & Streaming Flow

ChronoGraph uses an asynchronous **NDJSON Progressive Pipeline** to eliminate perceived LLM latency:

```
[ User Query ]
       │
       ▼
[ FastAPI Backend /api.py ]
       │
       ├───▶ 1. Cypher Graph Traversal + Vector Search (Neo4j)
       │
       ├───▶ 2. Flash-Lite Synthesizes Cinematic Timeline Cards (~1.2s)
       │      │
       │      └─▶ [EMIT TELEMETRY PACKET] ──▶ Reflex UI renders "Pit Wall" immediately!
       │
       └───▶ 3. Gemini 3.8 Flash Streams Full Investigation Report (Token-by-Token)
              │
              └─▶ [EMIT TOKEN STREAM] ────▶ Reflex UI streams editorial text live
```

---

## 📂 Project Structure

```text
chronograph/
├── .github/workflows/
│   └── nightly_sync.yml        # Automated scheduled ingestion workflow
├── app/
│   ├── ui/
│   │   ├── ui.py               # Reflex reactive dashboard & streaming client
│   │   └── traces.py           # Cinematic "Pit Wall" timeline grammar components
├── data/
│   ├── raw_news/               # Raw scraped motorsport articles (.gitignore)
│   ├── processed_news/         # Extracted entities & sanitized text (.gitignore)
│   └── scraped_news.txt        # Staging buffer
├── api.py                      # FastAPI streaming backend & GraphRAG bridge
├── build_knowledge_graph.py    # Neo4j schema, constraints, and relationship ingestion
├── evaluator.py                # GraphRAG grounding and hallucination metrics
├── history_backfill.py         # Curated 2018-2026 archive seeder (31 core milestones)
├── hydrate_chunks.py           # Vector embedding generator for graph nodes
├── ingestion_pipeline.py       # Entity extraction and semantic linking pipeline
├── orchestrator.py             # Multi-hop retrieval loop and archetype classifier
├── retrieval.py                # Cypher query builder & semantic vector search
├── run_benchmark_queries.py    # Benchmark runner across narrative archetypes
├── scraper.py                  # On-demand CLI backfill scraper for requested events
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
├── docker-compose.yml          # Multi-container setup (Neo4j + ChronoGraph)
└── .env.example                # Configuration template
```

---

## 📍 System Status & Progress

- [x] **Graph Database Schema:** Neo4j constraints for Drivers, Constructors, Grand Prix, and Technical Directives
- [x] **Historical Archive Seed:** 31 foundational milestones scraped and ingested across 2018–2026
- [x] **Zero-Latency Telemetry Streaming:** Instant Pit Wall timeline rendering via NDJSON packets
- [x] **Domain Guardrails:** Prompt engineering constraints preventing dual-constructor hallucinations and duplicate penalty counts
- [x] **Collapsible Executive Briefing:** UI preview mode with expandable deep-dive investigation toggle
- [x] **Interactive Archetypes:** Dynamic grammar support for `EPISTEMIC_PERCEPTION_SHIFT`, `CAUSAL_CONSEQUENCE_CHAIN`, and `TEMPORAL_EVOLUTION`, etc.
- [x] **On-Demand Backfill Engine:** CLI-driven article scraper to ingest community-requested events directly into the active graph

---

## 🎯 Supported Analytical Archetypes

ChronoGraph categorizes historical inquiries into structured narrative archetypes:

1. **Epistemic Perception Shift:** Maps how paddock consensus transformed from initial loophole exploitation to formal FIA intervention.
2. **Causal Consequence Chain:** Traces how a single racing lap incident cascaded into penalty points, contractual clauses, and constructor standings.
3. **Temporal Evolution:** Chronological breakdown tracking technical upgrades or team development across seasons.
4. **Multihop Lineage:** Maps driver career progressions, junior academy promotions, and reserve driver call-ups.

---

## 🔧 How to Run Locally

### 1. Clone the Repository
```bash
git clone https://github.com/Nazarene-Mustoor-1570/chronograph.git
cd chronograph
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Unix/MacOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template and add your credentials:
```bash
cp .env.example .env
```
Ensure your `.env` contains:
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=neo4j

GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
```

### 4. Seed the Knowledge Graph (Optional / First Run)
```bash
# Seed 2018-2026 archive
python history_backfill.py

# Build graph entities & vector embeddings
python ingestion_pipeline.py
```

### 5. Launch the Application

In **Terminal 1** (Backend API):
```bash
uvicorn api:app --reload --port 8000
```

In **Terminal 2** (Reflex Dashboard):
```bash
reflex run
```

Open your browser at `http://localhost:3000` to access ChronoGraph.

---

## 🧪 On-Demand Backfill Scraper

To backfill a new event or article requested from the Pit Wall queue:
```bash
python scraper.py --url "https://www.autosport.com/f1/news/sample-article" --event "Baku Grand Prix" --season "2026"
python ingestion_pipeline.py
```

---

## 👤 Author

**Nazarene Mustoor**  
*Data & AI Engineer*  
*Specializing in Real-Time Streaming Systems & Temporal GraphRAG Architecture.*

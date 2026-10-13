# 🏎️ ChronoGraph: Temporal GraphRAG for Formula 1

An end-to-end, live **Temporal GraphRAG Intelligence Engine** designed to reconstruct complex Formula 1 technical regulations, controversial sporting incidents, and multi-year driver market lineages across ground-effect and hybrid eras.

Built with a custom hybrid architecture pairing **Neo4j graph traversals**, **semantic vector embeddings**, and **Gemini 3.8 Flash**, ChronoGraph solves LLM synthesis latency by streaming interactive telemetry timeline traces to the UI within seconds.

> 📖 **Read the Full Engineering Deep Dive on Medium:**  
> [Beyond the Lap Times: Building Chronograph](https://medium.com/@nazarenemustoor/beyond-the-lap-times-building-chronograph)
>
> 🏎️ **Live Paddock Engine:** [chronograph-f1-engine.reflex.run](https://chronograph-f1-engine.reflex.run)  
> *(Optimized for desktop/laptop displays. Mobile supports pinch-to-zoom scaling via custom viewport).*

---

## 🚀 Project Vision

Standard LLMs struggle with Formula 1 history: they conflate mid-season driver swaps, aggregate synonymous penalties into non-existent multi-grid demotions, and hallucinate rules across regulatory transitions. 

**ChronoGraph** solves this by enforcing a grounded Knowledge Graph where temporal relationships, entity boundaries, and regulatory technical directives are preserved as deterministic facts rather than probabilistic guesses.

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

## 🏗️ Architecture & Parallel Retrieval Flow

ChronoGraph runs a dual-branch parallel retrieval architecture to balance structural relationships with narrative reporting:

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
├── history_backfill.py         # Curated 2021-2025 archive seeder (25 core milestones)
├── hydrate_chunks.py           # Vector embedding generator & emergency chunk recovery utility
├── ingestion_pipeline.py       # Entity extraction and semantic linking pipeline
├── orchestrator.py             # Multi-hop retrieval loop and archetype classifier
├── retrieval.py                # Cypher query builder & semantic vector search
├── run_benchmark_queries.py    # Benchmark runner across narrative archetypes (42 queries)
├── scraper.py                  # On-demand CLI backfill scraper for requested events
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
├── docker-compose.yml          # Multi-container setup (Neo4j + ChronoGraph)
└── .env.example                # Configuration template
## 📍 System Status & Progress
- [x] **Graph Database Schema:** Neo4j constraints for Drivers, Constructors, Grand Prix, and Technical Directives

- [x] **Curated Milestone Seed:** 25 defining historical milestones ingested across 2021–2025 (Abu Dhabi '21, 2022 ground effect reset, Piastri saga, cost-cap breach, Zandvoort injury, etc.)

- [x] **Benchmark Evaluation Suite:** 42-query test suite passing across all 7 investigation archetypes

- [x] **Parallel Retrieval Engine:** Dual-branch execution combining Text2Cypher structural queries with VectorCypher semantic chunking

- [x] **Zero-Latency Telemetry Streaming:** Instant Pit Wall timeline rendering via NDJSON packets

- [x] **Resilient Ingestion & Recovery:** hydrate_chunks.py fallback utility for rebuilding semantic layers directly from raw graph entities

- [x] **On-Demand Backfill Engine:** Interactive queue and CLI scraper to ingest community-voted historical events directly into the active graph

---

## 🎯 The 7 Supported Analytical Archetypes
ChronoGraph classifies inquiries into 7 distinct investigative archetypes:

1. **Epistemic Perception Shift:** Maps how paddock consensus transformed from initial loophole exploitation to formal FIA intervention.

2. **Causal Consequence Chain:** Traces how a single racing incident cascaded into penalty points, contractual disputes, and constructor standings (e.g., Austria 2024 Lap 64).

3. **Temporal Evolution:** Chronological breakdown tracking technical upgrades or team lineup evolution across seasons.

4. **Multihop Lineage:** Maps driver career progressions, junior academy promotions, and reserve driver call-ups across teams.

5. **Regulatory Impact Analysis:** Traces how specific Technical Directives altered competitive performance and aero concepts.

6. **Contradiction & Dispute Resolution:** Synthesizes competing steward rulings and telemetry statements across controversial stewarding decisions.

7. **Cross-Season Lineup Dynamics:** Reconstructs complex multi-year contractual shifts, buyouts, and team principal transitions.

--- 

## 🔧 How to Run Locally

### 1. Clone the Repository
```bash
git clone https://github.com/Nazarene-Mustoor/Chronograph.git
cd Chronograph
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
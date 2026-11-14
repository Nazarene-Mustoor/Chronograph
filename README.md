# 🏎️ ChronoGraph: Temporal GraphRAG for Formula 1

An end-to-end, live **Temporal GraphRAG Intelligence Engine** designed to reconstruct complex Formula 1 technical regulations, controversial sporting incidents, and multi-year driver market lineages across ground-effect and hybrid eras.

Built with a custom hybrid architecture pairing **Neo4j AuraDB graph traversals**, **Gemini vector embeddings (`gemini-embedding-001`)**, and **`gemini-3.5-flash-lite`**, ChronoGraph eliminates LLM timeline hallucinations and streams interactive telemetry traces and dynamic HUD visuals to the UI within seconds.

> 📖 **Read the Full Engineering Deep Dive on Medium:**  
> [F1 Temporal GraphRAG Engine — Investigating F1 Lore with Neo4j & Reflex](https://medium.com/@nazarenemustoor/f1-temporal-graphrag-engine-df6e0c5484c8)
>
> 📊 **View the 42-Query Benchmark & Stress-Test Report:**  
> [BENCHMARK_REPORT.md](./BENCHMARK_REPORT.md)
>
> 🏎️ **Live Paddock Engine:** [chronograph-f1-engine.reflex.run](https://chronograph-f1-engine.reflex.run)  
> *(Optimized for desktop/laptop displays. Mobile supports pinch-to-zoom scaling via custom viewport).*

---

## 🚀 Project Vision

Standard LLMs struggle with Formula 1 history: they conflate mid-season driver swaps, suffer from vector recency bias, aggregate synonymous penalties into non-existent grid demotions, and hallucinate rules across regulatory transitions. 

**ChronoGraph** solves this by enforcing a grounded Temporal Knowledge Graph where chronological relationships, entity boundaries, and FIA technical directives are preserved as deterministic facts rather than probabilistic guesses.

---

## 🧠 Why Temporal GraphRAG?

F1 is a non-static technical ecosystem where truth depends on **when** an event happened:
* **Preventing Temporal Collapse:** In standard RAG, retrieving a 2022 regulation about porpoising can bleed into a 2026 active-aero query.
* **Epistemic Perception Tracking:** Facts are anchored by timestamp, season hub, and event lineage—enabling queries like *"Why did everyone say the Macarena rotating wing was legal until the FIA mandated mechanical modifications?"*

---

## 📦 Tech Stack

* **Neo4j AuraDB** — Property graph storage, APOC entity resolution, and cosine vector indexing (`chunkEmbedding`)
* **Gemini (`gemini-3.5-flash-lite` & `gemini-embedding-001`)** — Entity extraction, high-dimensional chunk vectorization, Cypher generation, and temporal synthesis
* **Reflex** — Pure Python full-stack reactive framework for the interactive telemetry dashboard
* **FastAPI & Uvicorn** — Asynchronous NDJSON streaming server for progressive payload delivery
* **BeautifulSoup4 & Feedparser** — Multi-source RSS scraper (`Autosport`, `BBC Sport`, `The Race`) with `SequenceMatcher` story deduplication
* **GitHub Actions & Docker** — Automated nightly ingestion workflows and containerized orchestration

---

## 🏗️ Architecture & Parallel Retrieval Flow

Instead of waiting for structured queries to fail before falling back to vector search, ChronoGraph executes a **Dual-Branch Parallel Ensemble** combined with an asynchronous **NDJSON Progressive Pipeline**:

```text
[ User Query ]
       │
       ▼
[ FastAPI Backend / api.py ]
       │
       ├───▶ Branch 1: Text2CypherRetriever (Deterministic Graph Triples & Multi-Hop Paths)
       ├───▶ Branch 2: VectorCypherRetriever (Semantic Chunks + 1-Hop Entity Traversal)
       │
       ├───▶ 1. Archetype Classifier & TraceNode Generator (~1.2s)
       │      └─▶ [EMIT TELEMETRY PACKET] ──▶ Reflex UI renders Reconstruction Trace & HUD Canvas
       │
       └───▶ 2. Temporal Synthesis Layer Streams Grounded Debrief (Token-by-Token)
              └─▶ [EMIT TOKEN STREAM] ────▶ Reflex UI renders Essential Context Primer + Report
```

### 🖥️ Reflex UI: Dynamic HUD Canvas & Reconstruction Traces
* **Reconstruction Trace (`TraceNode`):** Dynamically adapts its visual layout to the query's analytical archetype (Timeline, Directed Causal Chain, Split Horizons, Parallel Tracks, Inflection Pivot, or Multi-Hop Lineage).
* **Context-Aware Telemetry HUD Carousel:** Scans synthesized debriefs in real time to render visual slides above the Knowledge Coverage deck:
  1. **Circuit Sector HUD:** Highlights specific track layouts and corners when circuits or sectors are referenced.
  2. **Chassis Wireframe Blueprint:** Pinpoints aerodynamic and mechanical upgrade zones (`CarUpgrade`).
  3. **FIA Stewards Banner:** Displays regulatory citations, penalties, and steward decisions with official flag states.
  4. **Pit-to-Car Radio Callout:** Extracts verbatim driver/pit-wall radio transcripts and team principal statements.
* **Essential Context Primer:** Provides an immediate, high-level executive synthesis before diving into the chronological evidence table.

---

## 🎯 The 7 Investigation Archetypes & Benchmark Suite

ChronoGraph was evaluated against a **42-query formal benchmark suite** plus **9 colloquial/half-context HUD stress tests** spanning 7 distinct investigative archetypes. 

👉 **[See the Full 42-Query Scorecard, Failure Taxonomy & Stress-Test Matrix in `BENCHMARK_REPORT.md`](./BENCHMARK_REPORT.md)**

| Archetype | Visual Trace Grammar | Core Investigation Target | Initial Pass | Post-Fix |
| :--- | :--- | :--- | :---: | :---: |
| **1. `TEMPORAL_EVOLUTION`** | Chronological Timeline | Multi-season career arcs, upgrade rollouts & contract timelines | 9 / 11 | **11 / 11** ✅ |
| **2. `TRANSITION_INFLECTION_POINT`** | Pivot / Hourglass | Pinpointing exact structural shifts in leadership or hierarchy | 4 / 5 | **5 / 5** ✅ |
| **3. `EPISTEMIC_PERCEPTION_SHIFT`** | Split Horizons ($T_1 \rightarrow T_2$) | Pre-season expectations vs. in-season reality & FIA disclosures | 6 / 7 | **7 / 7** ✅ |
| **4. `COMPARATIVE_TRAJECTORY`** | Parallel Tracks | Side-by-side constructor/driver trajectories & temporal graph diffs | 5 / 7 | **7 / 7** ✅ |
| **5. `CAUSAL_CONSEQUENCE_CHAIN`** | Directed Causal Flow | How a single catalyst (e.g., Austria '24 Lap 64) cascades across the grid | 10 / 11 | **11 / 11** ✅ |
| **6. `MULTIHOP_LINEAGE`** | Lineage Web | Cross-era substitution chains (Ricciardo '23 $\rightarrow$ Lawson $\rightarrow$ Hadjar '26) | Passed | **Passed** ✅ |
| **7. `FACTUAL_LOOKUP`** | Structured Telemetry Card | Deterministic regulation checks & zero-hallucination refusals | Passed | **Passed** ✅ |
| **Colloquial HUD Stress Suite** | Dynamic HUD Carousel + Trace | 9 lower-case, half-context fan prompts & dual-schematic triggers | **9 / 9** | **9 / 9** ✅ |

### 🔬 Engineering Post-Mortem Summary (How We Fixed the 7 Initial Failures)

1. **Entity Attribution Inversion (Queries #14, #27, #34):** Locked driver-team edges to explicit season hubs so in-race quotes (e.g., Ferrari's Hamilton referencing *"the two Mercedes drivers ahead"*) never invert team affiliations.
2. **Unbounded Temporal Vector Bleed (Queries #24, #29):** Implemented a **2-Tier Multi-Year Context Budget** (~300 tokens for deterministic Cypher season-driver tables + ~2,500 tokens for narrative excerpts) to prevent 2026 vector chunks from contaminating 2021–2023 historical reconstructions.
3. **Cartesian Chunk Joins & Dialect Traps (Queries #8, #11):** Stripped `:Chunk` from `Text2Cypher` schema prompts (*Text2Cypher queries domain entities only; VectorCypher handles text chunks*), escaped Python `str.format()` collisions (`KeyError: 'name'`), and deployed label-agnostic APOC graph sanitization (`sanitize_graph()`).

---

## 📂 Project Structure

```text
chronograph/
├── .github/workflows/
│   └── nightly_sync.yml        # Automated nightly RSS scrape, KG extraction & APOC cleanup
├── app/
│   ├── ui/
│   │   ├── ui.py               # Reflex reactive dashboard, HUD carousel & streaming client
│   │   └── traces.py           # Archetype TraceNode visualizers & Pit Wall grammar
├── data/
│   ├── raw_news/               # Newly scraped motorsport articles staging buffer
│   ├── processed_news/         # Archived articles (auto-pruned after 14-day retention)
│   └── scraped_history.txt     # URL deduplication ledger
├── api.py                      # FastAPI NDJSON streaming backend & GraphRAG bridge
├── build_knowledge_graph.py    # Neo4j schema, Gemini extraction & generalized APOC sanitization
├── evaluator.py                # GraphRAG grounding and anti-hallucination verifier
├── history_backfill.py         # Curated 2021-2025 archive seeder (25 catalyst milestones)
├── hydrate_chunks.py           # Graph-to-chunk synthetic recovery & embedding utility
├── ingestion_pipeline.py       # Multi-feed RSS scraper with SequenceMatcher deduplication
├── orchestrator.py             # End-to-end cron pipeline runner & 14-day archive cleanup
├── retrieval.py                # Parallel Ensemble (Text2Cypher + VectorCypher) & Temporal Synthesis
├── run_benchmark_queries.py    # Automated 42-query evaluation runner across 7 archetypes
├── BENCHMARK_REPORT.md         # Full 42-query benchmark & 9 casual stress-test evaluation report
├── Dockerfile                  # Container definition
├── docker-compose.yml          # Multi-container orchestration
└── .env.example                # Environment configuration template
```

---

## 🔧 How to Run Locally

### 1. Clone the Repository & Install Dependencies
```bash
git clone [https://github.com/Nazarene-Mustoor/Chronograph.git](https://github.com/Nazarene-Mustoor/Chronograph.git)
cd Chronograph
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file from `.env.example`:
```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=neo4j

GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
```

### 3. Run the Ingestion & Graph Pipeline
```bash
# Run full scrape -> KG extraction -> APOC sanitization -> archive cleanup
python orchestrator.py
```

### 4. Launch the Application
In **Terminal 1** (FastAPI Streaming Backend):
```bash
uvicorn api:app --reload --port 8000
```
In **Terminal 2** (Reflex Telemetry UI):
```bash
reflex run
```
Open `http://localhost:3000` to explore ChronoGraph.
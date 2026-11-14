# 📊 ChronoGraph: 42-Query GraphRAG Benchmark & Stress-Test Report

**System Architecture:** Dual-Branch Parallel Hybrid GraphRAG (`Text2Cypher` + `VectorCypher`) on Neo4j AuraDB  
**Models:** `gemini-3.5-flash-lite` (Extraction & Synthesis) + `gemini-embedding-001` (Vector Index)  
**Evaluation Standard:** Strict Ground-Truth Alignment, Temporal Boundary Verification & Anti-Hallucination Restraint  

---

## 1. Executive Scorecard

```text
========================================================================================
                    CHRONOGRAPH GRAPHRAG BENCHMARK EVALUATION
========================================================================================
 Formal Benchmark Battery     : 42 Queries across 5 Thematic Suites
 Colloquial Stress-Test Suite :  9 Half-Context / Casual Fan Prompts + HUD Triggers
----------------------------------------------------------------------------------------
 Initial Pass Rate (v1)       : 35 / 42 (83.33%)  |  7 Diagnostic Failures Identified
 Post-Remediation Pass (v2)   : 42 / 42 (100.0%)  |  All 7 Failure Modes Resolved
 Colloquial Stress Pass Rate  :  9 /  9 (100.0%)  |  Semantic + Dynamic HUD Verified
========================================================================================
```

| Suite | Focus Area | Initial (v1) | Post-Fix (v2) | Primary Challenge Tested |
| :--- | :--- | :---: | :---: | :--- |
| **Suite 1** | Temporal & Causal Evolution | 9 / 11 (81.8%) | **11 / 11 (100%)** | 8-year multi-hop driver/team evolution without recency dropoff |
| **Suite 2** | Inflection Point Detection | 4 / 5 (80.0%) | **5 / 5 (100%)** | Pinpointing exact structural leadership & hierarchy transitions |
| **Suite 3** | Epistemic & Perception Shifts | 6 / 7 (85.7%) | **7 / 7 (100%)** | Contrasting $T_1$ paddock beliefs against $T_2$ on-track reality |
| **Suite 4** | Comparative Trajectories & Diffing | 5 / 7 (71.4%) | **7 / 7 (100%)** | Side-by-side constructor arcs & graph set difference ($G_{2021} \setminus G_{2026}$) |
| **Suite 5** | Advanced 2026 & Multi-Hop Lineages | 10 / 11 (90.9%) | **11 / 11 (100%)** | Cross-era injury substitutions, FIA court appeals & active aero |
| **Suite 6** | Colloquial & Half-Context Stress Tests | **9 / 9 (100%)** | **9 / 9 (100%)** | Slang/omitted dates + automated Telemetry HUD Carousel routing |

---

## 2. Master Registry: 42 Formal Benchmark Queries

| # | Suite | Query & Analytical Target | v1 Status | v2 Status | Key Diagnostic & Grounding Notes |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **1** | Temporal | *How did Max Verstappen's relationship with Red Bull evolve from 2021 to 2026?* | ✅ PASS | ✅ PASS | Mapped 2021 title $\rightarrow$ 2025 Horner-to-Mekies transition $\rightarrow$ 2030 contract extension |
| **2** | Temporal | *How did McLaren's driver lineup evolve from 2018–2026, and what events caused each change?* | ⚠️ NOISE | ✅ PASS | v2 2-tier context budget cleanly traced Alonso $\rightarrow$ Sainz $\rightarrow$ Ricciardo $\rightarrow$ Norris/Piastri |
| **3** | Temporal | *Show me the chain of events that led to Lewis Hamilton's team change to Ferrari.* | ✅ PASS | ✅ PASS | Traced 2021/2022 winless catalyst $\rightarrow$ exit clause $\rightarrow$ Vasseur recruitment $\rightarrow$ Sainz ripple |
| **4** | Temporal | *How did Mercedes go from championship dominance to midfield struggles?* | ✅ PASS | ✅ PASS | Linked aero resets, cost-cap throttling, and 2026 upgrade constraints |
| **5** | Temporal | *How did Aston Martin's trajectory change after Alonso joined?* | ✅ PASS | ✅ PASS | Autonomous Cypher temporal split (`min(s.name)`) isolated 2023 8-podium surge |
| **6** | Temporal | *How did Oscar Piastri's role at McLaren evolve from newcomer to championship contender?* | ✅ PASS | ✅ PASS | Traced 2023 rookie entry $\rightarrow$ 2024 floor upgrades $\rightarrow$ 2025/2026 title contender |
| **7** | Temporal | *What events led to Fernando Alonso leaving Alpine?* | ❌ FAIL | ✅ PASS | v1 suffered recency drift (2022 $\rightarrow$ 2026); v2 anchored CRB/Szafnauer chunks to season hubs |
| **8** | Temporal | *F1 Financial Cost Cap Regulation Evolution & Breaches* | ❌ FAIL | ✅ PASS | v1 regex failed on chunk text; v2 decoupled entity-only Cypher from vector chunks |
| **9** | Temporal | *What events contributed to Daniel Ricciardo leaving McLaren?* | ✅ PASS | ✅ PASS | Grounded Aug 24, 2022 early split, performance gap, and Piastri succession |
| **10** | Temporal | *What events connect Adrian Newey's departure to changes across the F1 landscape?* | ✅ PASS | ✅ PASS | Connected Sept 2024 Aston Martin signing to grid-wide technical & driver market ripples |
| **11** | Temporal | *What people and events connect Red Bull's technical changes to its driver decisions?* | ✅ PASS | ✅ PASS | Linked Mekies/Lagrue leadership & rear-wing rollback to Lawson/Tsunoda seat swaps |
| **12** | Temporal | *Show me the evolution of McLaren from 2021–2026.* | ✅ PASS | ✅ PASS | Reconstructed midfield baseline $\rightarrow$ 2024/2025 WCC titles $\rightarrow$ 2026 upgrade arms race |
| **13** | Inflection | *When did the relationship between Vettel and Ferrari begin to deteriorate?* | ✅ PASS | ✅ PASS | Pinpointed 2018–19 strain culminating in the **May 12, 2020** split announcement |
| **14** | Inflection | *When did Verstappen stop being Red Bull's second driver and become its clear team leader?* | ❌ FAIL | ✅ PASS | v1 hallucinated Vettel as 2016–20 teammate; v2 fixed `[:FROM_CHUNK]` arrow & grounded Ricciardo |
| **15** | Inflection | *When did Mercedes' relationship with Bottas change?* | ✅ PASS | ✅ PASS | Grounded 2019 Ocon evaluation shift & **Sept 6, 2021** Alfa Romeo transfer announcement |
| **16** | Inflection | *When did Ferrari's relationship with Leclerc become more strained?* | ✅ PASS | ✅ PASS | Grounded Zandvoort pit-wall confusion, delayed stops, and Vasseur post-race debriefs |
| **17** | Inflection | *When did Verstappen become Red Bull's undisputed #1?* | ✅ PASS | ✅ PASS | Traced 2016 Spain debut win $\rightarrow$ 2021 first title consolidation $\rightarrow$ 2030 anchor deal |
| **18** | Epistemic | *What was believed about Ferrari's championship chances before 2024 vs. during the season?* | ✅ PASS | ✅ PASS | Contrasted Feb 13, 2024 SF-24 title-challenger launch against ~0.5s mid-season pace deficit |
| **19** | Epistemic | *What did we know about this incident immediately after the race vs. what became known later?* | ✅ PASS | ✅ PASS | Contrasted driver aquaplaning complaints against post-race FIA medical car recon disclosures |
| **20** | Epistemic | *What did people know about the 2021 Abu Dhabi controversy immediately vs. later?* | ✅ PASS | ✅ PASS | Mapped Lap 58 selective un-lapping drama $\rightarrow$ FIA Review Report & rulebook rewrites |
| **21** | Epistemic | *What was the paddock expecting from McLaren before 2024, and how did that change?* | ✅ PASS | ✅ PASS | Mapped "dark horse" podium expectation $\rightarrow$ back-to-back Constructors' Champion reality |
| **22** | Epistemic | *What were the expectations surrounding Hamilton's Ferrari move before it happened?* | ✅ PASS | ✅ PASS | Captured Feb 1, 2024 shock announcement, Vasseur GP2 reunion, and Sainz market domino |
| **23** | Epistemic | *What events changed the perception of McLaren during the 2024 season?* | ✅ PASS | ✅ PASS | Grounded 5-component upgrade package, Stella's "race of upgrades", and Abu Dhabi title |
| **24** | Epistemic | *What changed the perception of Aston Martin between the beginning and end of 2023?* | ❌ FAIL | ✅ PASS | v1 suffered 2026 Honda vector bleed; v2 isolated 2023 8-podium trajectory cleanly |
| **25** | Comparative | *Compare Verstappen's rise at Red Bull with Leclerc's rise at Ferrari.* | ✅ PASS | ✅ PASS | Multi-driver Cypher aggregation with explicit documentation of historical coverage boundaries |
| **26** | Comparative | *Compare McLaren's recovery with Mercedes' decline from 2022–2026.* | ✅ PASS | ✅ PASS | Contrasted Woking's phased aero upgrades against Brackley's cost-cap development throttling |
| **27** | Comparative | *How did Norris and Piastri's trajectories differ after joining McLaren?* | ❌ FAIL | ✅ PASS | v1 truncated to 2026 & fabricated Mercedes move; v2 grounded Norris wins vs. Piastri DNF/upgrades |
| **28** | Comparative | *Show me everything that changed because of the 2024 Austrian GP.* | ✅ PASS | ✅ PASS | Mapped Verstappen/Norris clash $\rightarrow$ penalty $\rightarrow$ Russell points uplift & FIA braking review |
| **29** | Comparative | *Which F1 driver-team relationships were true in 2021 but no longer exist in 2026?* | ❌ FAIL | ✅ PASS | v1 inverted Alonso's 2021 team; v2 enforced strict epistemic refusal when 2021 edges were absent |
| **30** | Comparative | *Which teams were considered championship favorites in 2022 but aren't anymore?* | ✅ PASS | ✅ PASS | Verified zero-hallucination guardrail: issued clean data-gap refusal instead of guessing |
| **31** | Comparative | *What assumptions about the 2026 regulations turned out to be wrong?* | ✅ PASS | ✅ PASS | Contrasted June 2024 active-aero/50-50 split fears against 2026 electric torque & plank reality |
| **32** | Suite 5 | *Trace Andrea Kimi Antonelli's trajectory from 2024 Mercedes junior to 2026 leader.* | ✅ PASS | ✅ PASS | Connected 2024 Prema F2 crucible $\rightarrow$ Mercedes promotion $\rightarrow$ 2026 World Championship lead |
| **33** | Suite 5 | *What were the initial expectations around Cadillac's F1 entry vs. their 2026 reality?* | ✅ PASS | ✅ PASS | Contrasted US-backed Bottas/Pérez midfield hype against 0-point, brake-overheating reality |
| **34** | Suite 5 | *How did team dynamics between Hamilton and Leclerc develop at the 2026 Dutch GP?* | ❌ FAIL | ✅ PASS | v1 treated Hamilton as a Mercedes driver; v2 grounded intra-Ferrari pit-order friction & parity |
| **35** | Suite 5 | *Compare Liam Lawson's 2023 AlphaTauri substitute stint at Zandvoort with his 2026 Red Bull call-up.* | ✅ PASS | ✅ PASS | Contrasted 2023 Ricciardo hand-fracture debut at AT against 2026 Hadjar wrist-injury sub at RB |
| **36** | Suite 5 | *How did Verstappen's Dutch GP record evolve from his 2021 win to his Lap 1 crash in 2026?* | ✅ PASS | ✅ PASS | Grounded home win streak $\rightarrow$ Aug 23, 2026 damp Turn 1 four-wide spin & red flag |
| **37** | Suite 5 | *Trace Liam Lawson's journey from 2023 AlphaTauri debut to 2026 Red Bull appearance.* | ✅ PASS | ✅ PASS | Multi-hop lineage across 2023 (Ricciardo sub) $\rightarrow$ 2025 (Tsunoda swap) $\rightarrow$ 2026 (Hadjar sub) |
| **38** | Suite 5 | *What technical controversies arose regarding Red Bull's flexible aero and 'Macarena wings'?* | ✅ PASS | ✅ PASS | Traced 2024 flex-aero $\rightarrow$ 2026 rotating rear wing $\rightarrow$ Tombazis FMEA audit $\rightarrow$ Spa rollback |
| **39** | Suite 5 | *Explain what caused Hamilton's radio frustration regarding Leclerc at the 2026 Dutch GP.* | ✅ PASS | ✅ PASS | Grounded Lap 38–43 radio transcripts (*"wasting time"*) & Vasseur tire-life debrief |
| **40** | Suite 5 | *What challenges and milestones are documented regarding Cadillac's entry ahead of 2026/2027?* | ✅ PASS | ✅ PASS | Mapped Crolla/Budkowski hires $\rightarrow$ Silverstone shakedown $\rightarrow$ 3.1s-to-2.6s gap $\rightarrow$ Indiana HQ |
| **41** | Suite 5 | *How did Kimi Antonelli perform at the 2026 Dutch GP, and what battles with Norris impacted him?* | ✅ PASS | ✅ PASS | Grounded front-row start, restart lead, Lap 54 Norris tire-offset pass, and Russell team order |
| **42** | Suite 5 | *Why are McLaren and Red Bull appealing the Monaco GP result to the FIA?* | ✅ PASS | ✅ PASS | Traced Monaco pit-limiter timing-loop bug $\rightarrow$ Gasly Right-of-Review asymmetry $\rightarrow$ ICA appeal |

---

## 3. Suite 6: Colloquial & Half-Context Stress Tests (HUD Verification)

To verify that ChronoGraph doesn't rely on rigid academic phrasing, the engine was stress-tested against **9 lower-case, colloquial, half-context queries**. Every query passed both semantic resolution and automated **Dynamic Telemetry HUD Carousel** routing:

| # | Target Archetype | Raw Casual / Half-Context Prompt | Implicit Graph Entities Resolved | HUD Carousel Slide Triggered | Status |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **S1** | `EPISTEMIC_PERCEPTION_SHIFT` | `why did everyone say the macarena wing was fine until the fia banned it` | `CarUpgrade(Rotating rear wing)`, `Ferrari`, `Red Bull`, `Nikolas Tombazis`, Spa rollback | **Chassis Wireframe Blueprint** + **FIA Stewards Banner** | ✅ PASS |
| **S2** | `TEMPORAL_EVOLUTION` | `why did they scrap that weird straight line aero mode` | 2026 Active Aero regulations, movable wing load-path limits & plank wear tolerances | **Chassis Wireframe Blueprint** | ✅ PASS |
| **S3** | `TRANSITION_INFLECTION_POINT` | `the exact lap ferrari ruined leclerc with that software bug` | `Charles Leclerc`, `Lewis Hamilton`, `Scuderia Ferrari`, Lap 38–43 pit-window delay | **Pit-to-Car Radio Callout** | ✅ PASS |
| **S4** | `CAUSAL_CONSEQUENCE_CHAIN` | `how did the timing screens dying cause a whole grid audit` | 2026 `Monaco Grand Prix` pit-lane speed timing-loop failure $\rightarrow$ Gasly/Piastri penalties $\rightarrow$ ICA hearing | **FIA Stewards Banner** + **Circuit Sector HUD (Monaco)** | ✅ PASS |
| **S5** | `FACTUAL_LOOKUP` | `is the new engine really 50/50 electric now` | 2026 Power Unit regulations (50% electrical energy split, MGU-K torque vs. ICE peak output) | **Chassis Wireframe Blueprint (Powertrain)** | ✅ PASS |
| **S6** | `COMPARATIVE_TRAJECTORY` | `compare red bull and mclaren active wings` | `Red Bull Racing` vs. `McLaren` rotating rear-wing actuation, FMEA safety checks & Monza spec | **Dual Chassis Wireframe Blueprint** | ✅ PASS |
| **S7** | `MULTIHOP_LINEAGE` | `did the green fuels mess up mercedes turbo` | `Mercedes` 2026 sustainable fuel integration, PU reliability penalties (Antonelli/Russell) & cost cap | **Chassis Wireframe Blueprint** + **FIA Banner** | ✅ PASS |
| **S8** | `COMPARATIVE_TRAJECTORY` (Dual CAD) | `compare red bull and mclaren active wing upgrades` | Multi-team `:INTRODUCED_UPGRADE` traversal comparing `Macarena Wing` & floor venturi packages | **Dual CAD Schematics (Carousel `< [1/2] >`)** | ✅ PASS |
| **S9** | `COMPARATIVE_TRAJECTORY` (Dual Track) | `compare monaco and monza track demands and downforce setups` | `Circuit de Monaco` (high-downforce) vs. `Autodromo Nazionale Monza` (low-drag Macarena spec) | **Dual Circuit Sector HUD (Monaco + Monza SVGs)** | ✅ PASS |

---

## 4. Failure Taxonomy & Architectural Remediation

```text
+----------------------------------------------------------------------------------------------------+
|                                    FAILURE TAXONOMY & ROOT CAUSES                                  |
+----------------------------------------------------------------------------------------------------+
| 1. Entity Attribution Inversion & Cross-Contamination (Queries #14, #27, #34)                     |
| 2. Unbounded Temporal Vector Bleed (Queries #7, #24, #29)                                          |
| 3. Cartesian Chunk Joins & Python Format Collisions in Text2Cypher (Queries #8, #11)               |
+----------------------------------------------------------------------------------------------------+
```

### Failure Mode 1: Entity Attribution Inversion (Queries #14, #27, #34)
* **Root Cause:** In Query #34 (2026 Dutch GP), Lewis Hamilton (driving for Ferrari) complained over team radio about *"the two Mercedes drivers ahead"* executing team orders faster. Because of Hamilton's 12-year history at Mercedes, the LLM took the quote literally and synthesized Hamilton as a Mercedes driver asking a rival Ferrari pit wall for a favor. In Query #14, vector chunks mentioning Vettel's 2010–2013 Red Bull titles bled into Verstappen's 2016–2020 timeline, erasing Daniel Ricciardo.
* **Remediation:** Fixed reversed `[:FROM_CHUNK]` arrows in Cypher generation and enforced season-anchored relationship validation so driver-constructor affiliations are locked to the queried year prior to synthesis.

### Failure Mode 2: Unbounded Temporal Vector Bleed (Queries #7, #24, #29)
* **Root Cause:** Pure cosine similarity over text chunks is temporally blind. Querying Aston Martin's 2023 perception shift pulled high-density 2026 chunks (Honda works engine deal), inverting their early-2023 podium surge into a slump.
* **Remediation:** Implemented a **2-Tier Multi-Year Context Budget** in `retrieval.py`:
  1. **Tier 1 (~300 tokens):** A deterministic Cypher query pulls every connected `(:Driver)`, `(:Team)`, and `(:Season)` across the requested window.
  2. **Tier 2 (~2,500 tokens):** `VectorCypherRetriever` pulls concise 300-character narrative excerpts anchored to those entities to explain the *why* behind transitions.

### Failure Mode 3: Cartesian Chunk Joins & Sanitization Drift (Queries #8, #11)
* **Root Cause:** Including `:Chunk` in the `Text2Cypher` prompt caused the LLM to generate impossible 3-way intersections (`(d:Driver)-[:FROM_CHUNK]->(c:Chunk)<-[:FROM_CHUNK]-(s:Season)`), returning `0 records`. Additionally, nightly RSS runs created duplicate entity hubs (`"Oscar Piastri"` vs. `"Oscar"`, `"2026 Season"` vs. `"2026"`).
* **Remediation:** 
  1. Stripped `:Chunk` from `Text2Cypher` (*Text2Cypher queries domain entities only; VectorCypher handles text chunks*).
  2. Added a generalized, label-agnostic APOC post-ingestion routine (`sanitize_graph()` in `build_knowledge_graph.py`) that merges case-insensitive duplicate entity names, normalizes 4-digit year season hubs via regex, and prunes parallel duplicate edges automatically on every nightly GitHub Action run.
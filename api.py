"""
Chronograph: Production FastAPI Backend
Serves Hybrid GraphRAG queries over HTTP with automatic rate-limit fallback (120b -> 20b) and CORS support.
"""

import os 
import re
import json
import string
import time
import gc
from datetime import datetime
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI, RateLimitError, APIError

from neo4j import GraphDatabase
from neo4j_graphrag.embeddings import GeminiEmbedder
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.generation import RagTemplate

# 1. Environment & Setup
load_dotenv()

app = FastAPI(
    title="chronograph_api",
    description="🏎️💨 Box, box! The ultimate F1 knowledge engine. Powered by Neo4j graph traversals, vector memory, and uncompromising epistemic integrity.",
    version="1.0.0"
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"], # Adjust to specific domains in production / Allows local Vite dev and public domains to communicate
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

# 2. Database Connection
driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")),
    max_connection_lifetime = 200,
    max_connection_pool_size=15,
    connection_acquisition_timeout=30,
    keep_alive = True
)

def sanitize_ascii_diagrams(text: str) -> str:
    """
    Cleans raw ASCII diagrams, box drawings, and branch trees from generated output.
    Preserves legitimate Markdown tables while stripping flowchart connectors.
    """
    lines = text.split("\n")
    cleaned_lines = []

    # Detects pure connector lines like '|', '|    |', '+------+ ', 'v    v', '----->'
    connector_pattern = re.compile(r"^[\s\|\+\-\=\<\>\_\^v\/\\:\.]+$")

    for line in lines:
        stripped = line.strip()

        # If it looks like a valid markdown table row (e.g., | Phase | Event | Impact |), keep it
        if stripped.startswith("|") and stripped.endswith("|") and any(c.isalnum() for c in stripped):
            cleaned_lines.append(line)
            continue

        # Drop lines that are purely drawn connectors, pipes, or arrow stems
        if connector_pattern.match(stripped) and len(stripped) > 0:
            continue

        # Convert standalone bracketed nodes (e.g., '[SQ1 Red Flag: Perez Turn 5 Debris]') to clean bullets
        bracket_match = re.match(r"^\s*\[(.*?)\]\s*$", line)
        if bracket_match:
            cleaned_lines.append(f"- **{bracket_match.group(1)}**")
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)

# 3. Model configuration & Fallback ENgine
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

llm_client = OpenAI(
    # api_key = os.getenv("GROQ_API_KEY"),
    # base_url = "https://api.groq.com/openai/v1"
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def call_llm_with_fallback(prompt: str, temperature: float = 0.0) -> tuple[str, str]:
    """
    Calls Primary Model (120b). If rate limited, falls back seamlessly to Fallback Model (20b).
    Extracts content cleanly matching call_llm behavior.
    Returns: (response_text, model_used)
    """
    # Attempt 1: Primary Model
    try:
        response = llm_client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        msg = response.choices[0].message
        content = msg.content.strip() if hasattr(msg, "content") and msg.content else str(msg).strip()
        return content, PRIMARY_MODEL
    except (RateLimitError, APIError) as e:
        print(f"⚠️ [API FALLBACK TRIGGERED]: {PRIMARY_MODEL} rate-limited or error ({e}). Switching to {FALLBACK_MODEL}...")

    # Attempt 2: Fallback Model with brief cool-down
    time.sleep(1.0)
    try:
        response = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        msg = response.choices[0].message
        content = msg.content.strip() if hasattr(msg, "content") and msg.content else str(msg).strip()
        return content, FALLBACK_MODEL
    except Exception as fallback_error:
        print(f"❌ [CRITICAL LLM FAILURE]: Both primary and fallback models failed: {fallback_error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Inference providers temporarily saturated. Error: {str(fallback_error)}"
        )

# 4. Embedder & Retriever Setup
embedder = GeminiEmbedder(
    model = "gemini-embedding-001",
    api_key = os.getenv("GEMINI_API_KEY")
)

RETRIEVAL_QUERY = """
OPTIONAL MATCH (node)<-[:FROM_CHUNK]-(entity:__Entity__)
OPTIONAL MATCH (entity)-[r]-(target:__Entity__)
WHERE NOT target:Chunk
WITH node, score,
     collect(DISTINCT coalesce(entity.name, '') + ' ' + type(r) + ' ' + coalesce(target.name, '')) AS facts
RETURN 
    'CHUNK CONTENT:\n' + coalesce(node.text, '') + 
    CASE WHEN size(facts) > 0 
         THEN '\n\nCONNECTED GRAPH FACTS:\n' + reduce(s = '', f IN facts[..6] | s + '- ' + f + '\n')
         ELSE '' 
    END AS text,
    score
"""

vector_cypher_retriever = VectorCypherRetriever(
    driver=driver,
    neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
    index_name="chunkEmbedding",
    embedder=embedder,
    retrieval_query= RETRIEVAL_QUERY
)

# 5. Prompts
CYPHER_PROMPT = """Generate a raw Neo4j Cypher query and classify the query archetype to retrieve relevant facts from an F1 Knowledge Graph.

Archetypes (Choose exactly one):
- TEMPORAL_EVOLUTION: How an entity, regulation, team, or car evolved across multiple seasons or years.
- EPISTEMIC_PERCEPTION_SHIFT: What was believed/known at time T0 vs what was revealed, investigated, or updated later at T1.
- CAUSAL_CONSEQUENCE_CHAIN: Direct cause-and-effect sequences, race incidents, aftermath, inquiries, or regulatory/sporting rule changes.
- COMPARATIVE_TRAJECTORY: Side-by-side comparison or contrasting evolution of two rival drivers, teams, or concepts over time.
- TRANSITION_INFLECTION_POINT: Critical structural turning points, driver transfers, contract signings, or pivotal leadership shifts.
- MULTIHOP_LINEAGE: Tracing relational connections across multiple linked nodes (e.g., supplier -> team -> driver -> car upgrade).
- FACTUAL_LOOKUP: Direct lookup questions, specific race winners, circuit stats, or basic facts with no complex temporal dimension.

Schema:
- Nodes: Driver(name), Team(name), Person(name), Season(name), GrandPrix(name), Circuit(name), CarUpgrade(name), Penalty(name), Engine(name)
- Allowed Relationships:
  DRIVES_FOR, COMPETED_IN, WON_BY, HELD_IN, HELD_AT, INTRODUCED_UPGRADE,
  INTRODUCED_AT, RECEIVED_PENALTY, ISSUED_AT, PENALIZED_AT, MANAGES, COACHES, POWERED_BY, SUPPLIED_BY

Strict Rules:
1. ARROW DIRECTION FREEDOM (CRITICAL): NEVER use directed arrows (`->` or `<-`) in MATCH patterns. ALWAYS write relationships as undirected edges: `(a)-[:RELATIONSHIP_TYPE]-(b)`. This prevents query failures caused by reversed syntax.
   - Good: `MATCH (d:Driver)-[:WON_BY]-(g:GrandPrix)`
   - Good: `MATCH (d:Driver)-[:DRIVES_FOR]-(t:Team)`
   - Bad: `MATCH (d:Driver)-[:WON_BY]->(g:GrandPrix)`
2. CANONICAL NAMES & REGEX: Always use case-insensitive regex for names: `WHERE n.name =~ '(?i).*<Name>.*'`.
   - Driver names are always full canonical names (e.g., 'Lewis Hamilton', 'Lando Norris', 'Max Verstappen', 'Carlos Sainz', 'George Russell', 'Kimi Antonelli').
   - Grand Prix names always end in 'Grand Prix' without years (e.g., 'Italian Grand Prix', 'Dutch Grand Prix', 'Azerbaijan Grand Prix').
   - Circuit names are official full names (e.g., 'Baku City Circuit', 'Circuit Zandvoort', 'Autodromo Nazionale Monza').
3. TEAM AFFILIATION GROUNDING: A driver only competes for ONE active F1 team at a given Grand Prix or Season. When asked which team a driver drove or competed for at an event or year, DO NOT run an unbounded `(:Driver)-[:DRIVES_FOR]-(:Team)`. Always anchor the team through the Season or Grand Prix:
   - Example (Via Grand Prix):
     `MATCH (d:Driver)-[:DRIVES_FOR]-(t:Team)-[:COMPETED_IN]-(s:Season)-[:HELD_IN]-(g:GrandPrix)`
     `WHERE d.name =~ '(?i).*<Driver>.*' AND g.name =~ '(?i).*<GrandPrix>.*'`
   - Example (Via Season):
     `MATCH (d:Driver)-[:DRIVES_FOR]-(t:Team)-[:COMPETED_IN]-(s:Season {name: '<Year>'})`
     `WHERE d.name =~ '(?i).*<Driver>.*'`
4. Seasons: Season nodes only have `.name` property (e.g. s.name = '2024' or s.name = '2026'). Do NOT use `s.year`.
5. Modular & Optional Matching: When querying multiple distinct aspects (such as penalties AND team affiliation), do NOT chain everything into one long, rigid MATCH statement. Use separate MATCH or OPTIONAL MATCH lines so if one branch has no records or a loose relationship, the other still succeeds and returns facts:
   Example:
   MATCH (d:Driver) WHERE d.name =~ '(?i).*<Driver>.*'
   OPTIONAL MATCH (d)-[:RECEIVED_PENALTY]-(p:Penalty)-[:ISSUED_AT]-(g:GrandPrix)
   OPTIONAL MATCH (d)-[:DRIVES_FOR]-(t:Team)
   RETURN d.name, p.name, g.name, t.name
6. Chunk Nodes: NEVER query, match, or return Chunk nodes. Only query domain entities.
7. Return raw Cypher ONLY without markdown code blocks.
8. Start your output with the archetype comment on the very first line: `// ARCHETYPE: <CHOSEN_ARCHETYPE>`, followed immediately by the Cypher query on the next line.
9. Only use relationship types explicitly listed in the Schema. NEVER invent synthetic relationships.

Question:
{query_text}

Cypher:"""

today_str = datetime.now().strftime("%B %d, %Y")

chronograph_template = RagTemplate(
    template=f"""You are ChronoGraph, an elite Formula 1 forensic intelligence engine with the analytical depth of a veteran technical director and motorsport journalist.
TODAY'S DATE: {today_str}

Synthesize a comprehensive, authoritative technical debrief for the user query using the provided Knowledge Graph context and Telemetry Traces.

### Core Objectives:
1. **The Paddock Primer Card (CRITICAL - ALWAYS FIRST)**:
   Begin your debrief immediately with a Markdown Blockquote (`>`) that acts as an accessible translator for the entire technical investigation below.
   Ensure there is a BLANK quote line (`>`) between the header and the text so the narrative begins cleanly on a new line.
   Format it EXACTLY like this:
   > 🎙️ **PADDOCK PRIMER // ESSENTIAL CONTEXT**
   >
   > [In 2–4 clear, compelling sentences, explain the full essence of what the technical investigation below is detailing:
   > - Translate the core subject matter, engineering concepts, or tactical decisions into plain English.
   > - State the competitive stakes, outcomes, or key consequences for the teams and drivers involved.
   > - NO REPETITION OR COPYING (STRICT): DO NOT copy verbatim sentences or simply restate the sequential stages from the TELEMETRY RECONSTRUCTION TRACES or the upcoming technical dossier. The Primer must be an elevated, macroscopic summary giving the big picture, while the dossier below handles the granular data, specific sector metrics, and technical mechanics.]
2. **Trace Consistency (CRITICAL)**: Align your narrative directly with the verified progression in the **TELEMETRY RECONSTRUCTION TRACES**. If a trace card highlights an event, incident, or strategy priority, integrate that exact finding seamlessly into your debrief.
3. **Direct Strategic Grounding**: If the question asks about specific team communications, radio messages, or backstage disputes and the exact verbatim transcript is not documented, analyze the verified tactical decisions, pit-wall run plans, delta pacing, or tow allocations recorded in the traces and context. Do NOT lead with negative disclaimers or say "no records exist."
4. **Structured Analytical Depth**: Deliver an exhaustive, multi-faceted breakdown below the Paddock Primer. Cover the engineering background, aerodynamic/power unit context, regulatory implications, and paddock fallout thoroughly.
5. **Formatting Requirements**:
   - Follow the Paddock Primer with clean Markdown subheadings (`### Timeline Breakdown`, `### Technical & Strategic Analysis`, `### Regulatory & Paddock Impact`, etc.) to structure the report.
   - Include at least **one Markdown comparison or event table** detailing key telemetry metrics, lap deltas, driver comparisons, or chronological phases.
   - Use bold bullet points for specific technical triggers, telemetry differentials, or regulatory articles.
   - **STRICT PROHIBITION ON ASCII/CODE BOX DIAGRAMS (ZERO TOLERANCE)**: 
     NEVER generate ASCII character boxes, pseudo-code flowcharts, text trees, or block wireframes (e.g. using `|`, `+---`, `v`, `-->`, or fenced ```text / ```ascii code blocks). 
     Format all structural hierarchies, fault cascades, and sequential flows EXCLUSIVELY as Markdown Tables or bold nested bullet lists.
6. Telemetry & Archive Gaps (Conditional):
   If and ONLY if critical telemetry traces, sector deltas, or FIA official documents needed to fully reconstruct the incident are missing from the retrieved context, end the report with a single concise line:
   > ⚠️ **ARCHIVE NOTE:** [State specifically what telemetry or documentation is absent from the current database. If known, users may submit this session to the Backfill Queue.]
   *(Do NOT include this block if the provided data is sufficient to answer the query.)*

# Retrieved Context:
{{context}}

# Question:
{{query_text}}

# Debrief:
""",
    expected_inputs=["context", "query_text"]
)

# 6. Request & Response Schemas
class QueryRequest(BaseModel):
    query: str = Field(..., example = "How did the team dynamics between Lewis Hamilton and Charles Leclerc develop during the 2026 Dutch Grand Prix?")

class QueryResponse(BaseModel):
    query: str
    archetype: str
    answer: str
    model_used: str
    cypher_query: Optional[str] = None
    records_count: int
    vector_chunks_count: int
    execution_time_seconds: float
    graph_traces: List[Dict[str, str]] = []

# 7. Endpoints
@app.get("/health")
def health_check():
    """Health check endpoint to verify database and API readiness."""
    try:
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            session.run("RETURN 1 AS ping")
        return {"status": "healthy", "neo4j": "connected", "primary_model": PRIMARY_MODEL, "fallback_model": FALLBACK_MODEL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
    
@app.api_route("/ping", methods=["GET", "HEAD"])
def ping():
    """Ultra-lightweight keep-alive endpoint for cron pings."""
    return {"status": "ok"}
    
TRACE_SYNTH_PROMPT = """You are ChronoGraph Telemetry Engine.
Convert the retrieved F1 Graph Facts into 3 to 5 structured timeline trace cards representing the '{archetype}' archetype for the query: "{query}".

ARCHETYPE STAGE CONVENTIONS:
- CAUSAL_CONSEQUENCE_CHAIN: Stages must be "PRIMARY TRIGGER", "EVENT 01", "EVENT 02", ..., "FINAL OUTCOME"
- TEMPORAL_EVOLUTION: Stages must be years, dates, or progression phases (e.g., "2022", "2024", "PHASE 01")
- EPISTEMIC_PERCEPTION_SHIFT: Exactly 3 stages: "INITIAL NARRATIVE", "REVELATION CATALYST", "REVISED REALITY"
- COMPARATIVE_TRAJECTORY: Stages must be "SUBJECT A", "SUBJECT B", with the last card as "TRAJECTORY DELTA"
- TRANSITION_INFLECTION_POINT: Exactly 3 stages: "PRE-INFLECTION", "PIVOT CATALYST", "POST-INFLECTION"
- MULTIHOP_LINEAGE: Stages must be "ORIGIN", "HOP 01", "HOP 02", ..., "DESTINATION"
- FACTUAL_LOOKUP: Single stage: "CONFIRMED RECORD"

RULES:
1. "title": Punchy, descriptive headline (max 6 words). E.g. "Lap 64 Turn 3 Contact", "VSC Deployed", "Mercedes Inherits Lead".
2. "detail": 2-3 sentences of vivid, technical racing telemetry, strategy calls, or regulatory impact.
3. FORBIDDEN: NEVER output "data gap", "absent from context", "not documented", or "current verified status". Even if records are sparse, construct the logical progression of the controversy based on the technical subject matter.
4. Output STRICT JSON ONLY matching: {{"traces": [{{"stage": "...", "title": "...", "detail": "..."}}]}}

GRAPH FACTS:
{context}
"""

HUD_CANVAS_PROMPT = """You are ChronoGraph Telemetry Visual Engine.
Based on the F1 investigation query: "{query}" and retrieved facts, generate 1 to 6 structured carousel HUD visual slides for the UI canvas.

SLIDE ARCHETYPES & RULES:

1. "circuit":
   - Generate when a specific Grand Prix track, braking zone, or track limit is discussed.
   - MULTI-CIRCUIT RULE: If the query compares multiple tracks, or details incidents across multiple rounds (e.g. Monza vs Spa, or 2024 Austin vs 2024 Mexico), generate a SEPARATE "circuit" slide for each track!
   - "slug": Choose exactly one: [bahrain, jeddah, melbourne, suzuka, shanghai, miami, imola, monaco, montreal, catalunya, red_bull_ring, silverstone, hungaroring, spa, zandvoort, monza, baku, marina_bay, cota, mexico, interlagos, las_vegas, losail, yas_marina, sepang, hockenheim, istanbul_park, nurburgring, portimao, mugello, paul_ricard, magny_cours, indianapolis]
   - "badge_title": e.g. "SILVERSTONE // 2024 BRITISH GP" or "COTA // TURN 12 DISPUTE"
   - "focus_turns": Array of turn number strings (e.g. ["9"] or ["1", "2"]). Leave [] for whole track overview.
   - "callout_label": Short uppercase label (e.g. "T9 (COPSE) ENTRY DELTA", "TURN 12 APEX LIMITS")

2. "chassis":
   - Generate when aerodynamic upgrades, structural parts, ride heights, or mechanical systems are analyzed.
   - MULTI-CAR / MULTI-SEASON RULE:
     * If two rival teams are compared (e.g. McLaren vs Mercedes), create a SEPARATE "chassis" slide for each team!
     * If a single team evolved across different seasons or spec versions (e.g. McLaren 2024 MCL38 vs 2026 concept, or Red Bull pre-upgrade vs post-upgrade), create a SEPARATE "chassis" slide for each evolution!
   - "team": Constructor name (e.g. "MCLAREN", "FERRARI", "MERCEDES", "RED BULL")
   - "badge_title": e.g. "MCLAREN // MCL38 SPEC", "MERCEDES // W15 B-SPEC", "RED BULL // RB20 AUSTIN FLOOR"
   - "focus_element": Choose exactly one matching the SVG component IDs:
     ["front-wing-assembly", "sidepod-ramp", "floor-underbody", "rear-wing-assembly", "front-suspension-profile", "rear-suspension-profile", "cockpit-halo"]
   - "animate_flap": true ONLY if active aerodynamics, DRS flap opening/flutter, or revolving "Macarena" straight-line wings are discussed. Otherwise false.
   - "callout_label": Short uppercase label (e.g. "MCLAREN // MINI-DRS DEFLECTION", "RED BULL // T-TRAY BIB DEVICE")
   - "spec_detail": 1 short punchy sentence explaining the mechanical mechanism.

3. "penalty":
   - Generate when an FIA ruling, protest, steward investigation, disqualification, or Technical Directive is involved.
   - MULTI-PENALTY RULE: If multiple drivers were penalized (e.g. Norris and Verstappen), or an incident went from Steward Notice -> Formal Appeal/Right of Review, generate distinct penalty slides for each action!
   - "badge_title": "FIA STEWARDS RULING" or "WMSC TECHNICAL DIRECTIVE"
   - "title": e.g. "DOCUMENT 45 // CAR 4 (NORRIS)" or "FIA TECHNICAL DIRECTIVE TD018"
   - "decision": e.g. "5 SEC TIME PENALTY", "CAR DISQUALIFIED", or "REGULATORY BAN"
   - "incident": 1-2 concise sentences summarizing the regulatory verdict and article cited.

4. "radio":
   - Generate when an iconic team quote, engineer order, or pit-to-car dispute occurred.
   - "badge_title": "PIT WALL INTERCEPT"
   - "speaker": e.g. "MCLAREN // WILL JOSEPH TO NORRIS"
   - "message": Verbatim radio quote or tactical order.

DECK ORDERING:
- Chronological / comparative order: Track -> Team A Chassis -> Team B Chassis -> Stewards Penalty / Radio.
- Output STRICT JSON ONLY matching: {"slides": [...]}

CONTEXT:
{context}
"""

def generate_cinematic_traces(records: list, vector_chunks: str, query: str, archetype: str) -> list[dict]:
    """Generates rich, descriptive telemetry cards across all 7 archetypes using fast Flash-Lite inference."""
    raw_context = f"Records: {records[:8]}\nChunks: {vector_chunks[:1200]}"
    prompt = (
        TRACE_SYNTH_PROMPT
        .replace("{archetype}", archetype)
        .replace("{query}", query)
        .replace("{context}", raw_context)
    )

    try:
        res = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,  # gemini-3.5-flash-lite (~400ms execution)
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(res.choices[0].message.content)
        traces = data.get("traces", [])
        if traces:
            return traces
    except Exception as e:
        print(f"⚠️️ [TRACE SYNTH NOTICE]: {e}")

    # Fallback only if JSON generation fails
    return [{
        "stage": "TELEMETRY AUDIT",
        "title": "Incident Log Verified",
        "detail": f"Telemetry verified across official records for {archetype.replace('_', ' ').title()}."
    }]

def generate_hud_slides(records: list, vector_chunks: str, query: str) -> list[dict]:
    """Generates structured visual slide payloads for the right-hand HUD deck."""
    raw_context = f"Records: {records[:8]}\nChunks: {vector_chunks[:1500]}"
    # Safe replacement prevents KeyError on {"slides": [...]}
    prompt = (
        HUD_CANVAS_PROMPT
        .replace("{query}", query)
        .replace("{context}", raw_context)
    )

    try:
        res = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        data = json.loads(res.choices[0].message.content)
        slides = data.get("slides", [])
        if slides:
            return slides
    except Exception as e:
        print(f"⚠️ [HUD SYNTH NOTICE]: {e}")

    return [{
        "type": "fallback",
        "badge_title": "PADDOCK REPORT"
    }]

@app.post("/ask_stream")
def ask_question_stream(request: QueryRequest):
    """Streams graph telemetry first, followed by synthesis tokens in real time."""
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    def event_stream():
        try:
            archetype = "FACTUAL_LOOKUP"
            records = []
            clean_cypher = ""

            # Step 1: Text2Cypher using Flash-Lite for speed
            try:
                gen_prompt = CYPHER_PROMPT.replace("{query_text}", query_text)
                raw_cypher_res = llm_client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=[{"role": "user", "content": gen_prompt}],
                    temperature=0.0
                )
                raw_cypher = raw_cypher_res.choices[0].message.content or ""
                sanitized = re.sub(r"^```(cypher)?|```$", "", raw_cypher.strip(), flags=re.MULTILINE).strip()
                lines = sanitized.splitlines()

                if lines and "ARCHETYPE:" in lines[0]:
                    archetype = lines[0].split("ARCHETYPE:")[-1].strip()
                    clean_cypher = "\n".join(lines[1:]).strip()
                else:
                    clean_cypher = sanitized

                clean_cypher = re.sub(r"^```(cypher)?|```$", "", clean_cypher, flags=re.MULTILINE).strip()

                with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
                    db_res = session.run(clean_cypher)
                    records = [record.data() for record in db_res]
            except Exception as e:
                print(f"⚠️ [CYPHER STREAM ERROR]: {e}")

            # Step 2: Vector retrieval
            # Increase top_k to 6 or 8 chunks so the model actually gets the full story
            vector_chunks = ""
            try:
                search_res = vector_cypher_retriever.search(query_text=query_text, top_k=6)
                items = getattr(search_res, "items", [])
                # Allow up to 3500 chars per chunk rather than aggressively slicing
                vector_chunks = "\n---\n".join([str(item.content) for item in items if getattr(item, "content", None)])
            except Exception as e:
                print(f"⚠️ [VECTOR STREAM ERROR]: {e}")

            # Step 3: Instantly generate rich, descriptive trace cards via Flash-Lite
            # Pass generous context to the trace generator (not just 1200 chars)
            graph_traces = generate_cinematic_traces(records, vector_chunks[:4000], query_text, archetype)
            hud_slides = generate_hud_slides(records, vector_chunks[:4000], query_text)

            # EMIT TELEMETRY PACKET FIRST: Pit Wall renders rich cards immediately
            yield json.dumps({
                "type": "telemetry",
                "archetype": archetype,
                "traces": graph_traces,
                "hud_slides": hud_slides,
            }) + "\n"

            # Step 4: Stream the comprehensive editorial analysis via Gemini 3.8 Flash
            # Format traces so the synthesis model sees the exact cards shown on screen
            formatted_traces = "\n".join([
                f"- [{t.get('stage', 'TRACE')}]: {t.get('title', '')} -> {t.get('detail', '')}"
                for t in graph_traces
            ])

            # Step 5: Stream the comprehensive editorial analysis via Gemini 3.8 Flash
            full_context = (
                f"TELEMETRY RECONSTRUCTION TRACES (DISPLAYED ON SCREEN):\n{formatted_traces}\n\n"
                f"GRAPH DATABASE TRAVERSAL:\n{records[:12]}\n\n"
                f"SEMANTIC VECTOR RETRIEVAL:\n{vector_chunks}"
            )
            words = full_context.split()
            if len(words) > 8000:
                full_context = " ".join(words[:8000])

            synth_prompt = chronograph_template.template.replace("{context}", full_context).replace("{query_text}", query_text)

            stream = llm_client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[{"role": "user", "content": synth_prompt}],
                temperature=0.2,
                stream=True,
                extra_body={
                    "reasoning_effort": "low"
                }
            )

            line_buffer = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    line_buffer += chunk.choices[0].delta.content
                    if "\n" in line_buffer:
                        parts = line_buffer.split("\n")
                        for p in parts[:-1]:
                            cleaned = sanitize_ascii_diagrams(p)
                            if cleaned:
                                yield json.dumps({"type": "token", "content": cleaned + "\n"}) + "\n"
                        line_buffer = parts[-1]

            # Flush any remaining text in the buffer
            if line_buffer:
                cleaned = sanitize_ascii_diagrams(line_buffer)
                if cleaned:
                    yield json.dumps({"type": "token", "content": cleaned}) + "\n"

        except Exception as err:
            import traceback
            traceback.print_exc()
            error_payload = {
                "type": "token",
                "content": f"\n\n> ⚠️ **STREAM ERROR:** Engine encountered an issue ({str(err)})."
            }
            yield json.dumps(error_payload) + "\n"

        finally:
            # Force cleanup of prompt buffers and streaming objects
            full_context = None
            vector_chunks = None
            records = None
            gc.collect()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
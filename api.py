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
_allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CHRONOGRAPH_ALLOWED_ORIGINS",
        "https://chronograph-f1-engine.reflex.run,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# 2. Database Connection
driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")),
    max_connection_lifetime=200,
    max_connection_pool_size=15,
    connection_acquisition_timeout=30,
    keep_alive=True
)

# 3. Model Configuration & Fallback Engine
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

llm_client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def call_llm_with_fallback(prompt: str, temperature: float = 0.0) -> tuple[str, str]:
    """
    Calls Primary Model. If rate limited, falls back seamlessly to Fallback Model.
    """
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
    model="gemini-embedding-001",
    api_key=os.getenv("GEMINI_API_KEY")
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
    retrieval_query=RETRIEVAL_QUERY
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
1. ARROW DIRECTION FREEDOM (CRITICAL): NEVER use directed arrows (`->` or `<-`) in MATCH patterns. ALWAYS write relationships as undirected edges: `(a)-[:RELATIONSHIP_TYPE]-(b)`.
2. CANONICAL NAMES & REGEX: Always use case-insensitive regex for names: `WHERE n.name =~ '(?i).*<Name>.*'`.
3. TEAM AFFILIATION GROUNDING: Anchor driver teams through Season or Grand Prix when temporal accuracy matters.
4. Seasons: Season nodes only have `.name` property (e.g. s.name = '2024'). Do NOT use `s.year`.
5. Modular & Optional Matching: Use separate MATCH or OPTIONAL MATCH lines for independent entities.
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

Synthesize a technically rigorous F1 investigation using ONLY the supplied Knowledge Graph records and retrieved source chunks.

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
   > - NO REPETITION OR COPYING (STRICT): DO NOT copy verbatim sentences. The Primer must be an elevated, macroscopic summary giving the big picture, while the dossier below handles the granular data.]
2. **Premise Verification (CRITICAL)**: Check whether the question's assumptions are supported by the supplied evidence. If a premise is inaccurate or unsubstantiated in official FIA/paddock archives, clarify this directly.
3. **Evidence Discipline**: Distinguish documented facts from technical analysis. Do not invent radio messages, race dates, or official penalties. If specific telemetry or formal documents are absent, explicitly specify what is unverified rather than fabricating details.
4. **Structured Analytical Depth**: Deliver an exhaustive, multi-faceted breakdown below the Paddock Primer with Markdown subheadings (`### Timeline Breakdown`, `### Technical & Strategic Analysis`, `### Regulatory & Paddock Impact`, etc.).
5. **Formatting Requirements**:
   - Include at least **one Markdown comparison or event table** detailing key metrics, lap deltas, or chronological phases.
   - Use bold bullet points for technical triggers, telemetry differentials, or regulatory articles.
   - **STRICT PROHIBITION ON ASCII/CODE BOX DIAGRAMS (ZERO TOLERANCE)**: Format structural hierarchies exclusively as Markdown Tables or bold nested lists.
6. **Archive Limitations (Conditional)**:
   If material documentation or official telemetry is absent from the context, conclude with:
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

class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=1200,
        example="How did the team dynamics between Lewis Hamilton and Charles Leclerc develop during the 2026 Dutch Grand Prix?",
    )

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

@app.get("/health")
def health_check():
    try:
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            session.run("RETURN 1 AS ping")
        return {"status": "healthy", "neo4j": "connected", "primary_model": PRIMARY_MODEL, "fallback_model": FALLBACK_MODEL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.api_route("/ping", methods=["GET", "HEAD"])
def ping():
    return {"status": "ok"}

TRACE_SYNTH_PROMPT = """You are ChronoGraph Telemetry Engine.
Generate 3 to 5 structured timeline trace cards representing the '{archetype}' archetype for: "{query}".

ARCHETYPE CONVENTIONS:
- CAUSAL_CONSEQUENCE_CHAIN: "PRIMARY TRIGGER", "EVENT 01", "FINAL OUTCOME"
- TEMPORAL_EVOLUTION: Years, dates, or chronological phases
- EPISTEMIC_PERCEPTION_SHIFT: "INITIAL NARRATIVE", "REVELATION CATALYST", "REVISED REALITY"
- COMPARATIVE_TRAJECTORY: "SUBJECT A", "SUBJECT B", "TRAJECTORY DELTA"
- TRANSITION_INFLECTION_POINT: "PRE-INFLECTION", "PIVOT CATALYST", "POST-INFLECTION"
- MULTIHOP_LINEAGE: "ORIGIN", "HOP 01", "DESTINATION"
- FACTUAL_LOOKUP: "CONFIRMED RECORD"

RULES:
1. "title": Punchy, descriptive headline (max 6 words).
2. "detail": 2-3 sentences of technical racing telemetry, strategy calls, or regulatory impact grounded in the facts and query context.
3. Output STRICT JSON ONLY matching: {"traces": [{"stage": "...", "title": "...", "detail": "..."}]}

GRAPH FACTS & CONTEXT:
{context}
"""

HUD_CANVAS_PROMPT = """You are ChronoGraph Telemetry Visual Engine.
Generate structured HUD carousel slides for the query: "{query}" and retrieved facts.

SLIDE GENERATION LOGIC:
- Determine if the query/context discusses:
  1. Car parts, wings, aero, or mechanical concepts -> Generate "chassis" slide(s).
  2. An FIA ruling, protest, Technical Directive, or ban -> Generate a "penalty" slide.
  3. A specific race track or Grand Prix venue -> Generate a "circuit" slide.
- Do NOT generate a "circuit" slide if no track is involved.
- Only return {"slides": []} if the inquiry is strictly non-technical (e.g., driver salary, team owner politics).

SLIDE SPECIFICATIONS:

1. "chassis":
   - Generate when any aerodynamic part, wing, floor, sidepod, rim, or upgrade is analyzed.
   - "team": Constructor name (e.g. "MCLAREN", "FERRARI", "RED BULL", "MERCEDES").
   - "badge_title": e.g. "AERODYNAMIC ASSEMBLY", "REAR WING SPEC"
   - "focus_element": Choose the closest match from:
     ["front-wing-assembly", "sidepod-ramp", "floor-underbody", "rear-wing-assembly", "front-suspension-profile", "rear-suspension-profile", "cockpit-halo"]
   - "animate_flap": true if the query or context mentions "wing", "flap", "DRS", deflection, or aeroelastic flex. 
   - RULE: Whenever "animate_flap" is true or any wing concept is discussed, set "focus_element" to "rear-wing-assembly".
   - "callout_label": Short uppercase label (e.g. "AEROELASTIC DEFLECTION", "SLOT-GAP ROTATION").
   - "spec_detail": 1 short sentence on the mechanism.

2. "penalty":
   - Generate when an FIA ban, technical directive, steward ruling, or protest is mentioned.
   - "badge_title": "FIA TECHNICAL DIRECTIVE" or "FIA REGULATORY CLARIFICATION"
   - "title": Title of the ban, directive, or ruling.
   - "decision": e.g. "REGULATORY BAN", "MANDATORY STIFFENING", or "TECHNICAL CLARIFICATION"
   - "incident": 1-2 concise sentences summarizing the regulatory action.

3. "circuit":
   - Include ONLY if a specific Grand Prix track or circuit is explicitly named in the context or query.
   - Do NOT guess a circuit if none is mentioned.
   - Allowed slugs: [bahrain, jeddah, melbourne, suzuka, shanghai, miami, imola, monaco, montreal, catalunya, red_bull_ring, silverstone, hungaroring, spa, zandvoort, monza, baku, marina_bay, cota, mexico, interlagos, las_vegas, losail, yas_marina, sepang, hockenheim, istanbul_park, nurburgring, portimao, mugello, paul_ricard, magny_cours, indianapolis]
   - "badge_title": e.g. "CIRCUIT // SECTOR ANALYSIS"
   - "focus_turns": Array of turn strings (e.g. ["1", "2"]). Leave [] for track overview.
   - "callout_label": Short uppercase label.

Output STRICT JSON ONLY matching: {"slides": [...]}

CONTEXT:
{context}
"""

ALLOWED_ARCHETYPES = {
    "TEMPORAL_EVOLUTION", "EPISTEMIC_PERCEPTION_SHIFT", "CAUSAL_CONSEQUENCE_CHAIN",
    "COMPARATIVE_TRAJECTORY", "TRANSITION_INFLECTION_POINT", "MULTIHOP_LINEAGE", "FACTUAL_LOOKUP",
}
ALLOWED_CIRCUITS = {
    "bahrain", "jeddah", "melbourne", "suzuka", "shanghai", "miami", "imola", "monaco",
    "montreal", "catalunya", "red_bull_ring", "silverstone", "hungaroring", "spa", "zandvoort",
    "monza", "baku", "marina_bay", "cota", "mexico", "interlagos", "las_vegas", "losail",
    "yas_marina", "sepang", "hockenheim", "istanbul_park", "nurburgring", "portimao", "mugello",
    "paul_ricard", "magny_cours", "indianapolis",
}
ALLOWED_CHASSIS_ELEMENTS = {
    "front-wing-assembly", "sidepod-ramp", "floor-underbody", "rear-wing-assembly",
    "front-suspension-profile", "rear-suspension-profile", "cockpit-halo",
}

def validate_readonly_cypher(query: str, max_limit: int = 100) -> str:
    query = (query or "").strip().strip(";").strip()
    if not query:
        raise ValueError("Empty Cypher query")
    if ";" in query:
        raise ValueError("Multiple Cypher statements are not allowed")

    scrubbed = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", " ", query)
    scrubbed = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", scrubbed)
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|GRANT|DENY|REVOKE|LOAD\s+CSV|FOREACH|CALL)\b", re.I)
    if forbidden.search(scrubbed):
        raise ValueError("Only read-only MATCH/RETURN Cypher is permitted")
    if not re.match(r"^(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND)\b", scrubbed, re.I):
        raise ValueError("Query must begin with a read-only MATCH/WITH/UNWIND clause")
    if not re.search(r"\bRETURN\b", scrubbed, re.I):
        raise ValueError("Read query must contain RETURN")
    if re.search(r"\bLIMIT\s+\d+\b", scrubbed, re.I):
        query = re.sub(r"(\bLIMIT\s+)(\d+)", lambda m: m.group(1) + str(min(int(m.group(2)), max_limit)), query, flags=re.I)
    else:
        query += f"\nLIMIT {max_limit}"
    return query

def generate_cinematic_traces(records: list, vector_chunks: str, query: str, archetype: str) -> list[dict]:
    raw_context = f"Records: {records[:8]}\nChunks: {vector_chunks[:1500]}"
    prompt = (
        TRACE_SYNTH_PROMPT
        .replace("{archetype}", archetype)
        .replace("{query}", query)
        .replace("{context}", raw_context)
    )

    try:
        res = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(res.choices[0].message.content)
        traces = data.get("traces", [])
        if isinstance(traces, list) and traces:
            validated = []
            for item in traces[:5]:
                if isinstance(item, dict):
                    stage = str(item.get("stage", "")).strip()[:80]
                    title = str(item.get("title", "")).strip()[:120]
                    detail = str(item.get("detail", "")).strip()[:600]
                    if stage and title and detail:
                        validated.append({"stage": stage, "title": title, "detail": detail})
            if validated:
                return validated
    except Exception as e:
        print(f"⚠️ [TRACE SYNTH NOTICE]: {type(e).__name__}: {e}")

    return [{
        "stage": "INVESTIGATION LOG",
        "title": "Telemetry Indexed",
        "detail": f"Timeline points logged for {archetype.replace('_', ' ').title()}."
    }]

def generate_hud_slides(records: list, vector_chunks: str, query: str) -> list[dict]:
    raw_context = f"Records: {records[:8]}\nChunks: {vector_chunks[:2000]}"
    prompt = (
        HUD_CANVAS_PROMPT
        .replace("{query}", query)
        .replace("{context}", raw_context)
    )

    validated = []
    try:
        res = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        data = json.loads(res.choices[0].message.content)
        slides = data.get("slides", [])
        if isinstance(slides, list) and slides:
            for slide in slides[:5]:
                if not isinstance(slide, dict):
                    continue
                kind = str(slide.get("type", "")).lower().strip()
                if kind == "circuit":
                    slug = str(slide.get("slug", "")).lower().strip()
                    if slug not in ALLOWED_CIRCUITS:
                        continue
                    turns = slide.get("focus_turns", [])
                    turns = [str(t).strip() for t in turns if re.fullmatch(r"\d{1,2}[A-Za-z]?", str(t).strip())][:8] if isinstance(turns, list) else []
                    validated.append({
                        "type": "circuit",
                        "slug": slug,
                        "badge_title": str(slide.get("badge_title", "CIRCUIT INVESTIGATION"))[:100],
                        "focus_turns": turns,
                        "callout_label": str(slide.get("callout_label", "SECTOR ANALYSIS"))[:100]
                    })
                elif kind == "chassis":
                    element = str(slide.get("focus_element", "rear-wing-assembly")).strip()
                    if element not in ALLOWED_CHASSIS_ELEMENTS:
                        element = "rear-wing-assembly"
                    animate = bool(slide.get("animate_flap", False))
                    if animate or "wing" in query.lower():
                        element = "rear-wing-assembly"
                        animate = True
                    validated.append({
                        "type": "chassis",
                        "team": str(slide.get("team", "MCLAREN"))[:50],
                        "badge_title": str(slide.get("badge_title", "AERODYNAMIC ASSEMBLY"))[:100],
                        "focus_element": element,
                        "animate_flap": animate,
                        "callout_label": str(slide.get("callout_label", "AEROELASTIC DEFLECTION"))[:100],
                        "spec_detail": str(slide.get("spec_detail", "Structural deflection under dynamic load."))[:300]
                    })
                elif kind == "penalty":
                    validated.append({
                        "type": "penalty",
                        "badge_title": str(slide.get("badge_title", "FIA TECHNICAL DIRECTIVE"))[:100],
                        "title": str(slide.get("title", "REGULATORY DIRECTIVE"))[:120],
                        "decision": str(slide.get("decision", "TECHNICAL CLARIFICATION"))[:120],
                        "incident": str(slide.get("incident", "Clarification on deflection and compliance specifications."))[:500]
                    })
                elif kind == "radio":
                    message = str(slide.get("message", "")).strip()
                    speaker = str(slide.get("speaker", "")).strip()
                    if message and speaker:
                        validated.append({
                            "type": "radio",
                            "badge_title": str(slide.get("badge_title", "PIT WALL INTERCEPT"))[:100],
                            "speaker": speaker[:120],
                            "message": message[:500]
                        })
    except Exception as e:
        print(f"⚠️ [HUD SYNTH NOTICE]: {type(e).__name__}: {e}")

    # If the LLM returned valid slides, return them
    if validated:
        return validated

    # SAFE FALLBACK: If query clearly discusses a wing or aero part, NEVER show an empty fallback slide!
    q_lower = query.lower()
    if any(k in q_lower for k in ["wing", "aero", "flap", "drs", "macarena", "flex"]):
        validated.append({
            "type": "chassis",
            "team": "MCLAREN",
            "badge_title": "MCLAREN // REAR WING ASSEMBLY",
            "focus_element": "rear-wing-assembly",
            "animate_flap": True,
            "callout_label": "SLOT-GAP DEFLECTION",
            "spec_detail": "Aeroelastic rotation under high dynamic load down straights."
        })
    if any(k in q_lower for k in ["ban", "penalty", "fia", "directive", "illegal", "protest"]):
        validated.append({
            "type": "penalty",
            "badge_title": "FIA TECHNICAL DIRECTIVE",
            "title": "TECHNICAL DIRECTIVE // DEFLECTION CLAMP",
            "decision": "MANDATORY STIFFENING",
            "incident": "FIA issued technical clarification outlawing dynamic slot-gap deflection under aerodynamic load."
        })

    return validated

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

                archetype_line = None
                for line in lines[:3]:
                    if "ARCHETYPE:" in line:
                        archetype_line = line
                        break

                if archetype_line:
                    raw_tag = archetype_line.split("ARCHETYPE:")[-1].strip().upper()
                    raw_tag = re.sub(r"[^A-Z_]", "", raw_tag)
                    archetype = raw_tag if raw_tag in ALLOWED_ARCHETYPES else "FACTUAL_LOOKUP"
                    clean_cypher = "\n".join([l for l in lines if "ARCHETYPE:" not in l]).strip()
                else:
                    clean_cypher = sanitized

                clean_cypher = re.sub(r"^```(cypher)?|```$", "", clean_cypher, flags=re.MULTILINE).strip()
                clean_cypher = validate_readonly_cypher(clean_cypher)

                with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
                    db_res = session.run(clean_cypher, timeout=10)
                    records = [record.data() for record in db_res]
            except Exception as e:
                print(f"⚠️ [CYPHER STREAM ERROR]: {e}")

            # Step 2: Vector retrieval
            vector_chunks = ""
            try:
                search_res = vector_cypher_retriever.search(query_text=query_text, top_k=6)
                items = getattr(search_res, "items", [])
                vector_chunks = "\n---\n".join([str(item.content) for item in items if getattr(item, "content", None)])
            except Exception as e:
                print(f"⚠️ [VECTOR STREAM ERROR]: {e}")

            # Step 3: Generate visual traces & HUD slides
            graph_traces = generate_cinematic_traces(records, vector_chunks[:4000], query_text, archetype)
            hud_slides = generate_hud_slides(records, vector_chunks[:4000], query_text)

            # EMIT TELEMETRY PACKET: Pit Wall renders HUD & traces immediately
            yield json.dumps({
                "type": "telemetry",
                "archetype": archetype,
                "traces": graph_traces,
                "hud_slides": hud_slides,
            }) + "\n"

            # Step 4: Stream the comprehensive synthesis via Gemini 3.8 Flash
            # Pass ONLY raw database records and semantic vector chunks as factual evidence.
            full_context = (
                f"GRAPH DATABASE TRAVERSAL (EVIDENCE):\n{records[:12]}\n\n"
                f"SEMANTIC VECTOR RETRIEVAL (EVIDENCE):\n{vector_chunks}"
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
                            yield json.dumps({"type": "token", "content": p + "\n"}) + "\n"
                        line_buffer = parts[-1]

            if line_buffer:
                yield json.dumps({"type": "token", "content": line_buffer}) + "\n"

        except Exception as err:
            import traceback
            traceback.print_exc()
            error_payload = {
                "type": "token",
                "content": "\n\n> ⚠️ **INVESTIGATION INTERRUPTED:** Chronograph encountered a processing error. Please try again later."
            }
            yield json.dumps(error_payload) + "\n"

        finally:
            full_context = None
            vector_chunks = None
            records = None
            gc.collect()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
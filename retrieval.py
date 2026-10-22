"""
Chronograph: CLI Retrieval & Evaluation Module
Aligned with api.py for unified prompt architecture, token budgets, and hybrid GraphRAG retrieval.
"""

import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI, RateLimitError, APIError

from neo4j_graphrag.embeddings import GeminiEmbedder
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.generation import RagTemplate

# 1. Environment & Database Connection
load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")),
    max_connection_lifetime=200,
    keep_alive=True
)

# 2. LLM & Fallback Configuration (Aligned with api.py)
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

llm_client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def call_llm(prompt: str, temperature: float = 0.0) -> str:
    """Calls Primary Model with fallback to secondary model on rate limit or API error."""
    try:
        response = llm_client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        msg = response.choices[0].message
        return msg.content.strip() if hasattr(msg, "content") and msg.content else str(msg).strip()
    except (RateLimitError, APIError) as e:
        print(f"⚠️ [CLI FALLBACK TRIGGERED]: {PRIMARY_MODEL} rate-limited ({e}). Switching to {FALLBACK_MODEL}...")
        time.sleep(1.0)
        response = llm_client.chat.completions.create(
            model=FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        msg = response.choices[0].message
        return msg.content.strip() if hasattr(msg, "content") and msg.content else str(msg).strip()

embedder = GeminiEmbedder(
    model="gemini-embedding-001",
    api_key=os.getenv("GEMINI_API_KEY")
)

# 3. Streamlined, General-Purpose Cypher Generation Prompt (Identical to api.py)
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

# 4. Hybrid Semantic Vector Retriever
vector_cypher_retriever = VectorCypherRetriever(
    driver=driver,
    neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
    index_name="chunkEmbedding",
    embedder=embedder,
    retrieval_query=RETRIEVAL_QUERY
)

# 5. Synthesis Template (Synchronized with api.py)
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
2. **Direct Strategic Grounding**: If the question asks about specific team communications, radio messages, or backstage disputes and the exact verbatim transcript is not documented, analyze the verified tactical decisions, pit-wall run plans, delta pacing, or tow allocations recorded in the context. Do NOT lead with negative disclaimers or say "no records exist."
3. **Structured Analytical Depth**: Deliver an exhaustive breakdown below the Paddock Primer. Cover the engineering background, aerodynamic/power unit context, regulatory implications, and paddock fallout thoroughly.
4. **Formatting Requirements**:
   - Follow the Paddock Primer with clean Markdown subheadings (`### Timeline Breakdown`, `### Technical & Strategic Analysis`, `### Regulatory & Paddock Impact`, etc.) to structure the report.
   - Include at least **one Markdown comparison or event table** detailing key telemetry metrics, lap deltas, driver comparisons, or chronological phases.
   - Use bold bullet points for specific technical triggers, telemetry differentials, or regulatory articles.
   - **STRICT PROHIBITION ON ASCII DIAGRAMS**: DO NOT draw ASCII boxes, pseudo-code flowcharts, character-art trees, or wireframes (e.g., using `+---`, `|`, `+`, `v`). Format all structural hierarchies, system pillars, and sequences exclusively using standard Markdown Tables or bold nested lists.
5. **Archive Note (Conditional)**:
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

# 6. Hybrid Retrieval Engine (Aligned with api.py context scale)
def format_cypher_records(records: list[dict]) -> str:
    lines = []
    for r in records[:15]:
        parts = [f"{k}: {v}" for k, v in r.items() if v is not None]
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)

def ask_chronograph(question: str):
    print(f"\n🏎️ [USER QUERY]: {question}")
    retrieved_contexts = []

    # Branch 1: Graph Cypher Traversal
    try:
        gen_prompt = CYPHER_PROMPT.replace("{query_text}", question)
        raw_cypher = call_llm(gen_prompt, temperature=0.0)

        archetype = "FACTUAL_LOOKUP"
        lines = raw_cypher.strip().splitlines()
        if lines and "ARCHETYPE:" in lines[0]:
            archetype = lines[0].split("ARCHETYPE:")[-1].strip()
            clean_cypher = "\n".join(lines[1:]).strip()
        else:
            clean_cypher = raw_cypher.strip()

        clean_cypher = re.sub(r"^```(cypher)?|```$", "", clean_cypher, flags=re.MULTILINE).strip()
        
        print("\n⚙️ [STEP 1: TEXT2CYPHER GENERATION]")
        print(f"   Detected Archetype: {archetype}")
        print(f"   Cypher Query: {clean_cypher}")

        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            db_res = session.run(clean_cypher)
            records = [record.data() for record in db_res]
            
        print(f"   Records Returned: {len(records)}")
        if records:
            graph_context = format_cypher_records(records)
            retrieved_contexts.append(f"GRAPH DATABASE TRAVERSAL:\n{graph_context}")
    except Exception as e:
        print(f"   ❌ Text2Cypher Error: {e}")

    # Branch 2: VectorCypher Semantic Retrieval (top_k=6 matching api.py)
    try:
        print("\n🔄 [STEP 2: VECTORCYPHER SEMANTIC RETRIEVAL]")
        search_res = vector_cypher_retriever.search(query_text=question, top_k=6)
        items = getattr(search_res, "items", [])
        print(f"   Semantic Chunks Retrieved: {len(items)}")

        vector_chunks = "\n---\n".join([str(item.content) for item in items if getattr(item, "content", None)])
        if vector_chunks:
            retrieved_contexts.append(f"SEMANTIC VECTOR RETRIEVAL:\n{vector_chunks}")
    except Exception as e:
        print(f"   ❌ Vector Search Error: {e}")

    # Step 3: Synthesis with Expanded Context Budget (8000 words matching api.py)
    full_context = "\n\n====================\n\n".join(retrieved_contexts)
    
    words = full_context.split()
    if len(words) > 8000:
        print(f"   ⚠️ Context exceeded safe token budget ({len(words)} words). Truncating safely to 8000 words...")
        full_context = " ".join(words[:8000])

    print(f"\n🧠 [STEP 3: LLM SYNTHESIS]")
    print(f"   Payload Word Count: ~{len(full_context.split())} words")
    
    prompt = chronograph_template.template.replace("{context}", full_context).replace("{query_text}", question)
    return call_llm(prompt, temperature=0.2)

def pure_vector_search(question: str) -> str:
    """Pure Vector RAG baseline: retrieves chunks without structured Cypher traversal."""
    try:
        search_res = vector_cypher_retriever.search(query_text=question, top_k=6)
        items = getattr(search_res, "items", [])
        vector_chunks = "\n---\n".join([str(item.content) for item in items if getattr(item, "content", None)])
        context = f"SEMANTIC VECTOR RETRIEVAL ONLY:\n{vector_chunks}" if vector_chunks else "NO CONTEXT FOUND."
    except Exception as e:
        context = f"Vector retrieval error: {e}"

    prompt = chronograph_template.template.replace("{context}", context).replace("{query_text}", question)
    return call_llm(prompt, temperature=0.2)

# Alias for consistent naming
hybrid_graphrag_search = ask_chronograph

if __name__ == "__main__":
    try:
        print("🏎️ Chronograph Interactive CLI Test (Type 'exit' or 'quit' to stop)\n" + "-"*50)
        while True:
            user_query = input("\n👉 Enter your question: ")
            if user_query.lower() in ["exit", "quit", "q"]:
                break
            if not user_query.strip():
                continue
            answer = ask_chronograph(user_query)
            print(f"\n🤖 Answer:\n{answer}")
    finally:
        driver.close()
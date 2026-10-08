import os
import re
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI, RateLimitError

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

# 2. LLM & Embedder Configuration
llm_client = OpenAI(
    # api_key=os.getenv("GROQ_API_KEY"),
    # base_url="https://api.groq.com/openai/v1"
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL_NAME = "gemini-3.8-flash"

def call_llm(prompt: str, temperature: float = 0.0) -> str:
    response = llm_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature
    )
    msg = response.choices[0].message
    if hasattr(msg, "content") and msg.content:
        return msg.content.strip()
    return str(msg).strip()

embedder = GeminiEmbedder(
    model="gemini-embedding-001",
    api_key=os.getenv("GEMINI_API_KEY")
)

# 3. Streamlined, General-Purpose Cypher Generation Prompt
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

# 5. Temporal Synthesis Template
today_str = datetime.now().strftime("%B %d, %Y")

chronograph_template = RagTemplate(
    template=f"""You are Chronograph, an expert Formula 1 Temporal Knowledge Assistant with the editorial judgment of a veteran motorsport journalist.
TODAY'S DATE: {today_str}

Answer the user's question using the provided context retrieved from the Knowledge Graph.

Editorial & Synthesis Rules:
1. Editorial Hierarchy: Prioritize high-impact structural turning points (contract signings, team departures, championship milestones, technical leadership changes).
2. Ground your response temporally relative to TODAY'S DATE ({today_str}).
3. Synthesize milestones into a clear chronological breakdown.
4. Exhaustive Synthesis & Depth: Provide an in-depth, comprehensive journalistic breakdown. Explain the full narrative, technical engineering context, and sporting implications thoroughly. Only mention data gaps if critical requested milestones are completely missing, and keep any such note strictly to a single brief sentence at the very end.
5. Constructor & Driver Integrity:
   - In modern Formula 1, a driver actively races for only ONE constructor team during a specific Grand Prix weekend or season.
   - If retrieved context lists feeder series, GT cars (e.g., Lamborghini), junior academies, test outings, or transfer rumors, distinguish between past background/testing and the driver's active Formula 1 race seat. Never claim a driver raced for multiple constructors in the same Grand Prix.
   - Teammate interactions, pit strategy, or team orders between drivers representing the same constructor are strictly intra-team matters.
6. Penalty & Upgrade Consolidation:
   - Formula 1 news reports often describe the EXACT same penalty or car update using synonymous wording (e.g., 'grid-penalty', 'engine-penalty', and 'three-place grid-penalty' for a driver at the same race are different journalistic descriptions of ONE single regulatory sanction, not multiple separate penalties).
   - Consolidate synonymous penalty or upgrade descriptions into a unified, accurate event summary rather than listing them as separate consecutive infractions.
7. Zero Hallucination: Never invent driver transfers, results, or relationships. If a structured entity tag contradicts a detailed narrative event, prioritize the concrete event narrative.

# Context:
{{context}}

# Question:
{{query_text}}

# Answer:
""",
    expected_inputs=["context", "query_text"]
)

# 6. Hybrid Retrieval Engine
def format_cypher_records(records: list[dict]) -> str:
    lines = []
    for r in records[:15]:
        parts = [f"{k}: {v}" for k, v in r.items() if v is not None]
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)

def ask_chronograph(question: str):
    print(f"\n🏎️ [USER QUERY]: {question}")
    retrieved_contexts = []

    # Branch 1: Graph Cypher Traversal (Structured Facts)
    try:
        gen_prompt = CYPHER_PROMPT.replace("{query_text}", question)
        raw_cypher = call_llm(gen_prompt, temperature=0.0)

        # --- PARSE ARCHETYPE & CLEAN QUERY ---
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
        else:
            print("   ⚠️ Text2Cypher returned 0 records.")
    except Exception as e:
        print(f"   ❌ Text2Cypher Error: {e}")

    # Branch 2: VectorCypher Semantic Retrieval (Narrative Chunks)
    try:
        print("\n🔄 [STEP 2: VECTORCYPHER SEMANTIC RETRIEVAL]")
        search_res = vector_cypher_retriever.search(query_text=question, top_k=3)
        print(f"   Semantic Chunks Retrieved: {len(search_res.items)}")

        vector_chunks = "\n---\n".join([str(item.content)[:1800] for item in search_res.items[:3] if item.content])
        if vector_chunks:
            retrieved_contexts.append(f"SEMANTIC VECTOR RETRIEVAL:\n{vector_chunks}")
    except Exception as e:
        print(f"   ❌ Vector Search Error: {e}")

    # Step 3: Synthesis
    full_context = "\n\n====================\n\n".join(retrieved_contexts)
    
    words = full_context.split()
    if len(words) > 3500:
        print(f"   ⚠️ Context exceeded safe token budget ({len(words)} words). Truncating safely...")
        full_context = " ".join(words[:3500])

    print(f"\n🧠 [STEP 3: LLM TEMPORAL SYNTHESIS]")
    print(f"   Payload Word Count: ~{len(full_context.split())} words")
    
    prompt = chronograph_template.template.replace("{context}", full_context).replace("{query_text}", question)
    return call_llm(prompt, temperature=0.0)

# 7. Adding a pure vector search w/o the cypher query traversal for evaluator.py
def pure_vector_search(question: str) -> str:
    """Pure Vector RAG baseline: retrieves chunks without structured Cypher traversal."""
    try:
        search_res = vector_cypher_retriever.search(query_text=question, top_k=3)
        vector_chunks = "\n---\n".join([str(item.content)[:1800] for item in search_res.items[:3] if item.content])
        context = f"SEMANTIC VECTOR RETRIEVAL ONLY:\n{vector_chunks}" if vector_chunks else "NO CONTEXT FOUND."
    except Exception as e:
        context = f"Vector retrieval error: {e}"

    prompt = chronograph_template.template.replace("{context}", context).replace("{query_text}", question)
    return call_llm(prompt, temperature=0.0)

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
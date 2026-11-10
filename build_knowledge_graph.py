import os 
import glob
import asyncio
import shutil
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Import Gemini and Groq providers from neo4j_graphrag
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.embeddings import GeminiEmbedder
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.experimental.components.text_splitters.fixed_size_splitter import FixedSizeSplitter

# 0.5 Directories for news processing
RAW_DIR = os.path.join("data", "raw_news")
PROCESSED_DIR = os.path.join("data", "processed_news")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# 1. Load Environment Variables 
load_dotenv()

# 2. Neo4j Driver Connection
driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(
        os.getenv("NEO4J_USERNAME"),
        os.getenv("NEO4J_PASSWORD")
    ),
    max_connection_lifetime=200,
    max_connection_pool_size=50,
    connection_acquisition_timeout=60,
    keep_alive=True
)
driver.verify_connectivity()

# 3. Initialize Groq LLM & Gemini Embedder
# Use 120b or llama-3.3-70b-versatile to avoid JSON truncation from smaller models
llm = OpenAILLM(
    # model_name="openai/gpt-oss-120b", 
    # model_params={"temperature": 0.0},
    # api_key=os.getenv("GROQ_API_KEY"),
    # base_url="https://api.groq.com/openai/v1", 
    model_name="gemini-3.5-flash-lite",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=os.getenv("GEMINI_API_KEY")
)
llm.supports_structured_output = False

embedder = GeminiEmbedder(
    model="gemini-embedding-001",
    api_key=os.getenv("GEMINI_API_KEY")
)

text_splitter = FixedSizeSplitter(chunk_size=2500, chunk_overlap=150)

# 4. Define F1 Schema with Explicit Canonical Guidance
NODE_TYPES = [
    {
        "label": "Driver",
        "description": "An F1 driver. Name MUST be the full official name (e.g., 'Lewis Hamilton', 'Lando Norris', 'Max Verstappen', 'Carlos Sainz', 'George Russell'). NEVER use surnames alone like 'Hamilton' or abbreviations."
    },
    {
        "label": "Team",
        "description": "An F1 constructor team. Use standard constructor name (e.g., 'McLaren', 'Ferrari', 'Red Bull Racing', 'Mercedes', 'Aston Martin')."
    },
    {
        "label": "GrandPrix",
        "description": "An F1 race event. ALWAYS use the full event name ending in 'Grand Prix' WITHOUT years (e.g., 'Italian Grand Prix', 'Dutch Grand Prix', 'Azerbaijan Grand Prix'). NEVER use 'GP' or include years like '2026 Dutch GP'."
    },
    {
        "label": "Circuit",
        "description": "A racing track circuit. Use official track names (e.g., 'Baku City Circuit', 'Circuit Zandvoort', 'Autodromo Nazionale Monza', 'Silverstone Circuit')."
    },
    "Season",
    "Engine",
    "TyreManufacturer",
    "Penalty",
    "CarUpgrade",
    {
        "label": "Person",
        "description": "Non-driver personnel such as Team Principals or engineers (e.g., 'Toto Wolff', 'Christian Horner', 'Andrea Stella')."
    }
]

RELATIONSHIP_TYPES = [
    "DRIVES_FOR",
    "WON_BY",
    "MANAGES",
    "COACHES",
    "COMPETED_IN",
    "RECEIVED_PENALTY", 
    "ISSUED_AT",
    "INTRODUCED_UPGRADE",
    "INTRODUCED_AT",
    "POWERED_BY",
    "SUPPLIED_BY",
    "HELD_AT",
    "HELD_IN",
    "PENALIZED_AT",  
]

PATTERNS = [
    ("Driver", "DRIVES_FOR", "Team"),
    ("Driver", "RECEIVED_PENALTY", "Penalty"),
    ("Driver", "PENALIZED_AT", "GrandPrix"),
    ("Penalty", "ISSUED_AT", "GrandPrix"),
    ("Person", "MANAGES", "Driver"),
    ("Person", "COACHES", "Driver"),
    ("Person", "MANAGES", "Team"),
    ("Team", "POWERED_BY", "Engine"),
    ("Team", "INTRODUCED_UPGRADE", "CarUpgrade"),
    ("CarUpgrade", "INTRODUCED_AT", "GrandPrix"),
    ("GrandPrix", "WON_BY", "Driver"),
    ("GrandPrix", "HELD_AT", "Circuit"),
    ("GrandPrix", "HELD_IN", "Season"),
    ("Driver", "COMPETED_IN", "Season"),
    ("Team", "COMPETED_IN", "Season"),
    ("GrandPrix", "SUPPLIED_BY", "TyreManufacturer"),
]

# 5. Instantiate KG Pipeline with error tolerance
kg_pipeline = SimpleKGPipeline(
    llm=llm,
    driver=driver,
    neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
    embedder=embedder,
    text_splitter=text_splitter,
    from_file=False, 
    perform_entity_resolution=True,
    on_error="IGNORE",
    schema={
        "node_types": NODE_TYPES,            
        "relationship_types": RELATIONSHIP_TYPES, 
        "patterns": PATTERNS,
        "additional_node_types": False,
    }
)

# 6. Automated Sanitization and Deduplication
def sanitize_graph(driver):
    """
    Purges placeholder entities, loops, and dynamically merges identical duplicate
    entities and parallel edges across the entire graph without hardcoding names.
    """
    cleanup_queries = [
        # 1. Flatten any array names created by prior merges back to single clean strings
        """
        MATCH (n:__Entity__)
        WHERE n.name IS NOT NULL AND n.name IS :: LIST<ANY>
        SET n.name = head(n.name);
        """,

        # 2. Delete generic/placeholder entities safely (case-insensitive & trimmed)
        """
        MATCH (n:__Entity__) 
        WHERE toLower(trim(toString(n.name))) IN [
            'unknown', 'engine name', 'none', 'n/a', '', 
            'circuit', 'grand prix', '2026 grand prix', 'unnamed grand prix', 
            'car upgrades', 'upgrades', 'engine', 'f1 engine'
        ] 
        DETACH DELETE n;
        """,

        # 3. Delete self-referential relationship loops
        "MATCH (n:__Entity__)-[r]->(n) DELETE r;",

        # 4. GENERALIZED DEDUPLICATION: Merge ANY duplicate nodes sharing the exact same name
        # Automatically collapses all duplicate drivers, teams, tracks, upgrades, etc.
        """
        MATCH (n:__Entity__)
        WHERE n.name IS NOT NULL AND NOT n:Chunk
        WITH toLower(trim(toString(n.name))) AS normalized_name, collect(n) AS nodes
        WHERE size(nodes) > 1
        CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine', mergeRels: true}) YIELD node
        RETURN count(node);
        """,

        # 5. GENERALIZED SEASON NORMALIZATION: Automatically merges variations like "2026 Season" -> "2026"
        """
        MATCH (s:Season)
        WHERE s.name =~ '.*\\b(19\\d{2}|20\\d{2})\\b.*' AND NOT s.name =~ '^\\d{4}$'
        WITH s, apoc.text.regexGroups(s.name, '\\b(19\\d{2}|20\\d{2})\\b')[0][0] AS year_hub
        MERGE (target:Season {name: year_hub})
        WITH target, s
        WHERE target <> s
        CALL apoc.refactor.mergeNodes([target, s], {properties: 'combine', mergeRels: true}) YIELD node
        RETURN count(node);
        """,

        # 6. GENERALIZED RELATIONSHIP PRUNING: Prune redundant parallel edges between the same nodes
        """
        MATCH (a:__Entity__)-[r]->(b:__Entity__)
        WITH a, b, type(r) AS rel_type, collect(r) AS rels
        WHERE size(rels) > 1
        UNWIND rels[1..] AS dup
        DELETE dup;
        """
    ]
    with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
        for idx, q in enumerate(cleanup_queries, 1):
            try:
                session.run(q)
            except Exception as e:
                print(f"⚠️ Sanitization query {idx} notice: {e}")
    print("\n🧹 Graph sanitization complete! All duplicate entities and edges generalized & unified.")

# 7. Ingestion Helpers
async def ingest_large_text_safely(pipeline, full_text: str, chunk_limit: int = 4000):
    """Slices documents into safe windows and pauses to respect API token boundaries."""
    if len(full_text) <= chunk_limit:
        await pipeline.run_async(text=full_text)
        return

    slices = [full_text[i:i + chunk_limit] for i in range(0, len(full_text), chunk_limit)]
    print(f"  📄 Document is large ({len(full_text)} chars) -> Split into {len(slices)} throttled batches.")

    for idx, batch_text in enumerate(slices, 1):
        print(f"  ↳ Ingesting batch {idx}/{len(slices)} ({len(batch_text)} chars)...")
        await pipeline.run_async(text=batch_text)
        
        if idx < len(slices):
            print("  ⏳ Pausing 15s for Gemini TPM bucket recharge...")
            await asyncio.sleep(15)

# 8. Main Execution
async def run_kg_pipeline():
    search_path = os.path.join(RAW_DIR, "*.txt")
    target_files = glob.glob(search_path)

    if not target_files:
        print("⚠️ No raw news text files found in 'data/raw_news/'.")
        return
    
    print(f"🏎️ Ingesting {len(target_files)} F1 articles into Neo4j via Gemini...")

    for file_path in target_files:
        filename = os.path.basename(file_path)
        print(f"\n🧬 Processing Document: {filename}")

        with open(file_path, "r", encoding="utf-8") as f:
            text_content = f.read()

        try:
            await ingest_large_text_safely(kg_pipeline, text_content)
            print(f"✅ Extracted graph structure for: {filename}")

            dest_path = os.path.join(PROCESSED_DIR, filename)
            shutil.move(file_path, dest_path)
            print(f"📦 Archived: {filename} -> {PROCESSED_DIR}/")

        except Exception as e:
            print(f"⚠️ Extraction issue on {filename}: {e}")
            print(f"📌 {filename} remains in staging for the next retry.")

        print("⏳ Waiting 20 seconds for Gemini TPM reset...")
        await asyncio.sleep(20)

    # Run sanitization after the batch run
    sanitize_graph(driver)

if __name__ == "__main__":
    try:
        asyncio.run(run_kg_pipeline())
    finally:
        driver.close()
        print("🔌 Neo4j Driver disconnected safely.")
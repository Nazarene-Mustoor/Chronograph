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
    """Purges placeholder entities, loops, and merges aliases across drivers, GPs, and circuits."""
    cleanup_queries = [
        # 1. Flatten any array names created by previous merges back to single strings
        """
        MATCH (n:__Entity__)
        WHERE n.name IS NOT NULL AND n.name IS :: LIST<ANY>
        SET n.name = head(n.name);
        """,

        # 2. Delete generic/placeholder entities safely (using toString to protect against unexpected types)
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
        
        # 4. Merge Driver Aliases (keeping canonical properties intact)
        """
        UNWIND [
          {canonical: "Lewis Hamilton", aliases: ["Hamilton", "L. Hamilton", "Sir Lewis Hamilton"]},
          {canonical: "Lando Norris", aliases: ["Norris", "L. Norris"]},
          {canonical: "Max Verstappen", aliases: ["Verstappen", "M. Verstappen"]},
          {canonical: "George Russell", aliases: ["Russell", "G. Russell"]},
          {canonical: "Charles Leclerc", aliases: ["Leclerc", "C. Leclerc"]},
          {canonical: "Fernando Alonso", aliases: ["Alonso", "Fernando"]},
          {canonical: "Pierre Gasly", aliases: ["Gasly", "P. Gasly"]},
          {canonical: "Carlos Sainz", aliases: ["Sainz", "Carlos", "Sainz Jr", "Carlos Sainz Jr"]},
          {canonical: "Kimi Antonelli", aliases: ["Andrea Kimi Antonelli", "Antonelli"]},
          {canonical: "Esteban Ocon", aliases: ["Ocon", "Esteban"]},
          {canonical: "Valtteri Bottas", aliases: ["Bottas", "V. Bottas"]},
          {canonical: "Sergio Perez", aliases: ["Perez", "Checo", "Checo Perez"]},
          {canonical: "Oliver Bearman", aliases: ["Ollie Bearman", "Bearman", "Ollie"]},
          {canonical: "Franco Colapinto", aliases: ["Colapinto", "Rafael Colapinto"]},
          {canonical: "Alexander Albon", aliases: ["Alex Albon", "Albon"]},
          {canonical: "Nico Hulkenberg", aliases: ["Hulkenberg", "Ulkenberg"]},
          {canonical: "Lance Stroll", aliases: ["Stroll", "L. Stroll"]},
          {canonical: "Gabriel Bortoleto", aliases: ["Bortoleto"]},
          {canonical: "Isack Hadjar", aliases: ["Hadjar", "Michele Hadjar"]},
          {canonical: "Oscar Piastri", aliases: ["Piastri", "Oscar Pisatri", "Liam Piastri"]}
        ] AS row
        MATCH (target:Driver {name: row.canonical})
        MATCH (alias:Driver) WHERE alias.name IN row.aliases AND alias <> target
        CALL apoc.refactor.mergeNodes([target, alias], {properties: {name: 'discard', `.*`: 'combine'}}) YIELD node
        SET node.name = row.canonical
        RETURN count(node);
        """,

        # 5. Merge Grand Prix Aliases
        """
        UNWIND [
          {canonical: "Italian Grand Prix", aliases: ["Monza Grand Prix", "Monza GP", "F1 Italian GP", "2026 Italian Grand Prix", "Italian Grand Prix 2026", "2026 F1 Italian GP", "2024 Italian Grand Prix"]},
          {canonical: "Dutch Grand Prix", aliases: ["Dutch GP", "Zandvoort Grand Prix", "2026 Dutch Grand Prix", "Dutch GP 2026", "2023 Dutch GP", "2026 F1 Dutch GP"]},
          {canonical: "Azerbaijan Grand Prix", aliases: ["Baku Grand Prix", "Baku GP"]},
          {canonical: "Spanish Grand Prix", aliases: ["Spanish GP", "Barcelona Grand Prix", "Barcelona-Catalunya Grand Prix", "2026 Spanish Grand Prix", "Spanish Grand Prix 2026"]},
          {canonical: "British Grand Prix", aliases: ["British GP"]},
          {canonical: "Hungarian Grand Prix", aliases: ["Hungarian GP", "Hungary Grand Prix", "Budapest Grand Prix", "2026 Hungarian Grand Prix", "Hungarian Grand Prix 2026"]},
          {canonical: "Monaco Grand Prix", aliases: ["Monaco GP", "F1 Monaco GP 1982"]},
          {canonical: "Japanese Grand Prix", aliases: ["Japanese GP", "Suzuka Grand Prix", "Japan Grand Prix"]},
          {canonical: "United States Grand Prix", aliases: ["US GP", "United States GP", "Austin Grand Prix"]},
          {canonical: "Belgian Grand Prix", aliases: ["Spa Grand Prix", "1998 Belgian GP", "Belgian Grand Prix 2026"]},
          {canonical: "Chinese Grand Prix", aliases: ["China Grand Prix", "Shanghai Grand Prix"]},
          {canonical: "Saudi Arabian Grand Prix", aliases: ["Saudi Arabia Grand Prix", "Jeddah Grand Prix", "2023 Saudi Arabian Grand Prix"]},
          {canonical: "Brazilian Grand Prix", aliases: ["Brazil Grand Prix", "Brazilian Grand Prix 2024", "Brazilian Grand Prix 2025", "Brazilian Grand Prix 2021"]}
        ] AS row
        MATCH (target:GrandPrix {name: row.canonical})
        MATCH (alias:GrandPrix) WHERE alias.name IN row.aliases AND alias <> target
        CALL apoc.refactor.mergeNodes([target, alias], {properties: {name: 'discard', `.*`: 'combine'}}) YIELD node
        SET node.name = row.canonical
        RETURN count(node);
        """,

        # 6. Merge Circuit Aliases
        """
        UNWIND [
          {canonical: "Baku City Circuit", aliases: ["Baku Street Circuit", "Baku Circuit", "Baku"]},
          {canonical: "Circuit Zandvoort", aliases: ["Zandvoort Circuit", "Netherlands Circuit", "Dutch Grand Prix Circuit"]},
          {canonical: "Circuit de Monaco", aliases: ["Monaco street circuit", "Monaco Circuit"]},
          {canonical: "Autodromo Nazionale Monza", aliases: ["Monza Circuit", "Italian Circuit"]},
          {canonical: "Silverstone Circuit", aliases: ["British Circuit"]},
          {canonical: "Circuit de Barcelona-Catalunya", aliases: ["Barcelona Circuit", "Barcelona-Catalunya"]},
          {canonical: "Suzuka Circuit", aliases: ["Japanese Circuit", "Suzuka"]},
          {canonical: "Jeddah Corniche Circuit", aliases: ["Jeddah Circuit", "Saudi Arabia Circuit"]},
          {canonical: "Hungaroring", aliases: ["Hungarian circuit", "Hungarian Grand Prix Circuit"]}
        ] AS row
        MATCH (target:Circuit {name: row.canonical})
        MATCH (alias:Circuit) WHERE alias.name IN row.aliases AND alias <> target
        CALL apoc.refactor.mergeNodes([target, alias], {properties: {name: 'discard', `.*`: 'combine'}}) YIELD node
        SET node.name = row.canonical
        RETURN count(node);
        """
    ]
    with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
        for q in cleanup_queries:
            try:
                session.run(q)
            except Exception as e:
                print(f"⚠️ Sanitization query notice: {e}")
    print("\n🧹 Graph sanitization complete! Canonical entities merged and artifacts purged.")

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
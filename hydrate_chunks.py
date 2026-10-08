import os
import sys
import time
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings import GeminiEmbedder

# 1. Environment & Connectivity Setup
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not all([NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, GEMINI_API_KEY]):
    print("❌ Missing required environment variables (.env). Check NEO4J_* and GEMINI_API_KEY.")
    sys.exit(1)

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    max_connection_lifetime=200,
    keep_alive=True
)

embedder = GeminiEmbedder(
    model="gemini-embedding-001",
    api_key=GEMINI_API_KEY
)

# 2. Graph Subgraph Extraction & Chunk Generation
def build_chunks(session) -> list[dict]:
    print("\n🔍 Step 1: Extracting factual subgraphs across Driver, Team, and GrandPrix nodes...")
    chunks = []

    # A. Driver profiles, teams, active seasons, and specific incidents
    driver_rows = session.run(
        """
        MATCH (d:Driver)
        OPTIONAL MATCH (d)-[:DRIVES_FOR]->(t:Team)
        OPTIONAL MATCH (d)-[:COMPETED_IN]->(s:Season)
        OPTIONAL MATCH (d)-[:RECEIVED_PENALTY]->(p:Penalty)-[:ISSUED_AT]->(gp:GrandPrix)
        WHERE (d)-[:PENALIZED_AT]->(gp)
        RETURN d.name AS driver,
               collect(DISTINCT t.name) AS teams,
               collect(DISTINCT s.name) AS seasons,
               collect(DISTINCT {penalty: p.name, grand_prix: gp.name}) AS penalties
        """
    ).data()

    for r in driver_rows:
        driver_name = r.get("driver")
        if not driver_name:
            continue
        teams = ", ".join(r.get("teams", [])) or "Independent / Unspecified team"
        seasons = ", ".join(r.get("seaons", [])) or "Formula 1 calendar"

        penalties_list = []
        for pen in r.get("penalties", []):
            if pen.get("penalty") and pen.get("grand_prix"):
                penalties_list.append(f"received {pen['penalty']} at {pen['grand_prix']}")

            penalties_clause = (
                f" Stewarding and incident history: {'; '.join(penalties_list)}."
                if penalties_list else " No disciplinary or grid penalties recorded."
            )

            chunk_text = (
                f"Formula 1 Driver Profile: {driver_name}. "
                f"Affiliated teams: {teams}. Competed in season(s): {seasons}.{penalties_clause}"
            )

            chunks.append({
                "chunk_id": f"chunk_driver_{driver_name.lower().replace(' ', '_')}",
                "text": chunk_text,
                "anchor_name": driver_name,
                "anchor_label": "Driver"
            })

    # B. Team profiles, engine partnerships, drivers, and technical upgrades
    team_rows = session.run(
        """
        MATCH (t:Team)
        OPTIONAL MATCH (d:Driver)-[:DRIVES_FOR]->(t)
        OPTIONAL MATCH (t)-[:POWERED_BY]->(e:Engine)
        OPTIONAL MATCH (t)-[:INTRODUCED_UPGRADE]->(u:CarUpgrade)
        OPTIONAL MATCH (u)-[:INTRODUCED_AT]->(gp:GrandPrix)
        RETURN t.name AS team,
               collect(DISTINCT d.name) AS drivers,
               collect(DISTINCT e.name) AS engines,
               collect(DISTINCT {upgrade: u.name, grand_prix: gp.name}) AS upgrades
        """
    ).data()

    for r in team_rows:
        team_name = r.get("team")
        if not team_name:
            continue
        drivers = ", ".join(r.get("drivers", [])) or " Roster undergoing updates"
        engines = ", ".join(r.get("engines", [])) or "Formula 1 power unit"

        upgrades_list = []
        for up in r.get("upgrades", []):
            if up.get("upgrade"):
                venue = f" at {up['grand_prix']}" if up.get("grand_prix") else ""
                upgrades_list.append(f"{up['upgrade']}{venue}")

            upgrades_clause = (
                f" Technical packages introduced: {'; '.join(upgrades_list)}."
                if upgrades_list else " Standard aerodynamic configuration."
            )

            chunk_text = (
                f"Formula 1 Constructor Profile: {team_name}. "
                f"Engine supplier: {engines}. Driver lineup: {drivers}.{upgrades_clause}"
            )

            chunks.append({
                "chunk_id": f"chunk_team_{team_name.lower().replace(' ','_')}",
                "text": chunk_text,
                "anchor_name": team_name,
                "anchor_label": "Team"
            })

    # C. Grand Prix events, circuits, seasons, and penalties served
    gp_rows = session.run(
        """
        MATCH (gp:GrandPrix)
        OPTIONAL MATCH (gp)-[:HELD_IN]->(s:Season)
        OPTIONAL MATCH (gp)-[:HELD_AT]->(c:Circuit)
        OPTIONAL MATCH (d:Driver)-[:PENALIZED_AT]->(gp)
        MATCH (d)-[:RECEIVED_PENALTY]->(p:Penalty)-[:ISSUED_AT]->(gp)
        RETURN gp.name AS grand_prix,
               collect(DISTINCT c.name) AS circuits,
               collect(DISTINCT s.name) AS seasons,
               collect(DISTINCT {driver: d.name, penalty: p.name}) AS incidents
        """
    ).data()

    for r in gp_rows:
        gp_name = r.get("grand_prix")
        if not gp_name:
            continue
        circuits = ", ".join(r.get("circuits", [])) or "Grand Prix circuit"
        seasons = ", ".join(r.get("seasons", [])) or "Championship calendar"

        incidents_list = []
        for inc in r.get("incidents", []):
            if inc.get("driver") and inc.get("penalty"):
                incidents_list.append(f"{inc['driver']} ({inc['penalty']})")

        incidents_clause = (
            f" Documented penalties and incidents: {'; '.join(incidents_list)}."
            if incidents_list else " Clean race weekend without recorded grid sanctions."
        )

        chunk_text = (
            f"Formula 1 Event: {gp_name}. "
            f"Venue: {circuits}. Held in season(s): {seasons}.{incidents_clause}"
        )

        chunks.append({
            "chunk_id": f"chunk_gp_{gp_name.lower().replace(' ', '_')}",
            "text": chunk_text,
            "anchor_name": gp_name,
            "anchor_label": "GrandPrix"
        })

    print(f"✅ Generated {len(chunks)} canonical narrative chunks from the graph topology.")
    return chunks

# 3. Vector Embedding & Database Ingestion
def write_and_link_chunks(session, chunks: list[dict]):
    print("\n⚡ Step 2: Embedding chunks via Gemini and writing (:Chunk) nodes to Neo4j...")

    total = len(chunks)
    for idx, item in enumerate(chunks, start=1):
        # Generate the embedding vector
        embedding = embedder.embed_query(item["text"])

        # Write: Chunk and merge (:Entity)-[:FROM_CHUNK]->(:Chunk)
        session.run(
            """
            MERGE (c:Chunk {chunkId: $chunk_id})
            SET c.text = $text,
                c.embedding = $embedding
            WITH c
            MATCH (e)
            WHERE e.name = $anchor_name AND $anchor_label IN labels(e)
            MERGE (e)-[:FROM_CHUNK]->(c)
            """, {
                "chunk_id": item["chunk_id"],
                "text": item["text"],
                "embedding": embedding,
                "anchor_name": item["anchor_name"],
                "anchor_label": item["anchor_label"]
            }
        )

        if idx % 20 == 0 or idx == total:
            print(f"   [{idx}/{total}] Chunks embedded and linked to (:__Entity__)...")
            time.sleep(0.2)  # Avoid provider burst rate limits

def run_hydration():
    start_time = time.time()
    with driver.session(database=NEO4J_DATABASE) as session:
        chunks = build_chunks(session)
        if not chunks:
            print("⚠️ No valid subgraphs found. Are nodes populated in Neo4j?")
            return
        write_and_link_chunks(session, chunks)

        # Verification count
        count_res = session.run("MATCH (c:Chunk) RETURN count(c) AS chunk_count").single()
        rel_res = session.run("MATCH ()-[:FROM_CHUNK]->(c:Chunk) RETURN count(c) AS edge_count").single()
        
        print("\n" + "=" * 55)
        print("🎉 HYDRATION COMPLETE!")
        print(f"📊 Total (:Chunk) nodes active: {count_res['chunk_count']}")
        print(f"🔗 Total (Entity)-[:FROM_CHUNK]->(Chunk) edges: {rel_res['edge_count']}")
        print(f"⏱️ Time taken: {round(time.time() - start_time, 2)}s")
        print("=" * 55)

if __name__ == "__main__":
    try:
        run_hydration()
    finally:
        driver.close()
"""
Chronograph: 42-Query Benchmark Battery
Comprehensive evaluation suite testing Temporal GraphRAG against 5 core archetype suites:
- Suite 1: Temporal Evolution and Causal Chains (12 queries)
- Suite 2: Transition Point and Inflection Detection (5 queries)
- Suite 3: Epistemic and Perception Shifts (7 queries)
- Suite 4: Comparative Trajectories and Consequence Mappings (7 queries)
- Suite 5: Advanced 2026 and Multi-Hop Lineages (11 queries)
"""

import time
import argparse
from retrieval import ask_chronograph, driver

# Exact 42-Query Benchmark Battery
BENCHMARK_SUITES = {
    "Suite 1: Temporal Evolution and Causal Chains": [
        "How did Max Verstappen's relationship with Red Bull evolve from 2021 to 2026?",
        "How did McLaren's driver lineup evolve from 2018–2026, and what events caused each change?",
        "Show me the chain of events that led to this driver's team change.",
        "How did Mercedes go from championship dominance to midfield struggles?",
        "How did Aston Martin's trajectory change after Alonso joined?",
        "How did Oscar Piastri's role at McLaren evolve from newcomer to championship contender?",
        "What events led to Fernando Alonso leaving Alpine?",
        "What led to Hamilton's move from Mercedes to Ferrari?",
        "What events contributed to Daniel Ricciardo leaving McLaren?",
        "What events connect Adrian Newey's departure to changes across the F1 driver/team landscape?",
        "What people and events connect Red Bull's technical changes to its driver decisions?",
        "Show me the evolution of McLaren from 2021–2026."
    ],
    "Suite 2: Transition Point and Inflection Detection": [
        "When did the relationship between Vettel and Ferrari begin to deteriorate?",
        "When did Verstappen stop being Red Bull's second driver and become its clear team leader?",
        "When did Mercedes' relationship with Bottas change?",
        "When did Ferrari's relationship with Leclerc become more strained?",
        "When did Verstappen become Red Bull's undisputed #1?"
    ],
    "Suite 3: Epistemic and Perception Shifts": [
        "What was believed about Ferrari's championship chances before the 2024 season, and how did that perception change during the season?",
        "What did we know about this incident immediately after the race versus what became known later?",
        "What did people know about the 2021 Abu Dhabi controversy immediately after the race, versus what became known later?",
        "What was the paddock expecting from McLaren before the 2024 season, and how did that expectation change?",
        "What were the expectations surrounding Hamilton's Ferrari move before it happened?",
        "What events changed the perception of McLaren during the 2024 season?",
        "What changed the perception of Aston Martin between the beginning and end of 2023?"
    ],
    "Suite 4: Comparative Trajectories and Consequence Mappings": [
        "Compare Verstappen's rise at Red Bull with Leclerc's rise at Ferrari.",
        "Compare McLaren's recovery with Mercedes' decline from 2022–2026.",
        "How did Norris and Piastri's trajectories differ after joining McLaren?",
        "Show me everything that changed because of the 2024 Austrian GP.",
        "Which F1 driver-team relationships were true in 2021 but no longer exist in 2026?",
        "Which teams were considered championship favorites in 2022 but aren't anymore?",
        "What assumptions about the 2026 regulations turned out to be wrong?"
    ],
    "Suite 5: Advanced 2026 and Multi-Hop Lineages": [
        "Trace Andrea Kimi Antonelli's trajectory from his 2024 Mercedes junior announcement to leading the 2026 World Championship.",
        "What were the initial expectations around Cadillac's F1 entry versus the reality of their 2026 season with Bottas and Pérez?",
        "How did the team dynamics between Lewis Hamilton and Charles Leclerc develop during the 2026 Dutch Grand Prix, and what did Ferrari's team orders reveal about their hierarchy?",
        "Compare Liam Lawson's 2023 AlphaTauri substitute stint at Zandvoort with his 2026 Red Bull call-up replacing Isack Hadjar.",
        "How did Max Verstappen's Dutch Grand Prix record evolve from his 2021 return win to his Lap 1 crash at the final Zandvoort GP in 2026?",
        "Trace Liam Lawson's journey from his 2023 AlphaTauri debut to his 2026 Red Bull appearance at Zandvoort, explaining who he substituted for in each instance and why.",
        "What technical controversies or inquiries arose regarding Red Bull's flexible aero and the so-called 'Macarena wings' leading up to 2026?",
        "Explain what caused Lewis Hamilton's radio frustration regarding Charles Leclerc at the 2026 Dutch Grand Prix, and how Ferrari explained their strategy afterwards.",
        "What challenges and milestones are documented regarding Cadillac's entry and assembly ahead of the 2026/2027 regulation cycle?",
        "How did Kimi Antonelli perform at the 2026 Dutch Grand Prix, and what penalties or battles with Lando Norris impacted his result?",
        "Why are McLaren and Red Bull appealing the Monaco GP result to the FIA, and what is the strategic intent behind their appeal?"
    ]
}


def run_battery(suite_filter=None, query_index=None):
    """Executes the benchmark queries with structured CLI logging."""
    print("=" * 80)
    print("🏎️  CHRONOGRAPH: FULL 42-QUERY BENCHMARK REPRODUCIBILITY BATTERY")
    print("=" * 80)

    total_executed = 0
    start_time = time.time()

    for suite_name, queries in BENCHMARK_SUITES.items():
        if suite_filter and suite_filter.lower() not in suite_name.lower():
            continue

        print(f"\n📂 [{suite_name.upper()}] ({len(queries)} queries)\n" + "-" * 80)

        for i, query in enumerate(queries, 1):
            if query_index is not None and i != query_index:
                continue

            total_executed += 1
            print(f"\n[{total_executed}/42] 📋 Benchmark Query: \"{query}\"")
            
            try:
                answer = ask_chronograph(query)
                print("\n🤖 [CHRONOGRAPH SYNTHESIS]:")
                print(answer)
                print("\n" + "." * 80)
            except Exception as e:
                print(f"\n❌ [ERROR RUNNING QUERY]: {e}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"✅ Benchmark run completed: {total_executed} queries executed in {elapsed:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Chronograph Benchmark Battery")
    parser.add_argument("--suite", type=str, help="Filter by suite keyword (e.g. 'causal', 'inflection', 'epistemic', 'comparative', 'lineages')")
    parser.add_argument("--index", type=int, help="Run a specific query index within the chosen suite")
    
    args = parser.parse_args()

    try:
        run_battery(suite_filter=args.suite, query_index=args.index)
    finally:
        driver.close()
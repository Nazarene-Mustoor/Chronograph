"""
Chronograph Benchmark Evaluator: Pure Vector RAG vs. Hybrid GraphRAG
Measures Faithfulness, Temporal Completeness, and Entity Accuracy using Groq LLM-as-a-Judge across 5 capability suites.
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from retrieval import hybrid_graphrag_search, pure_vector_search, driver

load_dotenv()

# Initialize Groq client
eval_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
MODEL_NAME = "openai/gpt-oss-120b"

# High-stress representative test queries across 5 GraphRAG capability suites
TEST_QUERIES = [
    {
        "suite": "Suite 1: Multi-Year Causal Chain",
        "query": "What led to Hamilton's move from Mercedes to Ferrari?",
        "ground_truth": "Hamilton's move followed Mercedes' post-2021 competitive decline, his 2022 winless season, the February 2024 confirmation of his departure via a contract clause, Ferrari recruitment led by Frédéric Vasseur, and a subsequent multi-year Ferrari deal for 2025-2027, with the move reshaping Ferrari's driver lineup."
    },
    {
        "suite": "Suite 2: Relationship Inflection Point",
        "query": "When did the relationship between Vettel and Ferrari begin to deteriorate?",
        "ground_truth": "The relationship began deteriorating in early 2020 amid performance decline, missteps and team-order tensions; the decisive public turning point was Ferrari's 12 May 2020 announcement that Vettel would leave at the end of the season."
    },
    {
        "suite": "Suite 3: Temporal Horizon & Retrospective Inquiry",
        "query": "What did people know about the 2021 Abu Dhabi controversy immediately after the race, versus what became known later?",
        "ground_truth": "Immediately after the race, the controversy centered on Masi's selective unlapping and the final-lap restart. Later FIA inquiry findings concluded the procedure was not covered by the existing regulations and led to recommendations and subsequent changes to safety-car and race-direction governance."
    },
    {
        "suite": "Suite 4: Negative Space & Grounded Restraint",
        "query": "Show me everything that changed because of the 2024 Austrian GP.",
        "ground_truth": "The Verstappen-Norris clash led to a post-race penalty for Verstappen, which dropped him down the classification and allowed George Russell to move higher and gain additional championship points. No further structural consequences are established in the supplied evidence."
    },
    {
        "suite": "Suite 5: Multi-Hop Substitute Lineage",
        "query": "Trace Liam Lawson's journey from his 2023 AlphaTauri debut to his 2026 Red Bull appearance at Zandvoort, explaining who he substituted for in each instance and why.",
        "ground_truth": "In 2023 Lawson substituted for injured Daniel Ricciardo at AlphaTauri after Ricciardo's hand injury. He was later promoted to Red Bull in early 2025 ahead of Yuki Tsunoda, then returned to AlphaTauri mid-season. In 2026 he returned to Red Bull at Zandvoort as a substitute for Isack Hadjar, who was unavailable with a wrist injury."
    }
]

JUDGE_PROMPT = """You are an expert motorsport and AI benchmark evaluator comparing RAG outputs.
Evaluate the Generated Answer against the Ground Truth and Query.

Suite: {suite}
Query: {query}
Ground Truth: {ground_truth}
Generated Answer: {answer}

Score the answer on two dimensions from 1 to 5:
1. Faithfulness (1-5): Is the answer factually accurate, grounded in context, and free of hallucinated driver-team pairings or events?
2. Completeness (1-5): Did the answer capture the key causal turning points and temporal progression? (Properly declared data gaps must NOT be penalized).

Return your evaluation strictly as a valid JSON object:
{{
    "faithfulness_score": <int 1-5>,
    "completeness_score": <int 1-5>,
    "critique": "<2 sentence explanation highlighting strengths or failure points>"
}}
"""

def evaluate_response(suite: str, query: str, ground_truth: str, answer: str) -> dict:
    prompt = JUDGE_PROMPT.format(suite=suite, query=query, ground_truth=ground_truth, answer=answer)
    try:
        response = eval_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"faithfulness_score": 1, "completeness_score": 1, "critique": f"Evaluation error: {e}"}

def run_benchmark():
    print("=" * 80)
    print("🔬 RUNNING BENCHMARK: Pure Vector RAG vs. Hybrid GraphRAG (Chronograph)")
    print("=" * 80 + "\n")

    results = []
    graph_faith_total, graph_comp_total = 0, 0
    vec_faith_total, vec_comp_total = 0, 0

    for idx, item in enumerate(TEST_QUERIES, start=1):
        suite = item["suite"]
        q = item["query"]
        gt = item["ground_truth"]
        print(f"\n[{idx}/{len(TEST_QUERIES)}] 🏷️ {suite}")
        print(f"📋 Query: \"{q}\"")

        # 1. Evaluate Hybrid GraphRAG (Chronograph)
        print("  ⚙️ Executing Hybrid GraphRAG...")
        graph_ans = hybrid_graphrag_search(q)
        graph_eval = evaluate_response(suite, q, gt, graph_ans)
        graph_faith_total += graph_eval.get("faithfulness_score", 0)
        graph_comp_total += graph_eval.get("completeness_score", 0)

        # 2. Evaluate Pure Vector RAG (Baseline)
        print("  🔍 Executing Pure Vector RAG...")
        vector_ans = pure_vector_search(q)
        vector_eval = evaluate_response(suite, q, gt, vector_ans)
        vec_faith_total += vector_eval.get("faithfulness_score", 0)
        vec_comp_total += vector_eval.get("completeness_score", 0)

        print(f"  📊 GraphRAG  -> Faithfulness: {graph_eval.get('faithfulness_score')}/5 | Completeness: {graph_eval.get('completeness_score')}/5")
        print(f"  📊 VectorRAG -> Faithfulness: {vector_eval.get('faithfulness_score')}/5 | Completeness: {vector_eval.get('completeness_score')}/5")

        results.append({
            "suite": suite,
            "query": q,
            "ground_truth": gt,
            "hybrid_graphrag": {
                "answer": graph_ans,
                "eval": graph_eval
            },
            "pure_vector_rag": {
                "answer": vector_ans,
                "eval": vector_eval
            }
        })

    # Summary Statistics
    total_q = len(TEST_QUERIES)
    print("\n" + "=" * 80)
    print("📈 FINAL BENCHMARK COMPARISON MATRIX")
    print("=" * 80)
    print(f"Hybrid GraphRAG (Chronograph) | Avg Faithfulness: {graph_faith_total/total_q:.2f}/5 | Avg Completeness: {graph_comp_total/total_q:.2f}/5")
    print(f"Pure Vector RAG Baseline     | Avg Faithfulness: {vec_faith_total/total_q:.2f}/5 | Avg Completeness: {vec_comp_total/total_q:.2f}/5")
    print("=" * 80)

    # Save artifact for README and blog post
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n💾 Benchmark comparison saved to benchmark_results.json\n")

if __name__ == "__main__":
    try:
        run_benchmark()
    finally:
        driver.close()
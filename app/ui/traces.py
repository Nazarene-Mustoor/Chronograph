import asyncio
import re
import string
from pydantic import BaseModel
import reflex as rx


class TraceNode(BaseModel):
    """Universal trace node compatible with Reflex serialization."""

    stage: str
    title: str
    detail: str

# ==============================================================================
# UI DESIGN SYSTEM & INTERACTION CONSTANTS
# ==============================================================================

_HOVER_ELEVATION = {
    "border_color": "#e10600",
    "transform": "translateY(-2px)",
    "box_shadow": "0 4px 14px rgba(225, 6, 0, 0.15)",
    "transition": "all 0.15s cubic-bezier(0.4, 0, 0.2, 1)",
}

STICKY_SIDEBAR_STYLE = {
    "position": "sticky",
    "top": "1.5rem",
    "height": "fit-content",
    "max_height": "calc(100vh - 3rem)",
    "overflow_y": "auto",
    # Hide scrollbar for Chrome, Safari, and Opera
    "&::-webkit-scrollbar": 
    {
        "display": "none",
    },
    # Hide scrollbar for IE, Edge, and Firefox
    "scrollbar_width": "none",
    "-ms-overflow-style": "none",
}

# ==============================================================================
# TEXT SANITIZATION & EXTRACTION UTILS
# ==============================================================================


def _clean_markdown(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^[#\s]+", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _parse_table(answer: str) -> list[tuple[str, str]]:
    """Extracts rows from markdown tables as clean (title, detail) tuples."""
    lines = [
        line.strip()
        for line in answer.splitlines()
        if line.strip().startswith("|")
    ]
    pairs = []
    if len(lines) >= 3:
        for row in lines[2:]:
            if re.match(r"^\|[\s\-:|]+\|$", row):
                continue
            cols = [
                _clean_markdown(c.strip()) for c in row.strip("|").split("|")
            ]
            if len(cols) >= 2 and any(cols):
                stage_or_title = cols[0]
                detail = cols[1] if len(cols) == 2 else f"{cols[1]}: {cols[2]}"
                pairs.append((stage_or_title, detail))
    return pairs

def _parse_table_columns(answer: str) -> list[tuple[str, str]]:
    """Detects comparative tables where columns represent entities

    (e.g., Year | McLaren | Mercedes | Verdict) and pivots them into Subject
    cards aggregated across time.
    """
    lines = [
        line.strip()
        for line in answer.splitlines()
        if line.strip().startswith("|")
    ]
    if len(lines) < 3:
        return []

    # Parse headers
    headers = [
        _clean_markdown(c.strip()) for c in lines[0].strip("|").split("|")
    ]
    if len(headers) < 3:
        return []

    # Detect if the first column is a time/axis indicator
    first_col_is_time = any(
        k in headers[0].lower()
        for k in [
            "year",
            "date",
            "season",
            "stage",
            "period",
            "phase",
            "timeline",
        ]
    )
    if not first_col_is_time:
        return []

    # Parse content rows (ignoring header delimiter line |---|---|)
    rows = []
    for line in lines[2:]:
        if re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        cells = [
            _clean_markdown(c.strip()) for c in line.strip("|").split("|")
        ]
        if len(cells) == len(headers):
            rows.append(cells)

    if not rows:
        return []

    results = []
    # Pivot remaining columns into individual Subject entities
    for col_idx in range(1, len(headers)):
        col_header = headers[col_idx]
        clean_title = col_header.split("–")[0].split("-")[0].strip()

        chronology = []
        for r in rows:
            time_label = r[0]
            val = r[col_idx]
            if val and not _is_meta_junk(time_label, val):
                clean_val = re.sub(r"^\s*[•\-\*]\s*", "", val).strip()
                chronology.append(f"• {time_label}: {clean_val}")

        if chronology:
            results.append((clean_title, "\n".join(chronology)))

    return results

# --- FILTERING & CLEANED LIST PARSER ---

_IGNORED_META_TITLES = (
    "data gap",
    "bottom line",
    "what the knowledge graph",
    "context",
    "putting the pieces together",
    "evidence gap",
    "note",
    "summary",
    "disclaimer",
)

def _is_meta_junk(title: str, body: str) -> bool:
    """Returns True if the item is reasoning noise rather than domain data."""
    t_clean = title.strip().lower()
    b_clean = body.strip().lower()
    return any(t_clean.startswith(bad) for bad in _IGNORED_META_TITLES) or any(
        b_clean.startswith(bad) for bad in _IGNORED_META_TITLES
    )

def _parse_list(answer: str) -> list[tuple[str, str]]:
    """Extracts clean (title, detail) tuples, automatically filtering out meta junk."""
    pattern = r"(?:^|\n)\s*(?:\d+\.|\*|\-)\s*(?:\*\*(.*?)\*\*[:\-]?\s*)?(.*?)(?=(?:\n\s*(?:\d+\.|\*|\-)|\Z))"
    matches = re.findall(pattern, answer, re.DOTALL)
    results = []

    for title, body in matches:
        t = _clean_markdown(title)
        d = _clean_markdown(body).replace("\n", " ").strip()

        if not t and d:
            parts = d.split(".", 1)
            t = parts[0][:40]
            d = parts[1].strip() if len(parts) > 1 else parts[0]

        if (t or d) and not _is_meta_junk(t, d):
            results.append((t or "Milestone", d))

    return results

# ==============================================================================
# ARCHETYPE BUILDERS (Pure Python)
# ==============================================================================

def build_causal_trace(answer: str) -> list[TraceNode]:
    """1. CAUSAL_CONSEQUENCE_CHAIN: Chronological sequence of domino triggers."""
    nodes = []

    # 1. Try Markdown Table first
    raw_data = _parse_table(answer)

    # 2. Fallback to Bullet/Numbered List
    if not raw_data:
        raw_data = _parse_list(answer)

    # 3. Filter out meta-commentary, data gaps, and analysis noise
    filtered_data = [
        (title, detail)
        for title, detail in raw_data
        if not any(title.lower().startswith(bad) for bad in _IGNORED_META_TITLES)
        and not any(detail[:30].lower().startswith(bad) for bad in _IGNORED_META_TITLES)
        and len(detail.strip()) > 10
    ]

    # If filtering wiped everything out, fall back to whatever raw bullets existed
    clean_data = filtered_data if filtered_data else raw_data

    # 4. Cap strictly at 4-5 domino steps
    clean_data = clean_data[:5]

    if clean_data:
        total = len(clean_data)
        for i, (title, detail) in enumerate(clean_data):
            if i == 0:
                stage_label = "PRIMARY TRIGGER"
            elif i == total - 1:
                stage_label = "FINAL OUTCOME"
            else:
                stage_label = f"EVENT {i:02d}"

            nodes.append(
                TraceNode(
                    stage=stage_label,
                    title=title[:40],
                    detail=detail,
                )
            )
        return nodes

    # 5. Last-resort fallback for plain text paragraphs (capped at 4)
    sections = [
        _clean_markdown(s)
        for s in answer.split("\n\n")
        if len(_clean_markdown(s)) > 25
        and not any(s.lower().startswith(bad) for bad in _IGNORED_META_TITLES)
    ][:4]

    total_s = len(sections)
    for i, s in enumerate(sections):
        if i == 0:
            stage_label = "PRIMARY TRIGGER"
        elif i == total_s - 1:
            stage_label = "FINAL OUTCOME"
        else:
            stage_label = f"EVENT {i:02d}"

        nodes.append(
            TraceNode(
                stage=stage_label,
                title=s.split(".")[0][:40] or f"Event {i+1}",
                detail=s,
            )
        )

    return nodes

def build_temporal_trace(answer: str) -> list[TraceNode]:
    """2. TEMPORAL_EVOLUTION: Clean milestones with gap omission and synthesis tail."""
    nodes = []

    def is_junk_or_gap(text: str) -> bool:
        t = text.lower()
        gap_phrases = [
            "knowledge graph provides no",
            "consequently, any detailed",
            "data gap",
            "no specific entry",
            "absent from",
            "not documented",
            "what this means for you",
            "data gaps",
            "bottom line (as of",
            "max verstappen-",
        ]
        return any(p in t for p in gap_phrases)

    table_data = _parse_table(answer)
    if table_data:
        for title, detail in table_data:
            if is_junk_or_gap(title) or is_junk_or_gap(detail):
                continue
            m = re.search(r"\b(19\d{2}|20\d{2}|Lap\s*\d+)\b", title, re.I)
            tag = m.group(1).upper() if m else "STAGE"
            clean_title = re.sub(
                r"^[–\-:\s]*" + tag + r"[–\-:\s]*", "", title, flags=re.I
            ).strip()
            clean_title = clean_title.split("–")[0].split("-")[0].split(":")[0].strip()

            if not clean_title or clean_title.strip() == tag:
                first_sentence = detail.split(".")[0].strip(" •-*")
                clean_title = first_sentence.split("–")[0].split("-")[0].strip()

            nodes.append(
                TraceNode(
                    stage=tag,
                    title=clean_title[:32] or tag,
                    detail=_clean_markdown(detail),
                )
            )

    if not nodes:
        list_data = _parse_list(answer)
        for title, detail in list_data:
            if is_junk_or_gap(title) or is_junk_or_gap(detail):
                continue
            m = re.search(
                r"\b(19\d{2}|20\d{2}|Lap\s*\d+|Mid-\d{4}|Late\s*\d{4})\b",
                title,
                re.I,
            )
            tag = m.group(1).upper() if m else "STAGE"
            clean_title = re.sub(
                r"^[–\-:\s]*" + tag + r"[–\-:\s]*", "", title, flags=re.I
            ).strip()
            clean_title = clean_title.split("–")[0].split("-")[0].split(":")[0].strip()

            if not clean_title or clean_title.strip() == tag:
                first_sentence = detail.split(".")[0].strip(" •-*")
                clean_title = first_sentence.split("–")[0].split("-")[0].strip()

            nodes.append(
                TraceNode(
                    stage=tag,
                    title=clean_title[:32] or tag,
                    detail=_clean_markdown(detail),
                )
            )

    bl_match = re.search(
        r"(?:Bottom line:?|Summary:?)(.*?)(?:\n\n|\Z)",
        answer,
        re.DOTALL | re.IGNORECASE,
    )
    if bl_match:
        bl_text = _clean_markdown(bl_match.group(1))
        if len(bl_text) > 25:
            nodes.append(
                TraceNode(
                    stage="SUMMARY",
                    title="Synthesized Trajectory",
                    detail=bl_text,
                )
            )

    return nodes or build_causal_trace(answer)

def build_epistemic_trace(answer: str) -> list[TraceNode]:
    """3. EPISTEMIC_SHIFT: Initial Narrative -> Revelation -> Revised Reality."""

    def clean_cell(text: str) -> str:
        text = _clean_markdown(text)
        lines = [line.strip().strip("|") for line in text.split("\n")]
        filtered = [l for l in lines if l and not all(c in "-: |" for c in l)]
        return "\n".join(filtered)

    table_data = _parse_table(answer)
    if len(table_data) >= 3:
        stages = [
            ("INITIAL NARRATIVE", "Contemporary Belief"),
            ("REVELATION CATALYST", "Discovery / Settlement"),
            ("REVISED REALITY", "Historical Consensus"),
        ]
        return [
            TraceNode(
                stage=stages[i][0],
                title=stages[i][1],
                detail=clean_cell(table_data[i][1]),
            )
            for i in range(3)
        ]

    sections = [s.strip() for s in answer.split("\n\n") if s.strip()]
    narrative_text, catalyst_text, reality_text = "", "", ""

    for s in sections:
        sl = s.lower()
        if (
            any(
                k in sl
                for k in [
                    "initially",
                    "believed",
                    "public",
                    "rival",
                    "contemporary",
                    "at the time",
                ]
            )
            and not narrative_text
        ):
            narrative_text = s
        elif (
            any(
                k in sl
                for k in [
                    "revelation",
                    "settlement",
                    "investigation",
                    "inquiry",
                    "uncovered",
                    "fia",
                ]
            )
            and not catalyst_text
        ):
            catalyst_text = s
        elif (
            any(
                k in sl
                for k in [
                    "revised",
                    "reality",
                    "later",
                    "truth",
                    "today",
                    "outcome",
                    "gap",
                ]
            )
            and not reality_text
        ):
            reality_text = s

    clean_paras = [
        _clean_markdown(p)
        for p in sections
        if len(_clean_markdown(p)) > 30 and not p.startswith("#")
    ]
    if not narrative_text and len(clean_paras) > 0:
        narrative_text = clean_paras[0]
    if not catalyst_text and len(clean_paras) > 1:
        catalyst_text = clean_paras[1]
    if not reality_text and len(clean_paras) > 2:
        reality_text = clean_paras[2]

    return [
        TraceNode(
            stage="INITIAL NARRATIVE",
            title="Contemporary Belief",
            detail=clean_cell(
                narrative_text or "No contemporary claims indexed."
            ),
        ),
        TraceNode(
            stage="REVELATION CATALYST",
            title="Discovery / Settlement",
            detail=clean_cell(
                catalyst_text or "Settlement / disclosure pending backfill."
            ),
        ),
        TraceNode(
            stage="REVISED REALITY",
            title="Historical Consensus",
            detail=clean_cell(reality_text or "Current verified status."),
        ),
    ]

def build_comparative_trace(answer: str) -> list[TraceNode]:
    """4. COMPARATIVE_TRAJECTORY: Multi-entity comparison labeled as SUBJECT A, SUBJECT B, etc."""
    # Priority 1: Check if markdown table has timeline rows and entity columns
    # Priority 2: Standard row-based table or markdown list
    col_data = _parse_table_columns(answer)
    raw_data = col_data or _parse_table(answer) or _parse_list(answer)

    # Filter out reasoning/meta junk and limit to 5 comparison items max
    clean_data = [
        (t, d) for t, d in raw_data if not _is_meta_junk(t, d) and len(d) > 10
    ][:5]

    letters = string.ascii_uppercase  # 'A', 'B', 'C', 'D', 'E'...

    if clean_data:
        nodes = []
        total = len(clean_data)
        for i, (title, detail) in enumerate(clean_data):
            # Check if the final node is an explicit divergence, summary, or turning point
            is_delta = (i == total - 1) and any(
                k in title.lower()
                for k in [
                    "delta",
                    "verdict",
                    "divergence",
                    "comparison",
                    "summary",
                    "why it mattered",
                    "turning point",
                ]
            )

            stage_label = (
                "TRAJECTORY DELTA" if is_delta else f"SUBJECT {letters[i]}"
            )

            nodes.append(
                TraceNode(
                    stage=stage_label,
                    title=title[:80],
                    detail=detail,
                )
            )
        return nodes

    # Priority 3: Paragraph fallback
    sections = [
        _clean_markdown(s)
        for s in answer.split("\n\n")
        if len(_clean_markdown(s)) > 30
        and not _is_meta_junk(s[:30], s)
        and not s.strip().startswith("#")
    ][:5]

    if sections:
        nodes = []
        total = len(sections)
        for i, s in enumerate(sections):
            is_delta = (i == total - 1) and any(
                k in s[:40].lower()
                for k in [
                    "delta",
                    "verdict",
                    "divergence",
                    "comparison",
                    "summary",
                    "why it mattered",
                ]
            )

            stage_label = (
                "TRAJECTORY DELTA" if is_delta else f"SUBJECT {letters[i]}"
            )

            nodes.append(
                TraceNode(
                    stage=stage_label,
                    title=s.split(".")[0][:40] or f"Subject {letters[i]}",
                    detail=s,
                )
            )
        return nodes

    return build_causal_trace(answer)

def build_transition_trace(answer: str) -> list[TraceNode]:
    """5. TRANSITION_INFLECTION_POINT: Pre-inflection, Catalyst, Post-inflection."""
    # Priority 1: Check markdown table, but dynamically find the pivot row
    table_data = _parse_table(answer)
    clean_table = [(t, d) for t, d in table_data if not _is_meta_junk(t, d) and len(d) > 8]

    if len(clean_table) >= 3:
        # Detect which row contains the catalyst/turning keywords
        pivot_idx = 1  # Default to middle row
        for idx, (title, detail) in enumerate(clean_table):
            combined = f"{title} {detail}".lower()
            if any(k in combined for k in ["undisputed", "champion", "inflection", "turning point", "catalyst", "leader"]):
                pivot_idx = idx
                break

        # Bound indices so we get a clean pre -> pivot -> post triad
        if pivot_idx == 0:
            pre_idx, piv_idx, post_idx = 0, min(1, len(clean_table) - 1), min(2, len(clean_table) - 1)
        elif pivot_idx >= len(clean_table) - 1:
            pre_idx, piv_idx, post_idx = len(clean_table) - 3, len(clean_table) - 2, len(clean_table) - 1
        else:
            pre_idx, piv_idx, post_idx = pivot_idx - 1, pivot_idx, pivot_idx + 1

        selected_indices = [pre_idx, piv_idx, post_idx]
        stages = ["PRE-INFLECTION", "PIVOT CATALYST", "POST-INFLECTION"]

        return [
            TraceNode(
                stage=stages[i],
                title=clean_table[row_idx][0][:45],
                detail=clean_table[row_idx][1],
            )
            for i, row_idx in enumerate(selected_indices)
        ]

    # Priority 2: Narrative Sections (Filtered against meta-junk / disclaimers)
    sections = [
        s.strip() for s in answer.split("\n\n")
        if s.strip() and not _is_meta_junk(s[:40], s)
    ]
    pre_text, pivot_text, post_text = "", "", ""

    for s in sections:
        s_lower = s.lower()
        if not pre_text and any(k in s_lower for k in ["before", "pre-", "status quo", "prior", "initial"]):
            pre_text = s
        elif not pivot_text and any(k in s_lower for k in ["inflection", "catalyst", "turning point", "decisive"]):
            pivot_text = s
        elif not post_text and any(k in s_lower for k in ["after", "post-", "subsequent", "outcome", "new reality"]):
            post_text = s

    clean_paras = [
        _clean_markdown(p)
        for p in sections
        if len(_clean_markdown(p)) > 30 and not p.startswith("#") and not _is_meta_junk(p[:40], p)
    ]
    if not pre_text and len(clean_paras) > 0:
        pre_text = clean_paras[0]
    if not pivot_text and len(clean_paras) > 1:
        pivot_text = clean_paras[1]
    if not post_text and len(clean_paras) > 2:
        post_text = clean_paras[2]

    def extract_clean_title(text: str, default: str) -> str:
        clean = _clean_markdown(text)
        first_line = clean.split("\n")[0].split(".")[0].strip()
        first_line = re.sub(
            r"^(pre-inflection|pivot catalyst|post-inflection|before|after|bottom line|decisive turning point):\s*",
            "",
            first_line,
            flags=re.IGNORECASE,
        )
        if 4 < len(first_line) <= 45:
            return first_line
        return default

    return [
        TraceNode(
            stage="PRE-INFLECTION",
            title=extract_clean_title(pre_text, "Baseline / Prior State"),
            detail=_clean_markdown(pre_text),
        ),
        TraceNode(
            stage="PIVOT CATALYST",
            title=extract_clean_title(pivot_text, "Decisive Turning Point"),
            detail=_clean_markdown(pivot_text),
        ),
        TraceNode(
            stage="POST-INFLECTION",
            title=extract_clean_title(post_text, "Aftermath & New Reality"),
            detail=_clean_markdown(post_text),
        ),
    ]

def build_lineage_trace(answer: str) -> list[TraceNode]:
    """6. MULTIHOP_LINEAGE: Stepped breadcrumb chain across succession hops."""
    clean_source = re.split(
        r"(?i)\n\s*(?:###?\s*|\*\*)?(?:Data Gaps?|What the KG does not|Bottom line|Notes?:?|Caveats?:?)",
        answer,
    )[0].strip()

    lines = clean_source.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*(?:\d+[\.\)]|[-*•])\s+", line):
            start_idx = i
            break
    core_text = "\n".join(lines[start_idx:])

    # 1. Arrow-delimited chains (A -> B -> C)
    arrow_match = re.search(
        r"((?:[A-Za-z0-9\(\)\s\-]+\s*(?:->|→)\s*){2,}[A-Za-z0-9\(\)\s\-]+)",
        core_text,
    )
    if arrow_match:
        hops = [
            h.strip(" -•*")
            for h in re.split(r"->|→", arrow_match.group(1))
            if h.strip()
        ]
        total = len(hops)
        if total >= 2:
            return [
                TraceNode(
                    stage="ORIGIN" if i == 0 else ("DESTINATION" if i == total - 1 else f"HOP {i:02d}"),
                    title=_clean_markdown(hop)[:45],
                    detail=f"Lineage step {i + 1} of {total}: {_clean_markdown(hop)}",
                )
                for i, hop in enumerate(hops)
            ]

    # Helper to build a clean title and preserve full detail without sentence clipping
    def _extract_hop_node(stage: str, raw_title: str, raw_detail: str) -> TraceNode:
        full_text = f"{raw_title}: {raw_detail}" if raw_detail else raw_title
        cleaned_detail = _clean_markdown(full_text).lstrip("•-* \t")

        # Strip generic numbers / prefixes
        cleaned_title = re.sub(
            r"^(?:hop\s*\d+|step\s*\d+|\d+[\.\)]|\b(?:19|20)\d{2}\b)[:\s\-–]*",
            "",
            raw_title,
            flags=re.IGNORECASE,
        ).strip()

        # If title collapsed into an empty string or just a year/date, pull from the sentence
        if not cleaned_title or len(cleaned_title) < 4:
            first_sent = cleaned_detail.split(".")[0]
            first_sent = re.sub(r"^(?:late|early|mid)?[-\s]*(?:19|20)\d{2}[:\s\-–]*", "", first_sent, flags=re.IGNORECASE)
            cleaned_title = first_sent.strip()

        # Clean dashes/hyphens
        cleaned_title = cleaned_title.split("–")[0].split("-")[0].strip()

        # Capitalize initial letter if clipped
        final_detail = cleaned_detail
        if final_detail and final_detail[0].islower():
            final_detail = final_detail[0].upper() + final_detail[1:]

        return TraceNode(
            stage=stage,
            title=(cleaned_title[:45] or "Intermediate Hop"),
            detail=final_detail,
        )

    # 2. Markdown Table Lineage
    table_data = _parse_table(core_text)
    if table_data:
        total = len(table_data)
        nodes = []
        for i, (title, detail) in enumerate(table_data):
            stage = "ORIGIN" if i == 0 else ("DESTINATION" if i == total - 1 else f"HOP {i:02d}")
            nodes.append(_extract_hop_node(stage, title, detail))
        return nodes

    # 3. Bulleted / Numbered List Lineage
    list_items = _parse_list(core_text)
    if list_items:
        total = len(list_items)
        nodes = []
        for i, (title, detail) in enumerate(list_items):
            stage = "ORIGIN" if i == 0 else ("DESTINATION" if i == total - 1 else f"HOP {i:02d}")
            nodes.append(_extract_hop_node(stage, title, detail))
        return nodes

    # 4. Paragraph Fallback
    paragraphs = [
        _clean_markdown(p)
        for p in core_text.split("\n\n")
        if len(_clean_markdown(p)) > 30 and not p.strip().startswith("#")
    ]
    total = len(paragraphs)
    if total >= 2:
        return [
            TraceNode(
                stage="ORIGIN" if i == 0 else ("DESTINATION" if i == total - 1 else f"HOP {i:02d}"),
                title=p.split(".")[0][:45],
                detail=p,
            )
            for i, p in enumerate(paragraphs[:5])
        ]

    # 5. Causal Trace Fallback
    base_nodes = build_causal_trace(answer)
    tot = len(base_nodes)
    for i, n in enumerate(base_nodes):
        n.stage = "ORIGIN" if i == 0 else ("DESTINATION" if i == tot - 1 else f"HOP {i:02d}")
    return base_nodes

def build_factual_trace(answer: str) -> list[TraceNode]:
    """7. FACTUAL_LOOKUP: Single verified telemetry card without generic title artifacts."""
    clean_source = re.split(
        r"(?i)\n\s*(?:###?\s*|\*\*)?(?:Data Gaps?|What the KG does not|Notes?:?)",
        answer,
    )[0].strip()

    clean = _clean_markdown(clean_source)

    lines = [
        re.sub(r"(?i)^(?:Answer|Result|Summary|Overview)[:\s\-]*", "", l).strip()
        for l in clean.split("\n")
        if l.strip() and not l.strip().lower() in ["answer", "result", "summary"]
    ]

    first_meaningful = (
        lines[0] if lines else "Telemetry Verification"
    )
    
    # Take up to the first period
    first_sent = first_meaningful.split(".")[0].strip()
    
    # Boundary-aware truncation to prevent mid-word cutting
    if len(first_sent) > 75:
        title = first_sent[:72].rsplit(" ", 1)[0] + "..."
    else:
        title = first_sent

    return [
        TraceNode(
            stage="CONFIRMED RECORD",
            title=title or "Telemetry Verification",
            detail=clean,
        )
    ]

def build_trace(archetype: str, answer: str) -> list[TraceNode]:
    """Master dispatcher mapping archetype name to its parser."""
    builders = {
        "CAUSAL_CONSEQUENCE_CHAIN": build_causal_trace,
        "TEMPORAL_EVOLUTION": build_temporal_trace,
        "EPISTEMIC_PERCEPTION_SHIFT": build_epistemic_trace,
        "COMPARATIVE_TRAJECTORY": build_comparative_trace,
        "TRANSITION_INFLECTION_POINT": build_transition_trace,
        "MULTIHOP_LINEAGE": build_lineage_trace,
        "FACTUAL_LOOKUP": build_factual_trace,
    }
    builder_fn = builders.get(archetype, build_causal_trace)
    return builder_fn(answer)


# ==============================================================================
# ANIMATION / STREAMING GENERATOR FOR REFLEX STATE
# ==============================================================================


async def animate_trace_stream(full_nodes: list[TraceNode], delay: float = 0.30):
    """
    Async generator yielding partial node states to simulate real-time graph assembly.
    Usage in your State handler:
        async for partial_nodes, selected in animate_trace_stream(nodes):
            self.trace_nodes = partial_nodes
            self.selected_node = selected
            yield
    """
    accumulated = []
    for node in full_nodes:
        accumulated.append(node)
        # Yield current list and automatically select the first node
        yield list(accumulated), accumulated[0]
        await asyncio.sleep(delay)


# ==============================================================================
# UI VISUAL GRAMMARS
# ==============================================================================


def render_trace_header(on_reconstruct) -> rx.Component:
    """Header bar with trace title and instant local re-parse button."""
    return rx.hstack(
        rx.text(
            "RECONSTRUCTION TRACE",
            font_size="0.75rem",
            font_weight="700",
            color="#666666",
            letter_spacing="0.05em",
        ),
        rx.button(
            "↻ RECONSTRUCT",
            size="1",
            variant="ghost",
            color_scheme="gray",
            font_size="0.65rem",
            padding="0.25rem 0.5rem",
            height="auto",
            cursor="pointer",
            on_click=on_reconstruct,
            _hover={"color": "#e10600", "background": "#141414"},
        ),
        justify="between",
        align="center",
        width="100%",
        margin_bottom="0.65rem",
    )

def _render_detail_panel(selected: TraceNode | None) -> rx.Component:
    """Interactive inspection drawer."""
    return rx.box(
        rx.cond(
            selected,
            rx.vstack(
                rx.badge(
                    selected.stage,
                    color_scheme="ruby",
                    variant="solid",
                    size="1",
                ),
                rx.heading(
                    selected.title,
                    size="3",
                    color="#ffffff",
                    margin_top="0.4rem",
                ),
                rx.divider(border_color="#242424", margin_y="0.75rem"),
                rx.box(
                    rx.markdown(
                        selected.detail,
                        font_size="0.85rem",
                        line_height="1.7",
                        white_space="pre-line",
                        color="#cccccc",
                    ),
                    max_height="220px",
                    overflow_y="auto",
                    width="100%",
                    padding_right="0.5rem",
                    style={
                        "&::-webkit-scrollbar": {"width": "4px"},
                        "&::-webkit-scrollbar-thumb": {
                            "background": "#2a2a2a",
                            "borderRadius": "4px",
                        },
                        "&::-webkit-scrollbar-thumb:hover": {
                            "background": "#e10600",
                        },
                    },
                ),
                align="start",
                padding="1.25rem",
                background="#111111",
                border="1px solid #282828",
                border_top="3px solid #e10600",
                border_radius="6px",
                width="100%",
            ),
            rx.box(
                rx.text(
                    "Select any milestone along the trace to inspect telemetry.",
                    font_size="0.8rem",
                    color="#666666",
                    font_style="italic",
                ),
                padding="2rem 1.25rem",
                border="1px dashed #222222",
                border_radius="6px",
                text_align="center",
                width="100%",
            ),
        ),
        width="100%",
    )

def render_causal_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Vertical Domino Chain with connected spine rail, elevation, and active highlight."""
    return rx.hstack(
        rx.box(
            rx.vstack(
                rx.foreach(
                    nodes,
                    lambda node: rx.hstack(
                        rx.box(
                            rx.box(
                                width="7px",
                                height="7px",
                                border_radius="50%",
                                background="#e10600",
                                box_shadow="0 0 8px #e10600",
                            ),
                            display="flex",
                            align_items="center",
                            justify_content="center",
                            width="18px",
                            height="18px",
                            border_radius="50%",
                            background="#1a0000",
                            border="1px solid #e10600",
                            flex_shrink=0,
                        ),
                        rx.vstack(
                            rx.badge(
                                node.stage,
                                color_scheme="ruby",
                                size="1",
                                variant="outline",
                                font_family="monospace",
                            ),
                            rx.text(
                                node.title,
                                font_size="0.875rem",
                                font_weight="600",
                                color="#ffffff",
                            ),
                            align="start",
                            spacing="1",
                            cursor="pointer",
                            padding="0.55rem 0.85rem",
                            border_radius="4px",
                            background=rx.cond(
                                selected
                                & (selected.stage == node.stage)
                                & (selected.title == node.title),
                                "#1a1a1a",
                                "#121212",
                            ),
                            border=rx.cond(
                                selected
                                & (selected.stage == node.stage)
                                & (selected.title == node.title),
                                "1px solid #e10600",
                                "1px solid #222222",
                            ),
                            width="100%",
                            _hover=_HOVER_ELEVATION,
                            on_click=lambda: on_select(node),
                        ),
                        align="start",
                        spacing="3",
                        width="100%",
                        padding_y="0.3rem",
                    ),
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            position="relative",
            width="55%",
            border_left="2px solid #282828",
            padding_left="1rem",
            margin_left="0.75rem",
        ),
        _render_detail_panel(selected),
        width="100%",
        spacing="5",
        align="start",
    )

def render_temporal_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Multi-row timeline flow with auto-wrapping, hiding the arrow on the final card."""
    return rx.vstack(
        rx.flex(
            rx.foreach(
                nodes,
                lambda node, index: rx.hstack(
                    rx.box(
                        rx.badge(
                            node.stage,
                            color_scheme="ruby",
                            size="1",
                            variant="surface",
                            font_family="monospace",
                            margin_bottom="0.25rem",
                        ),
                        rx.text(
                            node.title,
                            font_size="0.82rem",
                            font_weight="600",
                            color="#ffffff",
                            no_of_lines=2,
                        ),
                        background=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "#1f1414",
                            "#121212",
                        ),
                        border=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "1px solid #e10600",
                            "1px solid #242424",
                        ),
                        border_radius="6px",
                        padding="0.65rem 0.85rem",
                        width="160px",
                        min_height="72px",
                        cursor="pointer",
                        _hover=_HOVER_ELEVATION,
                        on_click=lambda: on_select(node),
                    ),
                    # Reactive check: hide arrow on the terminal card
                    rx.cond(
                        index < (nodes.length() - 1),
                        rx.icon(
                            tag="arrow_right",
                            size=14,
                            color="#666666",
                            flex_shrink=0,
                        ),
                        rx.fragment(),
                    ),
                    align="center",
                    spacing="2",
                ),
            ),
            flex_wrap="wrap",
            gap="2",
            align="center",
            width="100%",
            padding_bottom="0.5rem",
        ),
        _render_detail_panel(selected),
        width="100%",
        spacing="4",
        align="start",
    )

def render_epistemic_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Dual-Horizon split cards with click selection and hover elevation."""
    return rx.vstack(
        rx.grid(
            rx.foreach(
                nodes,
                lambda node: rx.box(
                    rx.badge(
                        node.stage,
                        color_scheme="ruby",
                        variant="surface",
                        size="1",
                    ),
                    rx.heading(
                        node.title, size="2", color="#ffffff", margin_top="0.35rem"
                    ),
                    # REMOVE or LIMIT node.detail here so the top card stays compact:
                    # rx.markdown(node.detail, ...)  <-- Removing this avoids the duplicate text!
                    padding="1rem",
                    background=rx.cond(
                        selected
                        & (selected.stage == node.stage)
                        & (selected.title == node.title),
                        "#18181b",
                        "#111111",
                    ),
                    border=rx.cond(
                        selected
                        & (selected.stage == node.stage)
                        & (selected.title == node.title),
                        "1px solid #e10600",
                        "1px solid #242424",
                    ),
                    border_radius="4px",
                    cursor="pointer",
                    on_click=lambda: on_select(node),
                    _hover=_HOVER_ELEVATION,
                ),
            ),
            columns="repeat(auto-fit, minmax(220px, 1fr))",
            spacing="3",
            width="100%",
        ),
        rx.box(
            _render_detail_panel(selected), 
            width="100%",
            margin_top="0.5rem",
        ),
        width="100%",
    )

def render_comparative_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Parallel tracks showing comparative evolution."""
    return rx.hstack(
        rx.vstack(
            rx.foreach(
                nodes,
                lambda node: rx.box(
                    rx.badge(
                        node.stage,
                        variant="surface",
                        color_scheme=rx.cond(
                            node.stage == "TRAJECTORY DELTA", "ruby", "gray"
                        ),
                        size="1",
                    ),
                    rx.text(
                        node.title,
                        font_size="0.85rem",
                        font_weight="600",
                        color="#ffffff",
                        margin_top="0.25rem",
                        no_of_lines=1,
                    ),
                    padding="0.75rem",
                    background=rx.cond(
                        selected
                        & (selected.stage == node.stage)
                        & (selected.title == node.title),
                        "#18181b",
                        "#111111",
                    ),
                    border_left=rx.cond(
                        selected
                        & (selected.stage == node.stage)
                        & (selected.title == node.title),
                        "3px solid #e10600",
                        "3px solid #333333",
                    ),
                    border_radius="2px",
                    cursor="pointer",
                    on_click=lambda: on_select(node),
                    width="100%",
                    _hover=_HOVER_ELEVATION,
                ),
            ),
            spacing="2",
            width="45%",
            flex_shrink=0,
        ),
        _render_detail_panel(selected),
        width="100%",
        spacing="4",
        align="start",
    )

def render_transition_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Hourglass Pivot: Pre-State -> Center Pivot -> Post-State."""
    return rx.hstack(
        rx.vstack(
            rx.foreach(
                nodes,
                lambda node: rx.hstack(
                    rx.text("▼", font_size="0.65rem", color="#e10600"),
                    rx.box(
                        rx.badge(node.stage, size="1", variant="outline"),
                        rx.text(
                            node.title,
                            font_size="0.85rem",
                            font_weight="600",
                            color="#ffffff",
                        ),
                        padding="0.4rem 0.65rem",
                        border_radius="4px",
                        background=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "#18181b",
                            "transparent",
                        ),
                        border=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "1px solid #e10600",
                            "1px solid transparent",
                        ),
                        cursor="pointer",
                        on_click=lambda: on_select(node),
                        _hover=_HOVER_ELEVATION,
                        width="100%",
                    ),
                    spacing="3",
                    align="center",
                    padding_y="0.2rem",
                    width="100%",
                ),
            ),
            spacing="1",
            width="50%",
        ),
        _render_detail_panel(selected),
        width="100%",
        spacing="4",
        align="start",
    )

def render_lineage_grammar(
    nodes: list[TraceNode], selected: TraceNode | None, on_select
) -> rx.Component:
    """Stepped breadcrumb lineage path."""
    return rx.hstack(
        rx.vstack(
            rx.foreach(
                nodes,
                lambda node: rx.hstack(
                    rx.text(
                        "↳",
                        font_size="1rem",
                        color="#888888",
                        padding_left="4px",
                    ),
                    rx.box(
                        rx.text(
                            node.stage,
                            font_size="0.65rem",
                            color="#e10600",
                            font_weight="700",
                        ),
                        rx.text(
                            node.title,
                            font_size="0.85rem",
                            font_weight="600",
                            color="#f5f5f5",
                            no_of_lines=1,
                        ),
                        padding="0.5rem 0.75rem",
                        background=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "#1a1a1a",
                            "#111111",
                        ),
                        border=rx.cond(
                            selected
                            & (selected.stage == node.stage)
                            & (selected.title == node.title),
                            "1px solid #e10600",
                            "1px solid #222222",
                        ),
                        border_radius="4px",
                        width="100%",
                        cursor="pointer",
                        on_click=lambda: on_select(node),
                        _hover=_HOVER_ELEVATION,
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
            ),
            spacing="2",
            width="42%",
            flex_shrink=0,
        ),
        rx.box(
            _render_detail_panel(selected),
            width="58%",
        ),
        width="100%",
        spacing="4",
        align="start",
    )

def render_factual_grammar(nodes: list[TraceNode]) -> rx.Component:
    """Clean factual stat card with confirmed entity citation."""
    return rx.vstack(
        rx.foreach(
            nodes,
            lambda node: rx.box(
                rx.badge(
                    "CONFIRMED KNOWLEDGE GRAPH ENTITY",
                    color_scheme="green",
                    size="1",
                ),
                rx.heading(
                    node.title, size="3", color="#ffffff", margin_top="0.5rem"
                ),
                rx.markdown(
                    node.detail,
                    font_size="0.875rem",
                    color="#bbbbbb",
                    margin_top="0.5rem",
                    line_height="1.6",
                ),
                padding="1.25rem",
                background="#111111",
                border="1px solid #222222",
                border_radius="4px",
                width="100%",
            ),
        ),
        width="100%",
    )

def render_trace(
    archetype: str,
    nodes: list[TraceNode],
    selected: TraceNode | None,
    on_select_event,
) -> rx.Component:
    """Master Renderer routing archetype to its tailored visual grammar."""
    return rx.box(
        rx.cond(
            archetype == "CAUSAL_CONSEQUENCE_CHAIN",
            render_causal_grammar(nodes, selected, on_select_event),
            rx.cond(
                archetype == "TEMPORAL_EVOLUTION",
                render_temporal_grammar(nodes, selected, on_select_event),
                rx.cond(
                    archetype == "EPISTEMIC_PERCEPTION_SHIFT",
                    render_epistemic_grammar(nodes, selected, on_select_event),
                    rx.cond(
                        archetype == "COMPARATIVE_TRAJECTORY",
                        render_comparative_grammar(
                            nodes, selected, on_select_event
                        ),
                        rx.cond(
                            archetype == "TRANSITION_INFLECTION_POINT",
                            render_transition_grammar(
                                nodes, selected, on_select_event
                            ),
                            rx.cond(
                                archetype == "MULTIHOP_LINEAGE",
                                render_lineage_grammar(
                                    nodes, selected, on_select_event
                                ),
                                rx.cond(
                                    archetype == "FACTUAL_LOOKUP",
                                    render_factual_grammar(nodes),
                                    render_causal_grammar(
                                        nodes, selected, on_select_event
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        margin_top="0.5rem",
        width="100%",
    )
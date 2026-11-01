import os
import re
import time
import json
import httpx
import reflex as rx
from sqlmodel import SQLModel, Field, select, desc
import typing
from .traces import TraceNode, build_trace, animate_trace_stream, render_trace, render_trace_header, STICKY_SIDEBAR_STYLE

def get_styled_chassis_svg(active_component: str = "") -> str:
    path = os.path.join("assets", "schematics", "f1_car_sideview_blueprint.svg")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        svg = f.read()

    svg = re.sub(r'width="[^"]+"', 'width="100%"', svg, count=1)
    svg = re.sub(r'height="[^"]+"', 'height="100%"', svg, count=1)

    # Complete eradication of cyan:
    svg = svg.replace('#00ffff', '#e10600')
    svg = svg.replace('#06b6d4', '#e10600')
    svg = svg.replace('rgb(0, 255, 255)', '#e10600')
    svg = svg.replace('cyan', '#e10600')

    # Convert dark labels into stark white
    svg = svg.replace('fill="#000000"', 'fill="#ffffff"')
    svg = svg.replace('fill="black"', 'fill="#ffffff"')
    svg = svg.replace('stroke="#000000"', 'stroke="#3f3f46"')

    return svg

def get_styled_circuit_svg(circuit_slug: str) -> str:
    """Reads the track SVG and formats it for crisp dark-mode rendering."""
    path = os.path.join("assets", "circuits", f"{circuit_slug}.svg")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        svg = f.read()

    svg = re.sub(r'width="[^"]+"', 'width="100%"', svg, count=1)
    svg = re.sub(r'height="[^"]+"', 'height="100%"', svg, count=1)
    # Ensure track numbers/circles pop cleanly
    svg = svg.replace('fill="#000000"', 'fill="#A1A1AA"')
    svg = svg.replace('stroke="#000000"', 'stroke="#FFFFFF"')
    return svg

class BackfillTicket(SQLModel, table=True):
    id: typing.Optional[int] = Field(default=None, primary_key=True)
    ticket_code: str
    title: str
    detail: str
    votes: int = 1
    status: str = "queued" # "queued", "ingested", or "deleted"

class State(rx.State):
    is_dev: bool = False
    dev: str = ""
    query: str = ""
    answer: str = ""
    answer_preview: str = ""
    archetype: str = ""
    loading: bool = False
    answer_expanded: bool = False

    # Carousel HUD State
    is_canvas_open: bool = True
    active_slide_idx: int = 0
    available_slides: list[str] = []
    circuit_slug: str = "bahrain"
    circuit_css: str = ""
    chassis_css: str = ""
    radio_speaker: str = ""
    radio_message: str = ""
    penalty_title: str = ""
    penalty_incident: str = ""
    penalty_decision: str = ""
    telemetry_st: str = "338.4 KM/H"
    # Dynamic HUD Telemetry State
    circuit_turn_highlight: str = ""       # e.g. "TURN 3" or ""
    chassis_component_label: str = ""      # e.g. "REAR WING ASSEMBLY"
    chassis_status_label: str = ""         # e.g. "ACTIVE // HIGH DOWNFORCE"

    # Rate-Limiting & Devloper Bypass
    query_count: int = 0
    max_queries: int = 15
    first_query_time: float = 0.0
    cooldown_seconds: float = 3 * 3600 # 3 hours cooldown

    follow_up_query: str = ""

    # Trace State
    trace_nodes: list[TraceNode] = []
    selected_node: TraceNode | None = None
    
    @rx.var
    def queries_remaining(self) -> int:
        if self.is_dev:
            return 999
        now = time.time()
        # Auto-recharge if cooldown period has passed
        if self.first_query_time > 0 and (now - self.first_query_time) > self.cooldown_seconds:
            return self.max_queries
        return max(0, self.max_queries - self.query_count)
    
    @rx.var
    def time_until_reset_min(self) -> int:
        if self.first_query_time == 0:
            return 0
        now = time.time()
        elapsed = now - self.first_query_time
        if elapsed >= self.cooldown_seconds:
            return 0
        return max(1, int((self.cooldown_seconds - elapsed) // 60))
    
    @rx.var
    def quota_reached(self) -> bool:
        if self.is_dev:
            return False
        return self.queries_remaining <= 0

    # Live Paddock & Race Debrief Quick-Starts
    live_audit_queries: list[str] = [
        "Give me an end-to-end debrief of the latest Grand Prix: the race winner, key overtakes, major mechanical failures, and any steward penalties.",
        "What is the latest engineering controversy or tech talk in the paddock?",
        "Reconstruct the key strategic phases and pit stop calls from the recent race.",
    ]

    example_queries: list[str] = [
        # 1. Epistemic Perception Shift (Raw paddock drama & consensus flip)
        "Why did everyone say the macarena wing was fine until the FIA banned it?",

        # 2. Temporal Evolution (Fans tracking rule changes & test runs)
        "Why did they scrap that weird straight line aero mode during early 2026 testing?",

        # 3. Transition Inflection Point (Tactical heartbreak & specific lap moment)
        "What was the exact lap Ferrari ruined Leclerc with that software bug at Monza?",

        # 4. Causal Consequence Chain (Systemic failure & domino effect)
        "How did the timing screens dying cause a whole grid audit in SQ1?",

        # 5. Factual Lookup (Technical spec curiosity)
        "Is the new 2026 engine really a 50/50 electric split now?",

        # 6. Comparative Trajectory (Engineering battle between rivals)
        "Compare how Red Bull and McLaren approached the new active rear wings.",

        # 7. Multihop Lineage (Connecting fuel chemistry to turbo hardware)
        "Did the 100% sustainable fuels actually mess with the Mercedes turbo reliability?",
    ]

    def use_example(self, query: str):
        self.query = query

    def set_query(self, value: str):
        self.query = value

    def set_follow_up(self, value: str):
        self.follow_up_query = value

    async def submit_follow_up(self):
        """Copies the follow-up text into the primary query pipeline, clears the input, and runs investigation."""
        if not self.follow_up_query.strip():
            return
        self.query = self.follow_up_query
        self.follow_up_query = ""
        return State.investigate

    def handle_follow_up_key_down(self, key: str):
        if key == "Enter":
            return State.submit_follow_up

    def toggle_answer(self):
        self.answer_expanded = not self.answer_expanded

    def select_node(self, node: TraceNode):
        self.selected_node = node

    async def reconstruct_active_trace(self):
        """Instant local re-parse with live construction animation."""
        if not self.answer:
            return

        # Build nodes locally without making any LLM/API calls
        full_nodes = build_trace(self.archetype, self.answer)

        # Animate the construction step-by-step
        self.trace_nodes = []
        self.selected_node = None
        yield

        async for partial_nodes, selected in animate_trace_stream(full_nodes):
            self.trace_nodes = partial_nodes
            self.selected_node = selected
            yield
    
    @rx.event(background=True)
    async def investigate(self):
        if not self.query.strip() or self.quota_reached:
            return

        async with self:
            self.loading = True
            self.trace_nodes = []
            self.selected_node = None
            self.answer = ""
            self.answer_preview = ""
            self.archetype = ""

            # Deduct quota on run
            now = time.time()
            if not self.is_dev:
                if self.first_query_time == 0 or (now - self.first_query_time) > self.cooldown_seconds:
                    self.first_query_time = now
                    self.query_count = 0
                self.query_count += 1

        try:
            api_base = os.getenv("CHRONOGRAPH_API_URL", "http://127.0.0.1:8000")
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{api_base}/ask_stream", json={"query": self.query}) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        packet = json.loads(line)

                        # Event 1: Telemetry and traces arrived from Neo4j and HUD slides arrived
                        if packet.get("type") == "telemetry":
                            async with self:
                                self.archetype = packet.get("archetype", "FACTUAL_LOOKUP")
                                backend_traces = packet.get("traces", [])
                                self.trace_nodes = [TraceNode(**t) for t in backend_traces]
                                if self.trace_nodes:
                                    self.selected_node = self.trace_nodes[0]

                                # POPULATE HUD CANVAS FROM LLM PAYLOAD:
                                self.slides_payload = packet.get("hud_slides", [])
                                self.available_slides = [s.get("type", "slide") for s in self.slides_payload]
                                self.active_slide_idx = 0
                                self.is_canvas_open = True
                                self.answer_expanded = False

                        # Event 2: Answer text streaming token-by-token (live typing)
                        elif packet.get("type") == "token":
                            async with self:
                                self.answer += packet.get("content", "")

                                # Extract only the opening executive summary for preview
                                clean_parts = [
                                    p.strip()
                                    for p in self.answer.split("\n\n")
                                    if p.strip() and not p.strip().startswith("#")
                                ]
                                
                                if clean_parts:
                                    if len(clean_parts[0]) > 320:
                                        self.answer_preview = clean_parts[0][:320] + "..."
                                    elif len(clean_parts) > 1:
                                        self.answer_preview = clean_parts[0] + "..."
                                    else:
                                        self.answer_preview = clean_parts[0]
                                else:
                                    self.answer_preview = self.answer[:320]

                    # # Trigger HUD parser once the investigation text is complete
                    # async with self:
                    #     if self.answer:
                    #         self.update_canvas_debrief(self.answer)

        except Exception as e:
            import traceback
            traceback.print_exc()
            async with self:
                self.archetype = "SYSTEM_BUSY"
                self.answer = "**Couldn't complete that investigation.** Please try again shortly."
                self.answer_preview = self.answer
        finally:
            async with self:
                self.loading = False

    def handle_key_down(self, key: str):
        if key == "Enter":
            return State.investigate()
        
    slides_payload: list[dict] = []

    @rx.var
    def current_slide(self) -> dict:
        if self.slides_payload and 0 <= self.active_slide_idx < len(self.slides_payload):
            return self.slides_payload[self.active_slide_idx]
        return {}

    @rx.var
    def current_slide_type(self) -> str:
        # Check explicit type first
        t = str(self.current_slide.get("type", "")).lower().strip()
        if t in ["circuit", "chassis", "penalty", "radio"]:
            return t

        # Smart fallback based on whatever fields the LLM actually returned:
        badge = str(self.current_slide.get("badge_title", "")).lower()
        
        if "circuit" in t or "slug" in self.current_slide or "focus_turns" in self.current_slide:
            return "circuit"
        if "chassis" in t or "team" in self.current_slide or "focus_element" in self.current_slide or "spec" in badge:
            return "chassis"
        if "penalty" in t or "directive" in t or "ruling" in t or "decision" in self.current_slide or "incident" in self.current_slide or "directive" in badge:
            return "penalty"
        if "radio" in t or "speaker" in self.current_slide or "message" in self.current_slide:
            return "radio"

        return "fallback"

    @rx.var
    def current_badge_title(self) -> str:
        return self.current_slide.get("badge_title", "PIT WALL HUD")

    def set_slide(self, index: int):
        self.active_slide_idx = index
    
    def next_slide(self):
        if len(self.available_slides) > 0:
            self.active_slide_idx = (self.active_slide_idx + 1) % len(self.available_slides)

    def prev_slide(self):
        if len(self.available_slides) > 0:
            self.active_slide_idx = (self.active_slide_idx - 1 + len(self.available_slides)) % len(self.available_slides)

   
    # def update_canvas_debrief(self, debrief_text: str):
    #     from .parser import analyze_debrief_for_carousel
    #     result = analyze_debrief_for_carousel(debrief_text)
    #     self.is_canvas_open = result["is_open"]
    #     self.slides_payload = result["slides"]
    #     self.available_slides = [s["type"] for s in result["slides"]]
    #     self.active_slide_idx = 0

    is_hud_expanded: bool = False

    def toggle_hud_expand(self):
        self.is_hud_expanded = not self.is_hud_expanded

    @rx.var
    def active_chassis_svg(self) -> str:
        return get_styled_chassis_svg()

    @rx.var
    def current_chassis_footer(self) -> str:
        team_str = self.current_slide.get("badge_title") or self.current_slide.get("team") or "GEN-3 SPEC"
        return f"CHASSIS // {team_str}"

    @rx.var
    def active_circuit_svg(self) -> str:
        # Pulls the slug of the slide currently in view
        slug = self.current_slide.get("slug", "bahrain")
        return get_styled_circuit_svg(slug)

    @rx.var
    def active_circuit_css(self) -> str:
        """Dynamically generates glowing SVG CSS for whichever turns the current slide highlights."""
        if self.current_slide_type != "circuit":
            return ""
        
        turns = self.current_slide.get("focus_turns", [])
        if not turns:
            return ""
        
        selectors = [f"#turn-{t} circle, [id='turn-{t}'] circle" for t in turns]
        sel_text = [f"#turn-{t} text, [id='turn-{t}'] text" for t in turns]
        
        return f"""
        {', '.join(selectors)} {{
            stroke: #e10600 !important;
            stroke-width: 2.8px !important;
            fill: #e10600 !important;
            filter: drop-shadow(0 0 10px #e10600) !important;
            animation: f1-turn-pulse 1.8s infinite !important;
        }}
        {', '.join(sel_text)} {{
            fill: #ffffff !important;
            font-weight: 900 !important;
        }}
        """

    @rx.var
    def active_chassis_css(self) -> str:
        """Dynamically injects crimson glow on the exact CAD component + flap actuation."""
        if self.current_slide_type != "chassis":
            return ""
        
        focus_elem = self.current_slide.get("focus_element", "rear-wing-assembly")
        should_flap = self.current_slide.get("animate_flap", False)
        
        css_rules = [
            f"""
            #{focus_elem} path, #{focus_elem} rect, #{focus_elem} line {{
                stroke: #e10600 !important;
                stroke-width: 2.5px !important;
                filter: drop-shadow(0 0 8px rgba(225, 6, 0, 0.85)) !important;
            }}
            #{focus_elem} text {{
                fill: #ffffff !important;
                font-weight: 900 !important;
            }}
            """
        ]
        
        # Inject the keyframe animation ONLY if the LLM flagged active aero / revolving wing!
        if should_flap:
            css_rules.append("""
            @keyframes flap-swing-active {
              0%, 100% { transform: rotate(0deg); }
              42%, 62% { transform: rotate(-24deg); }
            }
            #active-flap {
              transform-origin: 816px 118px !important;
              animation: flap-swing-active 2.8s cubic-bezier(0.4, 0, 0.2, 1) infinite !important;
            }
            """)
            
        return "\n".join(css_rules)

    queue_version: int = 0
    upvoted_ids: list[str] = []
    queue_filter: str = "top"
    show_all_tickets: bool = False #Toggle between top10 vs all
    ticket_search_query: str = "" # live filter so users can find events before posting

    # Modal input fields
    suggest_modal_open: bool = False
    custom_event_title: str = ""
    custom_event_desc: str = ""

    # Page initialization to seed benchmark events
    def on_load(self):
        # 1. Seed defaults
        seed_default_tickets()

        # 2. Extract query parameter reliably on page mount
        secret = os.getenv("DEV_ACCESS_KEY", "smoothoperator")
        try:
            query_dict = self.router.url.query_parameters or {}
            if query_dict.get("dev") == secret:
                self.is_dev = True
        except Exception:
            pass

        # 3. Start background live sync across tabs
        return State.poll_queue_updates

    @rx.event(background=True)
    async def poll_queue_updates(self):
        """Continuously syncs all open browser tabs whenever SQLite data changes."""
        import asyncio
        last_seen_count = -1
        while True:
            await asyncio.sleep(2)
            try:
                with rx.session() as session:
                    # Quick checksum: total tickets + total votes
                    results = session.exec(select(BackfillTicket)).all()
                    current_checksum = sum(t.votes for t in results) + sum(1 for t in results if t.status == "ingested") + len(results)
                    
                if last_seen_count != current_checksum:
                    last_seen_count = current_checksum
                    async with self:
                        self.queue_version += 1
            except Exception:
                pass

    def open_suggest_modal(self):
        self.suggest_modal_open = True
        self.custom_event_title = ""
        self.custom_event_desc = ""

    def close_suggest_modal(self):
        self.suggest_modal_open = False
        self.custom_event_title = ""
        self.custom_event_desc = ""
    
    def toggle_show_all(self):
        self.show_all_tickets = not self.show_all_tickets
    
    def set_ticket_search(self, query: str):
        self.ticket_search_query = query.lower().strip()

    def set_queue_filter(self, val: str):
        self.queue_filter = val

    def set_custom_title(self, val: str):
        self.custom_event_title = val

    def set_custom_desc(self, val: str):
        self.custom_event_desc = val

    # Dynamic SQLite Query with Live Filters
    @rx.var
    def displayed_backfill_queue(self) -> list[dict[str, typing.Any]]:
        """Reads persisted tickets from SQLite and filters according to view state."""
        # Reactive trigger hook: re-evaluates whenever queue_version changes
        _ = self.queue_version

        with rx.session() as session:
            # Ensure table exists before executing select
            SQLModel.metadata.create_all(session.get_bind())

            stmt = select(BackfillTicket).where(BackfillTicket.status != "deleted")
            
            # Sort order: active queued tickets first, then sort by votes / recent
            if self.queue_filter == "recent":
                stmt = stmt.order_by(
                    BackfillTicket.status.desc(),  # "queued" comes before "ingested" alphabetically
                    desc(BackfillTicket.id),
                )
            else:
                stmt = stmt.order_by(
                    BackfillTicket.status.desc(),  # "queued" comes before "ingested"
                    desc(BackfillTicket.votes),
                    desc(BackfillTicket.id),
                )

            # Cap unless dev mode or user expanded 'show_all'
            if not self.is_dev and not self.show_all_tickets:
                stmt = stmt.limit(10)

            results = session.exec(stmt).all()
            
            items = [
                {
                    "id": t.ticket_code,
                    "title": t.title,
                    "detail": t.detail,
                    "votes": t.votes,
                    "db_id": t.id,
                    "status": t.status,
                }
                for t in results
            ]

            if self.ticket_search_query:
                items = [
                    t for t in items 
                    if self.ticket_search_query in t["title"].lower() 
                    or self.ticket_search_query in t["detail"].lower()
                ]

            return items

    # Upvoting (Persistent in SQLite)
    def upvote_ticket(self, ticket_id: str):
        if ticket_id in self.upvoted_ids:
            return
        with rx.session() as session:
            ticket = session.exec(
                select(BackfillTicket).where(BackfillTicket.ticket_code == ticket_id)
            ).first()
            if ticket and ticket.status != "ingested":
                ticket.votes += 1
                session.add(ticket)
                session.commit()
                self.upvoted_ids.append(ticket_id)
                self.queue_version += 1  # <-- Triggers immediate UI render

    # Submitting New Events
    def submit_backfill_event(self):
        title = self.custom_event_title.strip()
        desc = self.custom_event_desc.strip()
        if not title:
            return

        with rx.session() as session:
            count = session.exec(select(BackfillTicket)).all()
            next_code = f"#{len(count) + 56}"

            new_ticket = BackfillTicket(
                ticket_code=next_code,
                title=title[:50],
                detail=desc or "User-submitted historical milestone.",
                votes=1,
                status="queued",
            )
            session.add(new_ticket)
            session.commit()
            self.upvoted_ids.append(next_code)

        self.queue_version += 1  # <-- Triggers immediate UI render
        self.queue_filter = "recent"
        self.close_suggest_modal()
        return rx.toast.success(f"Ticket {next_code} logged to knowledge graph!")
    
    # Developer Controls
    def mark_ticket_ingested(self, ticket_id: str):
        print(f"🔍 [INGEST CLICKED] Seeking ticket_code: '{ticket_id}'")
        with rx.session() as session:
            ticket = session.exec(
                select(BackfillTicket).where(BackfillTicket.ticket_code == ticket_id)
            ).first()
            if ticket:
                ticket.status = "queued" if ticket.status == "ingested" else "ingested"
                session.add(ticket)
                session.commit()
                print(f"✅ [STATUS UPDATED] {ticket_id} -> {ticket.status}")
                self.queue_version += 1
            else:
                print(f"❌ [NOT FOUND] No record with code '{ticket_id}' in SQLite")
        return rx.toast.success(f"Status updated for {ticket_id}")

    def delete_ticket(self, ticket_id: str):
        print(f"🗑️ [DELETE CLICKED] Seeking ticket_code: '{ticket_id}'")
        with rx.session() as session:
            ticket = session.exec(
                select(BackfillTicket).where(BackfillTicket.ticket_code == ticket_id)
            ).first()
            if ticket:
                session.delete(ticket)
                session.commit()
                print(f"✅ [TICKET DELETED] {ticket_id}")
                self.queue_version += 1
            else:
                print(f"❌ [NOT FOUND] Could not delete '{ticket_id}'")
        return rx.toast.info(f"Ticket {ticket_id} removed.")
    
def seed_default_tickets():
    seeds = [
            ("#58", "2024 Austin: Norris vs Verstappen Turn 12 Penalty", "Track limits off-track overtake dispute, driving standards guidelines, and McLaren right-of-review petition.", 94, "queued"),
            ("#51", "2024 Hungary: McLaren 'Papaya Rules' Radio Drama", "Lando Norris pit-undercut sequence on Oscar Piastri and the 20-lap team radio standoff before the swap.", 81, "queued"),
            ("#46", "2024 Red Bull RB20 T-Tray Ride-Height Device", "Scrutineering dispute in Austin regarding front bib clearance adjustments in Parc Fermé under FIA seals.", 68, "queued"),
            ("#42", "2024 Baku: McLaren Rear-Wing 'Mini-DRS' Flexing", "High-speed slot gap deflection telemetry and FIA technical directive triggering low-downforce flap revisions.", 55, "ingested"),
            ("#38", "2025 Hamilton Ferrari Debut & Steering Drift", "Melbourne cockpit ergonomic shifts, differential transition mappings, and radio debrief telemetry.", 44, "queued"),
            ("#31", "2024 Belgian GP: Russell 1.5kg Underweight Disqualification", "One-stop strategy tyre wear calculation error, fuel drain protocol, and FIA document 45.", 37, "queued"),
            ("#29", "2024 Canadian GP: Variable Weather SC Delta Miscalculations", "Race Control delta enforcement, intermediate tyre cross-over timing, and pit exit lane crossing disputes.", 33, "queued"),
        ]
   
    try:
        with rx.session() as session:
            SQLModel.metadata.create_all(session.get_bind())

            existing = session.exec(select(BackfillTicket)).first()
            if not existing:
                for code, title, detail, votes, status in seeds:
                    session.add(BackfillTicket(
                        ticket_code=code,
                        title=title,
                        detail=detail,
                        votes=votes,
                        status=status
                    ))
                session.commit()
    except Exception as e:
        print(f"❌ Ticket Seeding Error: {e}")

def empty_telemetry_placeholder() -> rx.Component:
    """Telemetry placeholder rendered in the center column before queries run."""
    return rx.vstack(
        rx.html(
            """
            <svg width="340" height="90" viewBox="0 0 340 90" fill="none" xmlns="http://www.w3.org/2000/svg" style="opacity: 0.18; display: block; margin: auto;">
                <!-- Center Grid Crosshairs -->
                <line x1="170" y1="0" x2="170" y2="90" stroke="#71717A" stroke-width="0.8" stroke-dasharray="3 3"/>
                <line x1="20" y1="45" x2="320" y2="45" stroke="#71717A" stroke-width="0.8" stroke-dasharray="3 3"/>

                <!-- Front Wing & Nosecone Assembly -->
                <path d="M25 45 L75 39 L125 42 L145 45 L125 48 L75 51 Z" stroke="#E10600" stroke-width="1.2" fill="none"/>
                <path d="M12 28 L40 28 L50 38 L50 52 L40 62 L12 62" stroke="#FFFFFF" stroke-width="1.2" fill="none"/>
                <line x1="20" y1="24" x2="20" y2="66" stroke="#E10600" stroke-width="1.5"/>

                <!-- Front Suspension & Tyres -->
                <line x1="95" y1="41" x2="110" y2="18" stroke="#71717A" stroke-width="1"/>
                <line x1="115" y1="42" x2="110" y2="18" stroke="#71717A" stroke-width="1"/>
                <rect x="95" y="10" width="30" height="15" rx="2" stroke="#FFFFFF" stroke-width="1.2" fill="#141418"/>
                
                <line x1="95" y1="49" x2="110" y2="72" stroke="#71717A" stroke-width="1"/>
                <line x1="115" y1="48" x2="110" y2="72" stroke="#71717A" stroke-width="1"/>
                <rect x="95" y="65" width="30" height="15" rx="2" stroke="#FFFFFF" stroke-width="1.2" fill="#141418"/>

                <!-- Halo & Cockpit Opening -->
                <ellipse cx="185" cy="45" rx="24" ry="11" stroke="#E10600" stroke-width="1.2" fill="none"/>
                <circle cx="174" cy="45" r="4.5" stroke="#FFFFFF" stroke-width="1" fill="#27272A"/>
                <line x1="160" y1="45" x2="170" y2="45" stroke="#E10600" stroke-width="1.8"/>

                <!-- Sidepod Contours & Engine Spine -->
                <path d="M150 32 C 170 28, 220 30, 260 38 L 290 43 L 290 47 L 260 52 C 220 60, 170 62, 150 58 Z" stroke="#FFFFFF" stroke-width="1.2" fill="none"/>

                <!-- Rear Suspension & Wheels -->
                <line x1="265" y1="40" x2="278" y2="15" stroke="#71717A" stroke-width="1"/>
                <rect x="265" y="8" width="36" height="17" rx="2" stroke="#FFFFFF" stroke-width="1.2" fill="#141418"/>
                
                <line x1="265" y1="50" x2="278" y2="75" stroke="#71717A" stroke-width="1"/>
                <rect x="265" y="65" width="36" height="17" rx="2" stroke="#FFFFFF" stroke-width="1.2" fill="#141418"/>

                <!-- Rear Wing Assembly -->
                <path d="M305 22 L328 22 L332 37 L332 53 L328 68 L305 68" stroke="#FFFFFF" stroke-width="1.2" fill="none"/>
                <line x1="322" y1="20" x2="322" y2="70" stroke="#E10600" stroke-width="1.8"/>
            </svg>
            """
        ),
        rx.text(
            "TELEMETRY ENGINE STANDBY // AWAITING QUERY EXECUTION",
            font_size="0.75rem",
            font_family="monospace",
            letter_spacing="0.14em",
            color="rgba(255, 255, 255, 0.28)",
            margin_top="1rem",
        ),
        align="center",
        justify="center",
        padding_y="4rem",
        width="100%",
    )

def custom_blockquote(children):
    return rx.box(
        rx.box(
            children,
            color="#E2E8F0",
            font_size="0.95rem",
            font_style="italic",
            line_height="1.65",
            letter_spacing="0.01em",
        ),
        bg="rgba(255, 255, 255, 0.03)",          # Translucent dark-panel tint
        border_left="4px solid #E10600",           # F1 Red accent stripe
        border_radius="0px 8px 8px 0px",          # Rounded right edge
        padding="1rem 1.25rem",                    # Medium-style generous spacing
        margin_y="1.25rem",                        # Breathing room top and bottom
        width="100%",
    )

MARKDOWN_COMPONENT_MAP = {
    "blockquote": lambda *children: custom_blockquote(children),
}

def slide_circuit() -> rx.Component:
    return rx.box(
        # Dynamically injects red glowing turn styles for the CURRENT slide
        rx.html(f"<style>{State.active_circuit_css}</style>"),

        rx.html(
            State.active_circuit_svg,
            style={
                "width": "100%",
                "height": "100%",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
            }
        ),

        # Active Turn Callout Pin for this specific track
        rx.cond(
            State.current_slide.get("callout_label", "") != "",
            rx.hstack(
                rx.box(width="7px", height="7px", border_radius="50%", background="#e10600", class_name="f1-beacon"),
                rx.text(State.current_slide.get("callout_label", ""), font_size="8px", font_family="monospace", font_weight="800", color="#ffffff"),
                position="absolute",
                right="16px",
                top="16px",
                background="rgba(18, 10, 12, 0.94)",
                border="1px solid #e10600",
                border_radius="4px",
                padding="3px 8px",
                box_shadow="0 0 14px rgba(225, 6, 0, 0.6)",
                spacing="2",
                align="center",
                z_index="15",
            ),
            rx.fragment(),
        ),
        width="100%",
        height="100%",
        display="flex",
        align_items="center",
        justify_content="center",
        position="relative",
        padding="8px 24px",
    )

def slide_chassis() -> rx.Component:
    return rx.box(
        # Dynamically injects component glow & flap swing for this slide
        rx.html(f"<style>{State.active_chassis_css}</style>"),

        rx.html(
            State.active_chassis_svg,
            style={"width": "100%", "height": "100%", "display": "flex", "alignItems": "center", "justifyContent": "center"}
        ),

        # Dynamic Hotspot Callout Pin
        rx.hstack(
            rx.box(width="7px", height="7px", border_radius="50%", background="#e10600", class_name="f1-beacon"),
            rx.text(
                State.current_slide.get("callout_label", "AERODYNAMIC SPEC"),
                font_size="8px", 
                font_family="monospace", 
                font_weight="800", 
                color="#FFFFFF",
                letter_spacing="0.08em",
            ),
            position="absolute",
            right="16px",
            top="16px",
            background="rgba(18, 10, 12, 0.92)",
            border="1px solid #e10600",
            border_radius="4px",
            padding="3px 8px",
            spacing="2",
            align="center",
            z_index="15",
        ),

        # Bottom-left Team & Spec Indicator
        rx.text(
            State.current_chassis_footer,
            font_size="7px",
            font_family="monospace",
            color="#71717a",
            position="absolute",
            bottom="8px",
            left="12px",
        ),
        width="100%",
        height="100%",
        position="relative",
    )

def slide_radio() -> rx.Component:
    return rx.vstack(
        # Dispatch Header Badge
        rx.hstack(
            rx.box(width="6px", height="6px", border_radius="50%", background="#e10600", class_name="f1-beacon"),
            rx.text(State.current_slide.get("badge_title", "PIT WALL RADIO"), font_size="9px", font_family="monospace", color="#e10600", font_weight="800"),
            spacing="2",
            align="center",
        ),
        rx.box(
            rx.text(State.current_slide.get("speaker", "PIT WALL"), font_size="9.5px", color="#a1a1aa", font_weight="700", font_family="monospace"),
            rx.text(f'"{State.current_slide.get("message", "")}"', font_size="11.5px", color="#ffffff", font_weight="600", font_family="monospace", margin_y="6px"),
            padding="10px 12px",
            background="#0d0d11",
            border="1px solid #27272a",
            border_left="3px solid #e10600",
            border_radius="4px",
            width="100%",
        ),
        spacing="2",
        align_items="start",
        padding="12px",
        height="180px",
        justify="center",
        width="100%",
    )

def slide_penalty() -> rx.Component:
    return rx.vstack(
        # Top Category Header
        rx.hstack(
            rx.badge("FIA OFFICIAL", color_scheme="red", variant="solid", size="1", font_size="8px"),
            rx.text("STEWARDS INVESTIGATION // RULING", font_size="8px", font_family="monospace", color="#e10600", font_weight="700"),
            spacing="2",
            align="center",
            width="100%",
        ),
        # Inner Dossier Box
        rx.box(
            rx.vstack(
                rx.text(
                    State.current_slide["title"], 
                    font_size="8.5px", 
                    font_weight="800", 
                    font_family="monospace", 
                    color="#ffffff",
                    line_height="1.25",
                    width="100%",
                ),
                rx.badge(
                    State.current_slide["decision"], 
                    color_scheme="red", 
                    variant="surface", 
                    size="1", 
                    font_size="7px", 
                    font_weight="bold",
                    width="fit-content",
                ),
                rx.text(
                    State.current_slide["incident"],
                    font_size="8.5px",
                    font_family="monospace",
                    color="#e4e4e7",
                    line_height="1.35",
                    margin_y="2px",
                    width="100%",
                ),
                rx.hstack(
                    rx.text("VERDICT STATUS:", font_size="7px", font_family="monospace", color="#71717a"),
                    rx.text("OFFICIALLY RATIFIED", font_size="7px", font_family="monospace", color="#22c55e", font_weight="bold"),
                    spacing="1",
                    align="center",
                ),
                spacing="1",
                align_items="start",
                width="100%",
            ),
            padding="6px 10px",
            background="#0d0d11",
            border="1px solid #27272a",
            border_left="3px solid #e10600",
            border_radius="4px",
            width="100%",
        ),
        spacing="1",
        padding="8px 10px",
        height="100%",
        width="100%",
        justify="center",
        align_items="start",
    )

def slide_fallback() -> rx.Component:
    """Clear, conversational fallback when no track, car, or steward events apply."""
    return rx.vstack(
        rx.hstack(
            rx.box(
                width="5px",
                height="5px",
                border_radius="50%",
                background="#e10600",
                box_shadow="0 0 6px rgba(225, 6, 0, 0.8)",
            ),
            rx.text(
                "PADDOCK & STRATEGY REPORT",
                font_size="9px",
                font_family="monospace",
                color="#e10600",
                font_weight="700",
                letter_spacing="0.08em",
            ),
            spacing="1",
            align="center",
        ),
        rx.box(
            rx.text(
                "NO ON-TRACK TELEMETRY IN THIS QUERY",
                font_size="10.5px",
                font_weight="700",
                color="#ffffff",
                letter_spacing="0.03em",
            ),
            rx.text(
                "This investigation focuses on contracts, politics, or calendar governance — so there are no track turn highlights or aerodynamic parts to visualize.",
                font_size="9px",
                color="#a1a1aa",
                line_height="1.4",
                margin_y="4px",
            ),
            rx.text(
                "Check the center column for the multi-hop timeline.",
                font_size="8.5px",
                font_family="monospace",
                color="#71717a",
            ),
            padding="10px 12px",
            background="#0d0d11",
            border="1px solid #27272a",
            border_left="3px solid #e10600",
            border_radius="4px",
            width="100%",
        ),
        spacing="2",
        align_items="start",
        padding="10px",
        height="180px",
        justify="center",
        width="100%",
    )

def slide_idle() -> rx.Component:
    """Rendered on initial landing before any query has been executed."""
    return rx.vstack(
       # Side-View F1 Silhouette SVG
        rx.html(
            """
            <svg width="100%" height="98" viewBox="0 0 280 98" fill="none" xmlns="http://www.w3.org/2000/svg" style="display: block; margin: auto; user-select: none;">
                <!-- Card Backdrop & Technical Border Frame -->
                <rect x="1" y="1" width="278" height="96" rx="4" fill="#0D0D11" stroke="#27272A" stroke-width="1"/>
                <line x1="1" y1="1" x2="1" y2="97" stroke="#E10600" stroke-width="3"/>

                <!-- Header Metadata: Channel & Driver Callout -->
                <text x="12" y="14" fill="#A1A1AA" font-family="'JetBrains Mono', monospace" font-size="8.5" font-weight="700" letter-spacing="0.06em">VERSTAPPEN // 465.125 MHz</text>
                <text x="268" y="14" text-anchor="end" fill="#E10600" font-family="'JetBrains Mono', monospace" font-size="8" font-weight="800">LAS VEGAS GP</text>

                <!-- Centered Compact Audio Waveform (36px width) -->
                <g transform="translate(112, 18)">
                    <rect x="0" y="5" width="2" height="4" rx="0.5" fill="#E10600"/>
                    <rect x="4" y="3" width="2" height="8" rx="0.5" fill="#E10600"/>
                    <rect x="8" y="1" width="2" height="12" rx="0.5" fill="#FF2A24"/>
                    <rect x="12" y="4" width="2" height="6" rx="0.5" fill="#E10600"/>
                    <rect x="16" y="0" width="2" height="14" rx="0.5" fill="#FF2A24"/>
                    <rect x="20" y="3" width="2" height="8" rx="0.5" fill="#E10600"/>
                    <rect x="24" y="2" width="2" height="10" rx="0.5" fill="#FF2A24"/>
                    <rect x="28" y="4" width="2" height="6" rx="0.5" fill="#E10600"/>
                    <rect x="32" y="5" width="2" height="4" rx="0.5" fill="#E10600"/>
                </g>

                <!-- Graphic Quotation Marks & Verbatim Radio Line -->
                <text x="12" y="39" fill="#71717A" font-family="'JetBrains Mono', monospace" font-size="14" font-weight="900">“</text>
                
                <text x="24" y="44" fill="#FFFFFF" font-family="'JetBrains Mono', monospace" font-size="9.5" font-weight="700" font-style="italic">
                    What an unbelievable race, guys.
                </text>
                
                <text x="24" y="58" fill="#FFFFFF" font-family="'JetBrains Mono', monospace" font-size="9.5" font-weight="700" font-style="italic">
                    You know what that is?
                </text>
                
                <!-- Highlight Punchline -->
                <text x="24" y="74" fill="#FF2A24" font-family="'JetBrains Mono', monospace" font-size="11" font-weight="900" font-style="italic" letter-spacing="0.04em">
                    SIMPLY LOVELY, I TELL YOU THAT!
                </text>
                <text x="242" y="77" fill="#71717A" font-family="'JetBrains Mono', monospace" font-size="14" font-weight="900">”</text>

                <!-- Footer Audio Datum Line -->
                <line x1="12" y1="86" x2="268" y2="86" stroke="#1F1F23" stroke-width="0.8"/>
                <text x="12" y="93" fill="#52525B" font-family="'JetBrains Mono', monospace" font-size="6.5">AUDIO DECRYPT // PIT-TO-CAR INTERCEPT</text>
                <circle cx="264" cy="91" r="2" fill="#E10600"/>
            </svg>
            """
        ),
        rx.vstack(
            rx.hstack(
                rx.box(
                    width="6px",
                    height="6px",
                    border_radius="50%",
                    background="#22c55e",
                    box_shadow="0 0 7px #22c55e, 0 0 2px #22c55e",
                    flex_shrink=0,
                ),
                rx.text(
                    "AWAITING INVESTIGATION",
                    font_size="9px",
                    font_family="monospace",
                    font_weight="700",
                    color="#e4e4e7",
                    letter_spacing="0.1em",
                ),
                spacing="2",
                align="center",
                justify="center",
            ),
            rx.text(
                "Calibrated for live circuits, CAD upgrades, and FIA stewarding.",
                font_size="8px",
                font_family="monospace",
                color="#71717a",
                text_align="center",
            ),
            spacing="1",
            align="center",
            width="100%",
            margin_top="6px",
        ),
        spacing="1",
        justify="center",
        align="center",
        height="180px",
        width="100%",
        padding="8px",
    )

def chronograph_hud_deck() -> rx.Component:
    """Heads-Up Display with side navigation chevrons and unified header."""
    return rx.cond(
        State.is_canvas_open,
        rx.box(
            rx.html(
                """
                <style>
                @keyframes f1-pulse {
                    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(225, 6, 0, 0.7); opacity: 0.8; }
                    70% { transform: scale(1.05); box-shadow: 0 0 0 8px rgba(225, 6, 0, 0); opacity: 1; }
                    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(225, 6, 0, 0); opacity: 0.8; }
                }
                .f1-beacon {
                    animation: f1-pulse 1.8s infinite cubic-bezier(0.45, 0, 0.55, 1);
                }

                /* Maintain red stroke and crimson drop shadow while preserving character legibility */
                svg text, svg tspan {
                    fill: #ffffff !important;
                    stroke: #e10600 !important;
                    stroke-width: 0.65px !important;
                    paint-order: stroke fill !important;      /* Pushes stroke to the outer edge, protecting glyph interiors */
                    filter: drop-shadow(0 0 3px rgba(225, 6, 0, 0.7)) !important;
                    font-family: 'JetBrains Mono', monospace !important;
                    font-weight: 800 !important;
                    letter-spacing: 0.08em !important;
                }

                /* Silverstone Circuit Turn Markers */
                svg text.turn-number, svg text[id*="turn"] {
                    font-size: 11px !important;
                    stroke-width: 0.5px !important;
                }
                </style>
                """
            ),

            # 1. Single Unified Top HUD Bar
            rx.hstack(
                rx.hstack(
                    rx.box(
                        width="6px",
                        height="6px",
                        border_radius="50%",
                        background=rx.cond(State.answer != "", "#e10600", "#22c55e"),
                        box_shadow=rx.cond(State.answer != "", "0 0 8px #e10600", "0 0 8px #22c55e"),
                        flex_shrink=0,
                    ),
                    rx.text(
                        State.current_badge_title,
                        font_size="10px",
                        font_family="monospace",
                        color="#ffffff",
                        font_weight="800",
                        letter_spacing="0.12em",
                    ),
                    rx.cond(
                        State.is_hud_expanded,
                        rx.badge("EXPANDED", variant="surface", color_scheme="ruby", size="1", font_size="7px"),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),

                # Right Controls: Slide Counter & Expand/Collapse Toggle
                rx.hstack(
                    rx.cond(
                        State.available_slides.length() > 1,
                        rx.badge(
                            f"{State.active_slide_idx + 1} / {State.available_slides.length()}",
                            size="1",
                            variant="surface",
                            color_scheme="gray",
                            font_size="8px",
                            font_family="monospace",
                        ),
                        rx.fragment(),
                    ),
                    rx.button(
                        rx.cond(State.is_hud_expanded, "COLLAPSE ↘", "EXPAND ↗"),
                        on_click=State.toggle_hud_expand,
                        size="1",
                        variant="ghost",
                        color="#a1a1aa",
                        font_size="8px",
                        font_family="monospace",
                        padding="0 6px",
                        height="20px",
                        _hover={"color": "#ffffff", "background": "#1f1f23"},
                        cursor="pointer",
                    ),
                    spacing="2",
                    align="center",
                ),
                justify="between",
                padding="7px 12px",
                border_bottom="1px solid #1f1f23",
                background="#0c0c0e",
                width="100%",
                align="center",
            ),

            # 2. Viewport Body with Left & Right Side Chevrons
            rx.box(
                # LEFT SIDE CHEVRON BUTTON
                rx.cond(
                    (State.answer != "") & (State.available_slides.length() > 1),
                    rx.box(
                        rx.text("‹", font_size="16px", color="#71717a", line_height="1"),
                        on_click=State.prev_slide,
                        position="absolute",
                        left="6px",
                        top="50%",
                        transform="translateY(-50%)",
                        width="24px",
                        height="32px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        background="rgba(12, 12, 16, 0.7)",
                        border="1px solid #27272a",
                        border_radius="4px",
                        cursor="pointer",
                        z_index="25",
                        transition="all 0.15s ease",
                        _hover={"background": "#1f1f23", "color": "#ffffff", "border_color": "#e10600"},
                    ),
                    rx.fragment(),
                ),

                # SLIDE CONTENT
                rx.cond(
                    State.answer != "",
                    rx.cond(
                        State.current_slide_type == "circuit",
                        slide_circuit(),
                        rx.cond(
                            State.current_slide_type == "chassis",
                            slide_chassis(),
                            rx.cond(
                                State.current_slide_type == "radio",
                                slide_radio(),
                                rx.cond(
                                    State.current_slide_type == "penalty",
                                    slide_penalty(),
                                    slide_fallback(),
                                ),
                            ),
                        ),
                    ),
                    slide_idle(),
                ),

                # RIGHT SIDE CHEVRON BUTTON
                rx.cond(
                    (State.answer != "") & (State.available_slides.length() > 1),
                    rx.box(
                        rx.text("›", font_size="16px", color="#71717a", line_height="1"),
                        on_click=State.next_slide,
                        position="absolute",
                        right="6px",
                        top="50%",
                        transform="translateY(-50%)",
                        width="24px",
                        height="32px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        background="rgba(12, 12, 16, 0.7)",
                        border="1px solid #27272a",
                        border_radius="4px",
                        cursor="pointer",
                        z_index="25",
                        transition="all 0.15s ease",
                        _hover={"background": "#1f1f23", "color": "#ffffff", "border_color": "#e10600"},
                    ),
                    rx.fragment(),
                ),

                width="100%",
                height=rx.cond(State.is_hud_expanded, "270px", "195px"),  # <-- Restore strict height!
                position="relative",
                display="flex",
                align_items="center",
                justify_content="center",
                background="radial-gradient(ellipse at top, #111116 0%, #08080a 100%)",
                transition="height 0.25s ease",
            ),

            # 3. Streamlined Bottom Indicator Strip
            rx.cond(
                (State.answer != "") & (State.available_slides.length() > 1),
                rx.hstack(
                    rx.text(
                        State.available_slides[State.active_slide_idx].upper(),
                        font_size="8px",
                        font_family="monospace",
                        font_weight="800",
                        color="#71717a",
                        letter_spacing="0.1em",
                    ),
                    rx.hstack(
                        rx.foreach(
                            State.available_slides,
                            lambda slide, idx: rx.box(
                                width=rx.cond(State.active_slide_idx == idx, "14px", "4px"),
                                height="3px",
                                border_radius="1.5px",
                                background=rx.cond(State.active_slide_idx == idx, "#e10600", "#27272a"),
                                transition="all 0.2s ease",
                                cursor="pointer",
                                on_click=lambda: State.set_slide(idx),
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    justify="between",
                    align="center",
                    padding="5px 12px",
                    background="#09090b",
                    border_top="1px solid #18181b",
                    width="100%",
                ),
                rx.fragment(),
            ),

            width="100%",
            background="#0a0a0c",
            border="1px solid",
            border_color=rx.cond(State.is_hud_expanded, "#e10600", "#222228"),
            border_radius="6px",
            overflow="hidden",
            margin_bottom="1.25rem",
            box_shadow=rx.cond(
                State.is_hud_expanded,
                "0 8px 30px rgba(225, 6, 0, 0.2), 0 4px 20px rgba(0, 0, 0, 0.8)",
                "0 8px 24px rgba(0, 0, 0, 0.4)",
            ),
            transition="all 0.25s ease",
        ),
        rx.fragment(),
    )

def index() -> rx.Component:
    return rx.box(
        # Header
        rx.box(
            rx.hstack(
                rx.hstack(
                    # F1 Aerodynamic Skew Chequer Badge
                    rx.html(
                        """
                        <svg width="24" height="24" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style="display:inline-block; vertical-align:middle; filter: drop-shadow(0 0 6px rgba(225, 6, 0, 0.45));">
                            <!-- Speed Slash 1 -->
                            <path d="M4 6L2 22H6.5L8.5 6H4Z" fill="#E10600"/>
                            
                            <!-- Chequered Racing Matrix (Italicized 14deg) -->
                            <g transform="skewX(-14)">
                                <!-- Col 1 -->
                                <rect x="11" y="6" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF"/>
                                <rect x="11" y="10" width="3.5" height="3.5" rx="0.5" fill="#27272A"/>
                                <rect x="11" y="14" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF"/>
                                <rect x="11" y="18" width="3.5" height="3.5" rx="0.5" fill="#27272A"/>

                                <!-- Col 2 -->
                                <rect x="15" y="6" width="3.5" height="3.5" rx="0.5" fill="#27272A"/>
                                <rect x="15" y="10" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF"/>
                                <rect x="15" y="14" width="3.5" height="3.5" rx="0.5" fill="#27272A"/>
                                <rect x="15" y="18" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF"/>

                                <!-- Col 3 (Fade edge) -->
                                <rect x="19" y="6" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF" fill-opacity="0.8"/>
                                <rect x="19" y="10" width="3.5" height="3.5" rx="0.5" fill="#27272A" fill-opacity="0.8"/>
                                <rect x="19" y="14" width="3.5" height="3.5" rx="0.5" fill="#FFFFFF" fill-opacity="0.8"/>
                                <rect x="19" y="18" width="3.5" height="3.5" rx="0.5" fill="#27272A" fill-opacity="0.8"/>
                            </g>
                        </svg>
                        """
                    ),
                    rx.text(
                        "CHRONOGRAPH",
                        font_size="1.1rem",
                        font_weight="800",
                        letter_spacing="0.22em",
                        color="#ffffff",
                    ),
                    align="center",
                    spacing="3",
                ),
                rx.badge(
                    "TEMPORAL GRAPHRAG ENGINE",
                    color_scheme="ruby",
                    variant="surface",
                    size="1",
                    letter_spacing="0.08em",
                    font_weight="bold",
                ),
                justify="between",
                align="center",
            ),
            position="sticky",
            top="0",
            z_index="50",
            background_color="rgba(11, 11, 14, 0.92)",
            backdrop_filter="blur(10px)",
            padding="1rem 2rem",
            border_bottom="1px solid rgba(255, 255, 255, 0.08)",
        ),
        # Main Pit Wall Layout (3 Columns: Left, Center, Right)
        rx.grid(
            # LEFT — Ask & Benchmarks
            rx.box(
                rx.text(
                    "QUERY ENGINE",
                    font_size="0.7rem",
                    font_weight="700",
                    letter_spacing="0.18em",
                    color="#888888",
                ),
                rx.heading(
                    "Reconstruct the timeline.",
                    size="4",
                    color="#ffffff",
                    margin_top="0.75rem",
                ),
                rx.text_area(
                    placeholder="Ask a question about F1 history or regulations...",
                    value=State.query,
                    on_change=State.set_query,
                    width="100%",
                    min_height="110px",
                    margin_top="1rem",
                    background="#111111",
                    border="1px solid #282828",
                    color="#ffffff",
                ),
                rx.button(
                    rx.cond(
                        State.loading,
                        "RECONSTRUCTING...",
                        rx.cond(
                            State.is_dev,
                            "INVESTIGATE (DEV UNLIMITED)",
                            rx.cond(
                                State.quota_reached,
                                f"QUOTA REACHED (RESETS IN {State.time_until_reset_min}M)",
                                f"INVESTIGATE ({State.queries_remaining} REMAINING)",
                            ),
                        ),
                    ),
                    on_click=State.investigate,
                    width="100%",
                    margin_top="0.75rem",
                    color_scheme=rx.cond(State.quota_reached, "gray", "ruby"),
                    disabled=State.loading | State.quota_reached,
                    cursor=rx.cond(State.quota_reached, "not-allowed", "pointer"),
                ),
                rx.cond(
                    State.quota_reached,
                    rx.box(
                        rx.text(
                            f"QUERY QUOTA REACHED ({State.query_count}/{State.max_queries}). Cooldown resets in ~{State.time_until_reset_min} minutes.",
                            font_size="0.7rem",
                            font_family="monospace",
                            color="#E10600",
                            font_weight="bold",
                            margin_top="0.5rem",
                        ),
                        rx.text(
                            "ChronoGraph runs on dedicated compute slots. Quotas preserve LPU inference capacity for public demonstration.",
                            font_size="0.68rem",
                            color="#71717A",
                            margin_top="0.2rem",
                        ),
                    ),
                ),
                rx.text(
                    "EXAMPLE QUERIES · RACE DEBRIEF",
                    font_size="0.65rem",
                    font_weight="700",
                    letter_spacing="0.15em",
                    color="#666666",
                    margin_top="2rem",
                ),
                rx.vstack(
                    rx.foreach(
                        State.live_audit_queries,
                        lambda query: rx.button(
                            query,
                            on_click=lambda: State.use_example(query),
                            variant="ghost",
                            width="100%",
                            padding="0.4rem 0.6rem",
                            justify_content="flex-start",
                            text_align="left",
                            white_space="normal",
                            height="auto",
                            font_size="0.78rem",
                            line_height="1.45",
                            color="#888888",
                            border_left="2px solid transparent",
                            border_radius="0px",
                            _hover={"color": "#f0f0f0", "background": "#141414", "border_left": "2px solid #e10600",},
                        ),
                    ),
                    align="start",
                    spacing="2",
                    margin_top="0.6rem",
                    width="100%",
                ),
                rx.text(
                    "EXAMPLE QUERIES · 7 ARCHETYPES",
                    font_size="0.65rem",
                    font_weight="700",
                    letter_spacing="0.15em",
                    color="#666666",
                    margin_top="2.5rem",
                ),
                rx.vstack(
                    rx.foreach(
                        State.example_queries,
                        lambda query: rx.button(
                            query,
                            on_click=lambda: State.use_example(query),
                            variant="ghost",
                            width="100%",
                            padding="0.4rem 0.6rem",
                            justify_content="flex-start",
                            text_align="left",
                            white_space="normal",
                            height="auto",
                            font_size="0.78rem",
                            line_height="1.45",
                            color="#888888",
                            border_left="2px solid transparent",
                            border_radius="0px",
                            _hover={"color": "#f0f0f0", "background": "#141414", "border_left": "2px solid #e10600",},
                        ),
                    ),
                    align="start",
                    spacing="2",
                    margin_top="0.75rem",
                    width="100%",
                ),
                padding="2rem",
                border_right="1px solid #222222",
                style=STICKY_SIDEBAR_STYLE,
            ),
            # CENTER — Synthesized Answer & Reconstruction Trace
            rx.box(
                rx.hstack(
                    rx.text(
                        "INVESTIGATION REPORT",
                        font_size="0.7rem",
                        font_weight="700",
                        letter_spacing="0.18em",
                        color="#888888",
                    ),
                    rx.cond(
                        State.archetype,
                        rx.badge(
                            State.archetype,
                            color_scheme="ruby",
                            variant="solid",
                            size="1",
                        ),
                    ),
                    justify="between",
                    align="center",
                ),
                rx.cond(
                    State.loading,
                    rx.vstack(
                        rx.text(
                            "QUERYING KNOWLEDGE GRAPH & SYNTHESIZING TELEMETRY...",
                            font_size="0.75rem",
                            letter_spacing="0.15em",
                            color="#888888",
                        ),
                        rx.spinner(color="#e10600"),
                        margin_top="2rem",
                        align="start",
                    ),
                    rx.cond(
                        State.answer,
                        rx.vstack(
                            rx.cond(
                                State.answer_expanded,
                                rx.markdown(
                                    State.answer,
                                    component_map=MARKDOWN_COMPONENT_MAP,
                                    margin_top="1rem",
                                ),
                                rx.markdown(
                                    State.answer_preview,
                                    component_map=MARKDOWN_COMPONENT_MAP,
                                    margin_top="1rem",
                                ),
                            ),
                            rx.button(
                                rx.cond(
                                    State.answer_expanded,
                                    "SHOW LESS ↑",
                                    "READ FULL INVESTIGATION ↓",
                                ),
                                on_click=State.toggle_answer,
                                variant="ghost",
                                padding="0",
                                margin_top="0.75rem",
                                color="#888888",
                                _hover={"color": "#ffffff"},
                            ),
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.heading(
                                "Your answer will appear here.",
                                size="6",
                                color="#ffffff",
                            ),
                            rx.text(
                                "Chronograph reconstructs events, causal chains, and "
                                "epistemic shifts across Formula 1 history.",
                                color="#888888",
                                max_width="650px",
                                font_size="0.95rem",
                                line_height="1.6",
                            ),
                            align="start",
                            margin_top="1.5rem",
                        ),
                    ),
                ),
                # Reconstruction Trace Section
                rx.box(
                    rx.cond(
                        State.trace_nodes.length() > 0,
                        rx.box(
                            render_trace_header(State.reconstruct_active_trace),
                            render_trace(
                                State.archetype,
                                State.trace_nodes,
                                State.selected_node,
                                State.select_node,
                            ),
                            width="100%",
                        ),
                        # Standby Telemetry Status Block
                        rx.vstack(
                            rx.hstack(
                                rx.box(
                                    width="7px",
                                    height="7px",
                                    border_radius="50%",
                                    background_color="#22C55E",
                                    box_shadow="0 0 10px #22C55E, 0 0 2px #22C55E",
                                ),
                                rx.text(
                                    "ENGINE STANDBY",
                                    font_size="0.72rem",
                                    font_family="monospace",
                                    font_weight="700",
                                    letter_spacing="0.14em",
                                    color="#E4E4E7",
                                ),
                                rx.text("//", color="#3F3F46", font_family="monospace", font_size="0.72rem"),
                                rx.text(
                                    "AWAITING QUERY EXECUTION",
                                    font_size="0.72rem",
                                    font_family="monospace",
                                    letter_spacing="0.12em",
                                    color="#71717A",
                                ),
                                align="center",
                                spacing="2",
                            ),
                            rx.text(
                                "No active trace. Run an investigation to inspect knowledge graph nodes.",
                                font_size="0.75rem",
                                color="#555555",
                                margin_top="0.35rem",
                            ),
                            align="start",
                            margin_top="0.75rem",
                        ),
                    ),
                    margin_top="3.5rem",
                    padding_top="1.5rem",
                    border_top="1px solid #222222",
                ),
                # Follow-up Section
                rx.box(
                    rx.text(
                        "CONTINUE THE INVESTIGATION",
                        font_size="0.65rem",
                        font_weight="700",
                        letter_spacing="0.15em",
                        color="#666666",
                    ),
                    rx.hstack(
                        rx.input(
                            placeholder=rx.cond(
                                State.quota_reached,
                                "Cooldown active...",
                                "Ask a follow-up question...",
                            ),
                            value=State.follow_up_query,
                            on_change=State.set_follow_up,
                            on_key_down=State.handle_follow_up_key_down,
                            disabled=State.loading | State.quota_reached,
                            flex="1",
                            background="transparent",
                            border="none",
                            outline="none",
                            color="#f2f2f2",
                        ),
                        rx.button(
                            "→",
                            on_click=State.submit_follow_up,
                            disabled=State.loading | State.quota_reached,
                            variant="ghost",
                            font_size="1.2rem",
                            color="#888888",
                            _hover={"color": "#e10600"},
                        ),
                        width="100%",
                        margin_top="0.5rem",
                        padding="0.5rem 0",
                        border_bottom="1px solid #282828",
                    ),
                    margin_top="3rem",
                ),
                padding="2.5rem",
            ),
            # RIGHT — Interactive Backfill Panel (Dynamic Upvoting & Baby KG Tooltip) & HUD Visual Canvas
            rx.box(
                rx.vstack(
                    # ---> VISUAL HUD CAROUSEL HERE <---
                
                    chronograph_hud_deck(),

                    rx.vstack(
                        # Header + Info Hover Card
                        rx.hstack(
                            rx.text(
                                "COMMUNITY BACKFILL",
                                font_size="0.75rem",
                                font_weight="700",
                                color="#888888",
                                letter_spacing="0.1em",
                            ),
                            rx.hover_card.root(
                                rx.hover_card.trigger(
                                    rx.text(
                                        "ⓘ",
                                        color="#666666",
                                        font_size="0.8rem",
                                        cursor="help",
                                        _hover={"color": "#aaaaaa"},
                                    ),
                                ),
                                rx.hover_card.content(
                                    rx.text(
                                        "Historical coverage is still being backfilled. "
                                        "The developer has to structure and verify all of this manually. Tragic.",
                                        font_size="0.7rem",
                                        line_height="1.4",
                                        color="#cccccc",
                                    ),
                                    max_width="190px",
                                    padding="0.65rem 0.8rem",
                                    background="rgba(18, 18, 18, 0.9)",
                                    backdrop_filter="blur(10px)",
                                    border="1px solid #282828",
                                    border_radius="6px",
                                    box_shadow="0 4px 16px rgba(0, 0, 0, 0.5)",
                                    side="bottom",
                                    align="end",
                                ),
                            ),
                            justify="between",
                            align="center",
                            width="100%",
                        ),
                        rx.heading("Knowledge Coverage", size="3", color="#ffffff"),
                        rx.text(
                            "Notice a missing event in an investigation? Upvote or request historical incidents to be indexed next.",
                            font_size="0.75rem",
                            color="#777777",
                            line_height="1.5",
                        ),
                        rx.divider(border_color="#222222", margin_y="0.5rem"),

                        # Controls & Dynamic Backlog Feed
                        rx.vstack(
                            # 1. Search Box for backlog lookup
                            rx.input(
                                placeholder="Filter backfill queue...",
                                on_change=State.set_ticket_search,
                                size="1",
                                variant="surface",
                                background="#0a0a0a",
                                border="1px solid #222222",
                                color="#cccccc",
                                margin_bottom="0.5rem",
                                width="100%",
                            ),

                            # 2. View Segmented Pill Switcher
                            rx.hstack(
                                rx.box(
                                    rx.hstack(
                                        rx.text("🔥", font_size="0.65rem"),
                                        rx.text("TOP VOTED", font_size="0.65rem", font_weight="700", letter_spacing="0.05em"),
                                        spacing="1",
                                        align="center",
                                    ),
                                    padding="0.25rem 0.65rem",
                                    border_radius="4px",
                                    cursor="pointer",
                                    background=rx.cond(State.queue_filter == "top", "#e10600", "transparent"),
                                    color=rx.cond(State.queue_filter == "top", "#ffffff", "#777777"),
                                    transition="all 0.15s ease",
                                    _hover={"color": "#ffffff"},
                                    on_click=lambda: State.set_queue_filter("top"),
                                ),
                                rx.box(
                                    rx.hstack(
                                        rx.text("⚡", font_size="0.65rem"),
                                        rx.text("RECENT", font_size="0.65rem", font_weight="700", letter_spacing="0.05em"),
                                        spacing="1",
                                        align="center",
                                    ),
                                    padding="0.25rem 0.65rem",
                                    border_radius="4px",
                                    cursor="pointer",
                                    background=rx.cond(State.queue_filter == "recent", "#222222", "transparent"),
                                    color=rx.cond(State.queue_filter == "recent", "#ffffff", "#777777"),
                                    transition="all 0.15s ease",
                                    _hover={"color": "#ffffff"},
                                    on_click=lambda: State.set_queue_filter("recent"),
                                ),
                                background="#0f0f0f",
                                border="1px solid #222222",
                                border_radius="6px",
                                padding="2px",
                                spacing="1",
                                margin_bottom="0.85rem",
                                width="fit-content",
                            ),

                            # 3. Scrollable List Box (replaces empty rx.box())
                            rx.box(
                                rx.foreach(
                                    State.displayed_backfill_queue,
                                    lambda item: rx.vstack(
                                            rx.hstack(
                                            # 1. UPVOTE COUNTER
                                            rx.hstack(
                                                rx.button(
                                                    "▲",
                                                    size="1",
                                                    variant="ghost",
                                                    disabled=State.upvoted_ids.contains(item["id"]) | (item["status"] == "ingested"),
                                                    cursor=rx.cond(item["status"] == "ingested", "not-allowed", "pointer"),
                                                    color=rx.cond(
                                                        item["status"] == "ingested",
                                                        "#333333",
                                                        rx.cond(
                                                            State.upvoted_ids.contains(item["id"]),
                                                            "#e10600",
                                                            "#666666",
                                                        ),
                                                    ),
                                                    font_size="0.65rem",
                                                    padding="0 0.2rem",
                                                    height="auto",
                                                    on_click=lambda: State.upvote_ticket(item["id"]),
                                                    _hover={"color": rx.cond(item["status"] == "ingested", "#333333", "#e10600"), "background": "transparent"},
                                                ),
                                                rx.text(
                                                    item["votes"],
                                                    font_size="0.75rem",
                                                    font_weight="700",
                                                    font_family="monospace",
                                                    color=rx.cond(
                                                        item["status"] == "ingested",
                                                        "#444444",
                                                        rx.cond(
                                                            State.upvoted_ids.contains(item["id"]),
                                                            "#ffffff",
                                                            "#888888",
                                                        ),
                                                    ),
                                                    min_width="18px",
                                                ),
                                                spacing="1",
                                                align="center",
                                                flex_shrink=0,
                                            ),

                                            # 2. TICKET CODE (e.g. #55)
                                            rx.text(
                                                item["id"],
                                                font_size="0.7rem",
                                                font_family="monospace",
                                                color="#555555",
                                                width="26px",
                                                flex_shrink=0,
                                            ),

                                            # 3. TITLE & HOVER CARD (Natural flex width, no harsh cutoffs)
                                            rx.hover_card.root(
                                                rx.hover_card.trigger(
                                                    rx.hstack(
                                                        rx.text(
                                                            item["title"],
                                                            font_size="0.76rem",
                                                            color=rx.cond(item["status"] == "ingested", "#666666", "#d8d8d8"),
                                                            text_decoration=rx.cond(item["status"] == "ingested", "line-through", "none"),
                                                            white_space="normal",      # Allows readable line wrap if needed
                                                            line_height="1.25",
                                                            cursor="help",
                                                            _hover={"color": "#ffffff"},
                                                        ),
                                                        rx.cond(
                                                            item["status"] == "ingested",
                                                            rx.badge(
                                                                "IN KG",
                                                                color_scheme="green",
                                                                size="1",
                                                                variant="surface",
                                                                font_size="0.55rem",
                                                                padding="0 0.2rem",
                                                            ),
                                                            rx.fragment(),
                                                        ),
                                                        spacing="1",
                                                        align="center",
                                                    ),
                                                ),
                                                rx.hover_card.content(
                                                    rx.text(
                                                        item["detail"],
                                                        font_size="0.72rem",
                                                        line_height="1.45",
                                                        color="#d0d0d0",
                                                    ),
                                                    max_width="240px",
                                                    padding="0.6rem 0.8rem",
                                                    background="rgba(14, 14, 14, 0.95)",
                                                    backdrop_filter="blur(10px)",
                                                    border="1px solid #282828",
                                                    border_radius="6px",
                                                    box_shadow="0 6px 20px rgba(0, 0, 0, 0.6)",
                                                    side="left",
                                                    align="center",
                                                ),
                                            ),

                                            align="center",
                                            justify="between",
                                            spacing="2",
                                            padding_y="0.35rem",
                                            width="100%",
                                            border_bottom="1px solid #161616",
                                        ),
                                        # DEVELOPER ACTIONS (Clean sub-row directly under the ticket)
                                        rx.cond(
                                            State.is_dev,
                                            rx.hstack(
                                                rx.text(
                                                    "DEV CONTROLS",
                                                    font_size="0.45rem",
                                                    font_weight="700",
                                                    font_family="monospace",
                                                    color="#444444",
                                                    letter_spacing="0.05em",
                                                ),
                                                rx.hstack(
                                                    rx.button(
                                                        rx.cond(item["status"] == "ingested", "Queued ↺", "Ingested ✓"),
                                                        size="1",
                                                        variant="surface",
                                                        color_scheme=rx.cond(item["status"] == "ingested", "gray", "green"),
                                                        font_size="0.6rem",
                                                        padding="0 0.35rem",
                                                        height="18px",
                                                        on_click=lambda: State.mark_ticket_ingested(item["id"]),
                                                        cursor="pointer",
                                                    ),
                                                    rx.button(
                                                        "Delete ✕",
                                                        size="1",
                                                        variant="surface",
                                                        color_scheme="red",
                                                        font_size="0.6rem",
                                                        padding="0 0.35rem",
                                                        height="18px",
                                                        on_click=lambda: State.delete_ticket(item["id"]),
                                                        cursor="pointer",
                                                    ),
                                                    spacing="1",
                                                ),
                                                width="100%",
                                                spacing="1",
                                                justify="start",
                                                align="center",
                                                padding_top="0.25rem",
                                                # padding_left="2.2rem",  # Aligns neatly right under the event title
                                            ),
                                            rx.fragment(),
                                        ),
                                        width="100%",
                                        spacing="1",
                                        align_items="start",
                                        padding_y="0.35rem",
                                        border_bottom="1px solid #161616",
                                    ),
                                ),
                                max_height=rx.cond(State.is_dev, "680px", rx.cond(State.show_all_tickets, "600px", "500px")),
                                overflow_y="auto",
                                width="100%",
                                padding="4px",
                            ),

                            # 4. View All Toggle Row
                            rx.hstack(
                                rx.button(
                                    rx.cond(
                                        State.show_all_tickets,
                                        "COLLAPSE TO TOP 10",
                                        "SHOW COMPLETE QUEUE",
                                    ),
                                    size="1",
                                    variant="ghost",
                                    color="#888888",
                                    font_size="0.65rem",
                                    _hover={"color": "#ffffff", "background": "transparent"},
                                    on_click=State.toggle_show_all,
                                ),
                                rx.cond(
                                    State.is_dev,
                                    rx.badge("DEV UNLOCKED", color_scheme="ruby", variant="outline", size="1"),
                                    rx.fragment(),
                                ),
                                justify="between",
                                align="center",
                                width="100%",
                                padding_top="0.25rem",
                            ),
                            width="100%",
                            spacing="1",
                        ),

                        # 5. Suggest Action Button at bottom
                        rx.button(
                            "+ SUGGEST AN EVENT",
                            size="2",
                            variant="outline",
                            color_scheme="gray",
                            font_size="0.75rem",
                            width="100%",
                            margin_top="1rem",
                            cursor="pointer",
                            on_click=State.open_suggest_modal,
                            _hover={"border_color": "#e10600", "color": "#ffffff"},
                        ),
                        spacing="3",
                        align="start",
                        width="100%",
                    ),
                    spacing="5",
                    width="100%",
                    # Sticky properties:
                    position="sticky",
                    top="1.5rem",
                    align_self="start",
                    height="fit-content",
                ),
                padding="1.5rem 1.75rem",
                border_left="1px solid #222222",
                position="relative",
                width="100%",
                min_height="100%",
                overflow="visible",
            ),
            # Dynamic Grid
            columns=rx.cond(
                State.is_hud_expanded,
                "0.8fr 1.6fr 1.8fr",    # Expanded state: wide sidebar without overlapping
                "1fr 2.3fr 0.9fr",      # Default layout
            ),
            width="100%",
            min_height="calc(100vh - 65px)",
            transition="grid-template-columns 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        ),
        # Dialog Modal for Event Submission (Placed outside the grid at the root level)
        rx.dialog.root(
            rx.dialog.content(
                # Header with Title and Top-Right '✕' Close Button
                rx.hstack(
                    rx.dialog.title("Request Knowledge Backfill", color="#ffffff", size="3", margin="0"),
                    rx.dialog.close(
                        rx.button(
                            "✕",
                            variant="ghost",
                            color="#666666",
                            font_size="0.9rem",
                            padding="0.2rem 0.5rem",
                            height="auto",
                            on_click=State.close_suggest_modal,
                            _hover={"color": "#ffffff", "background": "transparent"},
                            cursor="pointer",
                        ),
                    ),
                    justify="between",
                    align="center",
                    width="100%",
                ),
                rx.dialog.description(
                    "Help the developer scrape the right data. Give the event a title and any specific drivers, quotes, or keywords to search for.",
                    color="#888888",
                    font_size="0.8rem",
                    margin_y="0.5rem",
                ),
                
                # Form Inputs
                rx.vstack(
                    rx.text("EVENT TITLE / RACE", font_size="0.7rem", color="#aaaaaa", font_weight="600"),
                    rx.input(
                        placeholder="e.g., 2008 Singapore GP Crashgate",
                        value=State.custom_event_title,
                        on_change=State.set_custom_title,
                        background="#0d0d0d",
                        border="1px solid #282828",
                        color="#ffffff",
                        width="100%",
                        font_size="0.85rem",
                    ),
                    rx.text("KEY DETAILS / SEARCH CLUES", font_size="0.7rem", color="#aaaaaa", font_weight="600", margin_top="0.5rem"),
                    rx.text_area(
                        placeholder="e.g., Piquet Jr deliberate crash at Turn 17, Briatore radio instructions, safety car timing...",
                        value=State.custom_event_desc,
                        on_change=State.set_custom_desc,
                        background="#0d0d0d",
                        border="1px solid #282828",
                        color="#ffffff",
                        rows="3",
                        width="100%",
                        font_size="0.85rem",
                    ),
                    width="100%",
                    spacing="1",
                    margin_y="1rem",
                ),

                # Action Buttons (Balanced Height & Padding)
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color="#888888",
                            border="1px solid #282828",
                            background="transparent",
                            size="2",
                            font_size="0.8rem",
                            on_click=State.close_suggest_modal,
                            _hover={"color": "#ffffff", "border_color": "#444444"},
                            cursor="pointer",
                        ),
                    ),
                    rx.button(
                        "Submit to Queue",
                        size="2",
                        font_size="0.8rem",
                        font_weight="600",
                        background="#e10600",
                        color="#ffffff",
                        on_click=State.submit_backfill_event,
                        _hover={"background": "#b30500"},
                        cursor="pointer",
                    ),
                    justify="end",
                    spacing="3",
                    width="100%",
                    align="center",
                ),
                background="#111111",
                border="1px solid #282828",
                border_radius="8px",
                padding="1.5rem",
                max_width="460px",
            ),
            open=State.suggest_modal_open,
        ),
        width="100%",
        min_height="100vh",
        background="#0a0a0a",
        color="#f2f2f2",
    )


app = rx.App(
    head_components=[
        rx.el.meta(
            name="viewport",
            content="width=1280",
        ),
    ]
)
app.add_page(index, on_load=State.on_load)
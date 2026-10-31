import re
from typing import Dict, List, Any

# 1. CIRCUIT SLUG MAP (33 Circuits)
CIRCUIT_MAP = {
    "bahrain": "bahrain", "sakhir": "bahrain",
    "jeddah": "jeddah", "saudi arabia": "jeddah",
    "melbourne": "melbourne", "albert park": "melbourne",
    "suzuka": "suzuka", "japan": "suzuka",
    "shanghai": "shanghai", "china": "shanghai",
    "miami": "miami",
    "imola": "imola", "emilia romagna": "imola",
    "monaco": "monaco", "monte carlo": "monaco",
    "montreal": "montreal", "gilles villeneuve": "montreal", "canada": "montreal",
    "catalunya": "catalunya", "barcelona": "catalunya", "spain": "catalunya",
    "red bull ring": "red_bull_ring", "austria": "red_bull_ring", "spielberg": "red_bull_ring",
    "silverstone": "silverstone", "british": "silverstone",
    "hungaroring": "hungaroring", "hungary": "hungaroring", "budapest": "hungaroring",
    "spa": "spa", "spa-francorchamps": "spa", "belgium": "spa",
    "zandvoort": "zandvoort", "dutch": "zandvoort", "netherlands": "zandvoort",
    "monza": "monza", "italy": "monza",
    "baku": "baku", "azerbaijan": "baku",
    "marina bay": "marina_bay", "singapore": "marina_bay",
    "cota": "cota", "austin": "cota", "circuit of the americas": "cota",
    "mexico": "mexico", "hermanos rodriguez": "mexico",
    "interlagos": "interlagos", "brazil": "interlagos", "sao paulo": "interlagos",
    "las vegas": "las_vegas", "vegas": "las_vegas",
    "losail": "losail", "lusail": "losail", "qatar": "losail",
    "yas marina": "yas_marina", "abu dhabi": "yas_marina",
    "hockenheim": "hockenheim", "hockenheimring": "hockenheim",
    "indianapolis": "indianapolis", "indy": "indianapolis",
    "istanbul park": "istanbul_park", "turkey": "istanbul_park",
    "magny cours": "magny_cours", "magny-cours": "magny_cours",
    "mugello": "mugello", "tuscany": "mugello",
    "nurburgring": "nurburgring", "nürburgring": "nurburgring",
    "paul ricard": "paul_ricard", "le castellet": "paul_ricard",
    "portimao": "portimao", "algarve": "portimao", "portugal": "portimao",
    "sepang": "sepang", "malaysia": "sepang",
}

# 2. CIRCUIT-SPECIFIC NAMED CORNERS
CIRCUIT_CORNER_NAMES = {
    "silverstone": {
        "abbey": "1", "farm": "2", "village": "3", "the loop": "4", "loop": "4",
        "aintree": "5", "wellington straight": "5", "brooklands": "6", "luffield": "7",
        "woodcote": "8", "copse": "9", "maggotts": "10", "maggots": "10",
        "becketts": "11", "chapel": "12", "stowe": "15", "vale": "16", "club": "18",
    },
    "monza": {
        "variante del rettifilo": "1", "rettifilo": "1", "curva grande": "3", "biassono": "3",
        "variante della roggia": "4", "roggia": "4", "lesmo 1": "6", "lesmo 2": "7",
        "serraglio": "7", "variante ascari": "8", "ascari": "8", "curva parabolica": "11",
        "parabolica": "11", "curva alboreto": "11",
    },
    "spa": {
        "la source": "1", "source": "1", "eau rouge": "2", "raidillon": "3",
        "kemmel": "4", "kemmel straight": "4", "les combes": "5", "combes": "5",
        "malmedy": "6", "rivage": "7", "bruxelles": "8", "speaker's corner": "9",
        "pouhon": "12", "double gauche": "10", "fagnes": "13", "campus": "14",
        "stavelot": "15", "paul frere": "15", "blanchimont": "17", "bus stop": "19",
    },
    "monaco": {
        "sainte devote": "1", "saint devote": "1", "beau rivage": "2", "massenet": "3",
        "casino": "4", "casino square": "4", "mirabeau": "5", "grand hotel hairpin": "6",
        "loews": "6", "fairmont": "6", "portier": "8", "tunnel": "9",
        "nouvelle chicane": "10", "tabac": "12", "louis chiron": "13", "swimming pool": "14",
        "piscine": "14", "rascasse": "17", "anthony noghes": "18",
    },
    "suzuka": {
        "first corner": "1", "s curves": "3", "snakes": "4", "gyaku-bank": "6",
        "reverse bank": "6", "dunlop": "7", "degner 1": "8", "degner 2": "9",
        "degner": "8", "hairpin": "11", "200r": "12", "spoon": "13", "spoon curve": "14",
        "130r": "15", "casio triangle": "16",
    },
    "zandvoort": {
        "tarzan": "1", "tarzanbocht": "1", "gerlach": "2", "hugenholtz": "3",
        "hunserug": "4", "scheivlak": "7", "mastersbocht": "8", "hans ernst": "11",
        "arrie luyendyk": "14", "luyendyk": "14",
    },
    "red_bull_ring": {
        "niki lauda": "1", "lauda": "1", "remus": "3", "schlossgold": "4",
        "rauch": "4", "gerhard berger": "6", "jochen rindt": "9", "rindt": "9",
        "red bull mobile": "10",
    },
    "interlagos": {
        "senna s": "1", "senna esses": "1", "s do senna": "1", "curva do sol": "3",
        "descida do lago": "4", "ferradura": "6", "horseshoe": "6", "laranjinha": "8",
        "pinheirinho": "9", "bico de pato": "10", "mergulho": "11", "juncao": "12",
        "arquibancadas": "15",
    },
    "montreal": {
        "virage senna": "1", "senna corner": "1", "pont de la concorde": "3",
        "l'epingle": "10", "hairpin": "10", "wall of champions": "14",
    },
    "catalunya": {
        "elf": "1", "renault": "3", "repsol": "4", "seat": "5", "wurth": "6",
        "campsa": "9", "la caixa": "10", "banc sabadell": "12", "europcar": "13",
    },
    "melbourne": {
        "jones": "1", "brabham": "2", "whiteford": "3", "lauda": "9",
        "waite": "11", "hill": "12", "ascari": "13", "stewart": "14", "prost": "15", "senna": "16",
    },
    "imola": {
        "tamburello": "2", "villeneuve": "5", "tosa": "7", "piratella": "9",
        "acque minerali": "11", "variante alta": "14", "gresini": "14", "rivazza": "17",
    },
    "cota": {
        "big red": "1", "esses": "3", "maggotts complex": "4", "carousel": "17",
    },
    "mexico": {
        "moises solana": "1", "solana s": "2", "lake esses": "7", "foro sol": "13", "baseball stadium": "14",
    },
    "las_vegas": {
        "koval chicane": "1", "sphere": "5", "msg sphere": "5", "the strip": "12", "bellagio straight": "12",
    },
    "yas_marina": {
        "north hairpin": "5", "marsa straight": "5", "south banked hairpin": "9", "yas hotel": "13",
    },
    "hockenheim": {
        "nordkurve": "1", "parabolika": "4", "spitzkehre": "6", "mercedes arena": "8",
        "motodrom": "12", "sachskurve": "13", "opelkurve": "16",
    },
    "nurburgring": {
        "castrol-s": "1", "mercedes-arena": "2", "ford-kurve": "5", "dunlop-kehre": "7",
        "schumacher-s": "8", "veedol-schikane": "13", "coca-cola-kurve": "15",
    },
    "paul_ricard": {
        "verriere": "1", "sainte baume": "3", "mistral": "7", "chicane du mistral": "8", "signes": "10", "le beausset": "11",
    },
    "portimao": {
        "primeira": "1", "lagos": "3", "torre vip": "5", "curva do sol": "8", "galp": "15",
    },
    "sepang": {
        "turn 1 hairpin": "1", "langkawi": "5", "berjaya tioman": "9", "sunway": "15",
    },
    "mugello": {
        "san donato": "1", "materassi": "4", "casanova": "6", "savelli": "7", "arrabbiata 1": "8", "arrabbiata 2": "9", "correntaio": "12",
    },
    "magny_cours": {
        "grande courbe": "1", "estoril": "3", "adelaide": "5", "chateau d'eau": "7", "imola": "11",
    },
    "istanbul_park": {
        "turn 1 drop": "1", "turkish corkscrew": "8", "turn 8": "8", "quadruple apex": "8",
    },
    "bahrain": {"oasis": "4", "batelco": "8"},
    "jeddah": {"banked hairpin": "13", "marina bend": "22"},
    "shanghai": {"snail corner": "1", "main hairpin": "14"},
    "miami": {"yacht club": "6", "turnpike chicane": "14"},
    "hungaroring": {"mansell": "4", "alecs": "11"},
    "baku": {"castle section": "8", "narrow chute": "11"},
    "marina_bay": {"sheares": "1", "singapore sling": "10", "anderson bridge": "13"},
    "indianapolis": {"infield hairpin": "8", "oval banking": "13"},
    "losail": {"triple apex right": "12"},
}

# 3. CONSTRUCTOR REGISTRY
CONSTRUCTOR_MAP = {
    "mclaren": "mclaren", "papaya": "mclaren",
    "mercedes": "mercedes", "silver arrows": "mercedes",
    "red bull": "red_bull", "rbpt": "red_bull", "rbr": "red_bull",
    "ferrari": "ferrari", "scuderia": "ferrari", "maranello": "ferrari",
    "aston martin": "aston_martin", "racing point": "aston_martin", "force india": "aston_martin",
    "alpine": "alpine", "renault": "alpine", "enstone": "alpine",
    "williams": "williams", "grove": "williams",
    "audi": "audi", "sauber": "audi", "stake": "audi", "kick sauber": "audi", "alfa romeo": "audi",
    "racing bulls": "racing_bulls", "vcarb": "racing_bulls", "alphatauri": "racing_bulls", "toro rosso": "racing_bulls",
    "haas": "haas", "haas f1": "haas",
    "cadillac": "cadillac", "andretti": "cadillac",
    "lotus": "lotus", "brabham": "brabham", "tyrrell": "tyrrell", "benetton": "benetton",
    "jordan": "jordan", "brawn": "brawn", "toyota": "toyota", "bmw sauber": "bmw_sauber",
}

# 4. CHASSIS AERODYNAMICS & COMPONENT KEYWORDS
CHASSIS_KEYWORDS = [
    (r"\b(macarena|straight[- ]mode|active[- ]flap|active[- ]aero|rear[- ]wing|rwep|beam[- ]wing|bi[- ]plane|drs|drag[- ]reduction|actuator|gurney[- ]flap|slot[- ]gap)\b", "rear-wing-assembly", "REAR WING / BEAM WING"),
    (r"\b(front[- ]wing|fwep|wing[- ]flap|flap[- ]chord|diveplane|canard|outwash|endplate|nose[- ]cone|nose[- ]tip)\b", "front-wing-profile", "FRONT WING / MAINPLANE"),
    (r"\b(floor[- ]edge|edge[- ]wing|floor[- ]body|underbody|venturi|ground[- ]effect|venturi[- ]fences|skid[- ]block|plank|bib[- ]spring|porpoising)\b", "floor-underbody", "VENTURI FLOOR / SKID BLOCK"),
    (r"\b(sidepod|undercut|waterslide|gully|trench|downwash|cooling[- ]louvres|louvres|gills|radiator[- ]inlet)\b", "sidepod-ramp", "SIDEPOD UNDERCUT / LOUVRES"),
    (r"\b(diffuser|diffuser[- ]ramp|diffuser[- ]kick|expansion[- ]chamber|diffuser[- ]strakes)\b", "diffuser-ramp", "REAR DIFFUSER ASSEMBLY"),
    (r"\b(front[- ]suspension|rear[- ]suspension|suspension|wishbone|pushrod|pullrod|anti[- ]dive|anti[- ]squat|brake[- ]duct|brake[- ]scoop)\b", "front-suspension-profile", "SUSPENSION & BRAKE DUCTS"),
    (r"\b(engine[- ]cover|shark[- ]fin|dorsal[- ]fin|airbox|halo|roll[- ]hoop)\b", "engine-cover-spine", "AIRBOX / ENGINE COVER"),
    (r"\b(power[- ]unit|ice|mgu[- ]k|mgu[- ]h|battery[- ]pack|turbo|derating)\b", "airbox-intake", "POWER UNIT / HYBRID ERS"),
]

def analyze_debrief_for_carousel(text: str) -> Dict[str, Any]:
    lower = text.lower()
    slides_data = []

    # --- 1. CIRCUITS ---
    circuits_detected = []
    for kw, slug in sorted(CIRCUIT_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", lower) and slug not in circuits_detected:
            circuits_detected.append(slug)

    for c_slug in circuits_detected:
        c_highlights = {}
        detected_pills = []
        for t in sorted(set(re.findall(r"\b(?:turn|t)\s*(\d{1,2})\b", lower)), key=int):
            c_highlights[f"turn-{t}"] = "highlight-f1-red"
            detected_pills.append(f"TURN {t}")

        slides_data.append({
            "type": "circuit",
            "slug": c_slug,
            "badge_title": c_slug.replace("_", " ").upper(),
            "label": " // ".join(detected_pills[:3]) if detected_pills else "FULL TRACK LAYOUT",
            "highlights": c_highlights
        })

    # --- 2. CHASSIS / CONSTRUCTORS ---
    teams_detected = []
    for alias, canonical in CONSTRUCTOR_MAP.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            formatted_team = canonical.replace("_", " ").upper()
            if formatted_team not in teams_detected:
                teams_detected.append(formatted_team)

    matched_elements = []
    chassis_highlights = {}
    for pattern, elem_id, display_label in CHASSIS_KEYWORDS:
        if re.search(pattern, lower):
            chassis_highlights[elem_id] = "highlight-f1-red"
            matched_elements.append(display_label)

    comp_label = matched_elements[0] if matched_elements else "AERO COMPONENT"

    if len(teams_detected) > 1:
        for team in teams_detected:
            slides_data.append({
                "type": "chassis",
                "team": team,
                "badge_title": f"{team} // SPEC",
                "label": f"{team} // {comp_label}",
                "status": f"COMPARATIVE SPEC // {len(matched_elements)} UPGRADE(S)",
                "highlights": chassis_highlights
            })
    elif teams_detected or matched_elements:
        team_title = teams_detected[0] if teams_detected else "GEN-3 SPEC"
        slides_data.append({
            "type": "chassis",
            "team": team_title,
            "badge_title": f"{team_title} // SPEC",
            "label": f"{team_title} // {comp_label}",
            "status": f"ANALYSIS FOCUS // {len(matched_elements)} UPGRADE(S)",
            "highlights": chassis_highlights
        })

    # --- 3. TEAM RADIO ---
    radio_match = re.search(r'(?:radio|team radio|engineer|driver|said|box box)[:\s]+"([^"]+)"', text, re.IGNORECASE)
    if radio_match or any(k in lower for k in ["radio message", "box box", "leave me alone", "no power"]):
        slides_data.append({
            "type": "radio",
            "badge_title": "PIT WALL RADIO",
            "speaker": f"{teams_detected[0]} // PIT WALL" if teams_detected else "PIT WALL // TEAM RADIO",
            "message": radio_match.group(1) if radio_match else "Telemetry confirmed. Standby for delta feedback."
        })

    # --- 4. PENALTY / FIA DIRECTIVE ---
    if any(k in lower for k in ["penalty", "stewards", "investigation", "banned", "outlaw", "technical directive", "wmsc"]):
        sec_match = re.search(r"\b(\d{1,2})\s*(?:sec|second|s)\b", lower)
        
        verdict_snippet = "Regulatory intervention regarding aerodynamic / structural compliance."
        for sentence in re.split(r'(?<=[.!?])\s+', text):
            if any(w in sentence.lower() for w in ["bann", "outlaw", "penalty", "wmsc", "directive", "illegal"]):
                verdict_snippet = sentence.strip()
                break

        slides_data.append({
            "type": "penalty",
            "badge_title": "FIA REGULATORY RULING",
            "title": "WMSC / FIA TECHNICAL DIRECTIVE" if "wmsc" in lower or "directive" in lower else "FIA STEWARDS BULLETIN",
            "decision": f"{sec_match.group(1)} SEC TIME PENALTY" if sec_match else "REGULATORY BAN / CLARIFICATION",
            "incident": verdict_snippet[:220] + "..." if len(verdict_snippet) > 220 else verdict_snippet
        })

    if not slides_data:
        slides_data.append({
            "type": "fallback",
            "badge_title": "PADDOCK REPORT"
        })

    return {
        "is_open": True,
        "slides": slides_data
    }
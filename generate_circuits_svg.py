import os
import json
import urllib.request
import numpy as np

os.makedirs("assets/circuits", exist_ok=True)

# 1. 25 Modern Championship Circuits
MODERN_TRACKS = [
    ("bahrain", "bh-2002.geojson", 15),
    ("jeddah", "sa-2021.geojson", 27),
    ("melbourne", "au-1953.geojson", 14),
    ("suzuka", "jp-1962.geojson", 18),
    ("shanghai", "cn-2004.geojson", 16),
    ("miami", "us-2022.geojson", 19),
    ("imola", "it-1953.geojson", 19),
    ("monaco", "mc-1929.geojson", 19),
    ("montreal", "ca-1978.geojson", 14),
    ("catalunya", "es-1991.geojson", 14),
    ("red_bull_ring", "at-1969.geojson", 10),
    ("silverstone", "gb-1948.geojson", 18),
    ("hungaroring", "hu-1986.geojson", 14),
    ("spa", "be-1925.geojson", 19),
    ("zandvoort", "nl-1948.geojson", 14),
    ("monza", "it-1922.geojson", 11),
    ("baku", "az-2016.geojson", 20),
    ("marina_bay", "sg-2008.geojson", 19),
    ("cota", "us-2012.geojson", 20),
    ("mexico", "mx-1962.geojson", 17),
    ("interlagos", "br-1940.geojson", 15),
    ("las_vegas", "us-2023.geojson", 17),
    ("losail", "qa-2004.geojson", 16),
    ("yas_marina", "ae-2009.geojson", 16),
    ("sepang", "my-1999.geojson", 15),
]

# 2. 8 Classic & Historical Circuits
HISTORIC_TRACKS = [
    ("hockenheim", "de-1932.geojson", 17),       # Hockenheimring
    ("istanbul_park", "tr-2005.geojson", 14),   # Istanbul Park
    ("nurburgring", "de-1927.geojson", 16),     # Nürburgring
    ("portimao", "pt-2008.geojson", 15),        # Algarve / Portimão
    ("mugello", "it-1914.geojson", 15),         # Mugello Circuit
    ("paul_ricard", "fr-1969.geojson", 15),     # Circuit Paul Ricard
    ("magny_cours", "fr-1960.geojson", 17),     # Circuit de Nevers Magny-Cours
    ("indianapolis", "us-1909.geojson", 13),    # Indianapolis Motor Speedway
]

ALL_CIRCUITS = MODERN_TRACKS + HISTORIC_TRACKS

TRACK_LIMIT_TURNS = {
    "cota": [9, 12, 19, 20],
    "red_bull_ring": [1, 9, 10],
    "hungaroring": [4, 11],
    "silverstone": [9, 15, 18],
    "monza": [1, 2, 5, 11],
    "spa": [4, 9, 19],
    "losail": [4, 5, 12, 13, 14],
    "catalunya": [1, 2, 12],
    "hockenheim": [1, 17],
    "istanbul_park": [1, 8, 9],
    "portimao": [1, 4, 14, 15],
    "paul_ricard": [2, 6, 11],
}

def coords_to_path(px, py):
    if len(px) == 0:
        return ""
    coords = [f"{round(px[i], 1)} {round(py[i], 1)}" for i in range(len(px))]
    return f"M {coords[0]} L " + " L ".join(coords[1:])

def generate_svg_from_source(slug: str, filename: str, turn_count: int):
    url = f"https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/{filename}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"[{slug.upper()}] Failed to fetch trace ({e})")
        return False

    coords = []
    features = data.get('features', [])
    for feat in features:
        geom = feat.get('geometry', {})
        if geom.get('type') == 'LineString':
            coords = geom.get('coordinates', [])
            break

    if not coords or len(coords) < 10:
        print(f"[{slug.upper()}] Empty coordinate set.")
        return False

    raw_x = np.array([pt[0] for pt in coords])
    raw_y = np.array([pt[1] for pt in coords])

    min_x, max_x = raw_x.min(), raw_x.max()
    min_y, max_y = raw_y.min(), raw_y.max()
    scale = 400.0 / max(max_x - min_x, max_y - min_y)

    nx = (raw_x - min_x) * scale + 50
    ny = (max_y - raw_y) * scale + 50

    total_pts = len(nx)
    s1_end = int(total_pts * 0.33)
    s2_end = int(total_pts * 0.66)

    path_s1 = coords_to_path(nx[:s1_end + 1], ny[:s1_end + 1])
    path_s2 = coords_to_path(nx[s1_end:s2_end + 1], ny[s1_end:s2_end + 1])
    path_s3 = coords_to_path(np.append(nx[s2_end:], nx[0]), np.append(ny[s2_end:], ny[0]))

    pit_d = f"M {round(nx[0]+8, 1)} {round(ny[0]+8, 1)} L {round(nx[min(35, total_pts-1)]+8, 1)} {round(ny[min(35, total_pts-1)]+8, 1)}"

    drs_s2_start = int(s1_end + (s2_end - s1_end) * 0.4)
    drs_s2_end = int(s1_end + (s2_end - s1_end) * 0.85)
    path_drs = coords_to_path(nx[drs_s2_start:drs_s2_end], ny[drs_s2_start:drs_s2_end])

    corners_svg = []
    hotspots_svg = []
    active_hotspots = TRACK_LIMIT_TURNS.get(slug, [1, 4])
    step = max(1, total_pts // turn_count)

    for turn_num in range(1, turn_count + 1):
        idx = min((turn_num - 1) * step, total_pts - 1)
        cx, cy = round(nx[idx], 1), round(ny[idx], 1)
        
        corners_svg.append(
            f'<g id="turn-{turn_num}" class="corner-marker">\n'
            f'  <circle cx="{cx}" cy="{cy}" r="7" fill="#09090b" stroke="#52525b" stroke-width="1.2"/>\n'
            f'  <text x="{cx}" y="{cy+2.8}" font-size="7" font-family="monospace" font-weight="800" fill="#ffffff" text-anchor="middle">{turn_num}</text>\n'
            f'</g>'
        )

        if turn_num in active_hotspots:
            hotspots_svg.append(
                f'<g id="track-limits-turn-{turn_num}" class="track-limits-zone" opacity="0.3">\n'
                f'  <circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="#ffb800" stroke-width="1.8" stroke-dasharray="3 3"/>\n'
                f'</g>'
            )

    corners_markup = "\n  ".join(corners_svg)
    hotspots_markup = "\n  ".join(hotspots_svg)

    sf_x, sf_y = round(nx[0], 1), round(ny[0], 1)

    st_idx = int(s2_end * 0.9)
    st_x, st_y = round(nx[st_idx], 1), round(ny[st_idx], 1)

    # Clean XML with CDATA wrapper around CSS to guarantee XML compliance
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <defs>
    <style type="text/css">
      <![CDATA[
      .sector {{ stroke: #2d2d34; stroke-width: 4px; fill: none; stroke-linecap: round; stroke-linejoin: round; }}
      .corner-marker circle {{ transition: all 0.2s ease; }}
      
      @keyframes f1-turn-pulse {{
        0% {{ stroke-width: 2px; r: 7px; filter: drop-shadow(0 0 4px #e10600); }}
        50% {{ stroke-width: 3.5px; r: 8.5px; filter: drop-shadow(0 0 10px #e10600); fill: #e10600; }}
        100% {{ stroke-width: 2px; r: 7px; filter: drop-shadow(0 0 4px #e10600); }}
      }}
      .highlight-f1-red circle, .active-turn circle {{
        stroke: #e10600 !important;
        stroke-width: 2.5px !important;
        fill: #e10600 !important;
        animation: f1-turn-pulse 1.8s infinite;
      }}
      .highlight-f1-red text, .active-turn text {{
        fill: #ffffff !important;
        font-weight: 900 !important;
      }}
      .highlight-sector {{
        stroke: #e10600 !important;
        stroke-width: 5.5px !important;
        filter: drop-shadow(0 0 8px rgba(225, 6, 0, 0.85));
      }}
      ]]>
    </style>
  </defs>

  <!-- SECTORS -->
  <g id="sectors">
    <path id="sector-1" class="sector" d="{path_s1}" />
    <path id="sector-2" class="sector" d="{path_s2}" />
    <path id="sector-3" class="sector" d="{path_s3}" />
  </g>

  <!-- PIT LANE -->
  <g id="pit-lane-group">
    <path id="pit-lane" fill="none" stroke="#1f1f24" stroke-width="2.5" stroke-linecap="round" d="{pit_d}" />
  </g>

  <!-- DRS ACTIVATION ZONES -->
  <g id="drs-zones">
    <path id="drs-active" fill="none" stroke="#22c55e" stroke-width="2.2" stroke-dasharray="5 3" opacity="0.45" d="{path_drs}" />
  </g>

  <!-- TRACK LIMITS HOTSPOTS -->
  <g id="track-limits-hotspots">
    {hotspots_markup}
  </g>

  <!-- START / FINISH LINE -->
  <g id="start-finish-line" transform="translate({sf_x}, {sf_y})">
    <line x1="-5" y1="-5" x2="5" y2="5" stroke="#ffffff" stroke-width="2" />
    <text x="0" y="-8" font-size="6" font-family="monospace" font-weight="700" fill="#a1a1aa" text-anchor="middle">S/F</text>
  </g>

  <!-- SPEED TRAP -->
  <g id="speed-trap-st" transform="translate({st_x}, {st_y})">
    <rect x="-3" y="-3" width="6" height="6" fill="#e11d48" opacity="0.8" rx="1"/>
    <text x="0" y="-6" font-size="6" font-family="monospace" font-weight="700" fill="#e11d48" text-anchor="middle">ST</text>
  </g>

  <!-- NUMBERED CORNERS -->
  <g id="corners">
    {corners_markup}
  </g>
</svg>'''

    filepath = f"assets/circuits/{slug}.svg"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"[{slug.upper()}] Generated -> {filepath}")
    return True

if __name__ == "__main__":
    print(f"Compiling complete master vector library ({len(ALL_CIRCUITS)} tracks)...")
    success = 0
    for slug, filename, turns in ALL_CIRCUITS:
        if generate_svg_from_source(slug, filename, turns):
            success += 1
    print(f"\nAll done! {success}/{len(ALL_CIRCUITS)} SVG files successfully saved to assets/circuits/")
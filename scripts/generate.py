#!/usr/bin/env python3
"""Render the profile README cards: a neofetch-style terminal and an app switcher.

Stats come from the public GitHub API and only public repositories are counted,
so nothing private can leak onto the profile. Everything in the config section
below is published as-is. Run `python3 scripts/generate.py` to regenerate.
"""

import calendar
import datetime as dt
import json
import math
import os
import struct
import urllib.request
import zlib
from pathlib import Path
from xml.sax.saxutils import escape

USER = "j0rdiun"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = json.loads((Path(__file__).parent / "icons.json").read_text())

# ---- config -----------------------------------------------------------------

PROMPT_USER = "jordan@j0rdiun"
COMMAND = "neofetch"

# (key, value) pairs. None marks a slot filled from the GitHub API.
INFO = [
    ("OS", "Pop!_OS 24.04 LTS x86_64"),
    ("Host", f"github.com/{USER}"),
    ("Uptime", None),
    ("Packages", None),
    ("Stars", None),
    ("Shell", "zsh"),
    ("DE", "COSMIC"),
    ("Terminal", "Ghostty"),
    ("Location", None),
    ("Langs", "Rust, TypeScript, Python"),
    ("Building", "cosmic-ext-app-switcher"),
]

# (icon, name, caption). Captions are shown under the switcher as it cycles.
SWITCHER = [
    ("popos", "Pop!_OS", "24.04 on COSMIC, the daily driver"),
    ("rust", "Rust", "cosmic-ext-app-switcher, the real version of this"),
    ("typescript", "TypeScript", "web apps and tooling"),
    ("python", "Python", "scripts, and the generator that draws this page"),
    ("react", "React", "front ends, plus React Native on mobile"),
    ("nodedotjs", "Node.js", "APIs and back ends"),
]

# The pug. One sprite draws both the terminal logo and assets/avatar.png, which gets
# uploaded by hand in GitHub Settings > Public profile. "." is transparent.
SPRITE = [
    "..KK........KK..",
    ".KKKFFFFFFFFKKK.",
    "KKKFFFFFFFFFFKKK",
    "KKFFFFDFFDFFFFKK",
    "KFFFFFFDDFFFFFFK",
    ".FFFFFFFFFFFFFF.",
    ".FFKKFFFFFFKKFF.",
    "FFKWKKFFFFKWKKFF",
    "FFKKKKFDDFKKKKFF",
    "FFFKKFNNNNFKKFFF",
    ".FFFFMNNNNMFFFF.",
    ".FFFMMMMMMMMFFF.",
    "..FFMMMMMMMMFF..",
    "..FFFMMPPMMFFF..",
    "...FFFMPPMFFF...",
    ".....FFFFFF.....",
]
SPRITE_COLOURS = {
    "F": "#e6c38f",  # fawn
    "D": "#c79b63",  # wrinkles
    "K": "#2a211d",  # ears and eyes
    "W": "#ffffff",  # eye shine
    "M": "#3b2f29",  # muzzle
    "N": "#17110e",  # nose
    "P": "#ef8a9a",  # tongue
}
# GitHub crops avatars to a circle, so the sprite sits centred on a larger grid.
AVATAR_GRID, AVATAR_CELL = 22, 48
AVATAR_BG = "#a07acd"

ANSI = [
    ["#3a3a3a", "#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#dcdfe4"],
    ["#5c6370", "#f08c94", "#b5e08f", "#f2d49a", "#8cc7f5", "#d9a3eb", "#7fd3dd", "#ffffff"],
]

# Terminal colours (the accent is the avatar's purple), plus the Dark and Light theme
# values from cosmic-ext-app-switcher's config/src/lib.rs for the switcher panel.
THEMES = {
    "dark": {
        "window": "#1b1b1b", "titlebar": "#262626", "border": "#ffffff1a",
        "fg": "#d4d4d4", "muted": "#9a9a9a", "c1": "#a07acd",
        "path": "#98c379", "shadow": 0.45,
        "panel": ("#212121", 0.92), "selected": ("#ffffff", 0.25), "panel_shadow": 0.6,
        "label": "#f0f6fc", "caption": "#9198a1",
    },
    "light": {
        "window": "#fbfbfb", "titlebar": "#ededed", "border": "#0000001f",
        "fg": "#2b2b2b", "muted": "#6b6b6b", "c1": "#8558b8",
        "path": "#3d7a1f", "shadow": 0.14,
        "panel": ("#f2f2f2", 0.88), "selected": ("#000000", 0.12), "panel_shadow": 0.22,
        "label": "#1f2328", "caption": "#59636e",
    },
}

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'DejaVu Sans Mono', 'Liberation Mono', monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
REDUCED_MOTION = "@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }"

# ---- data -------------------------------------------------------------------


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER},
    )
    if token := os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)


def public_repos():
    repos, page = [], 1
    while batch := api(f"/users/{USER}/repos?type=owner&per_page=100&page={page}"):
        repos += [r for r in batch if not r["private"]]
        page += 1
    return repos


def plural(n, unit):
    return f"{n} {unit}{'' if n == 1 else 's'}"


def uptime(since, today):
    months = (today.year - since.year) * 12 + today.month - since.month
    if today.day < since.day:
        months -= 1
    y, m = divmod(since.month - 1 + months, 12)
    year, month = since.year + y, m + 1
    anchor = dt.date(year, month, min(since.day, calendar.monthrange(year, month)[1]))
    years, months = divmod(months, 12)
    parts = [(years, "year"), (months, "month"), ((today - anchor).days, "day")]
    return ", ".join(plural(n, u) for n, u in parts if n) or "0 days"


def stats():
    user = api(f"/users/{USER}")
    repos = public_repos()
    own = [r for r in repos if not r["fork"]]
    created = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).date()
    return {
        "Uptime": uptime(created, dt.datetime.now(dt.timezone.utc).date()),
        "Packages": f"{len(own)} (repos), {len(repos) - len(own)} (forks)",
        "Stars": str(sum(r["stargazers_count"] for r in own)),
        "Location": user.get("location") or "Earth",
    }


# ---- neofetch card ----------------------------------------------------------

FONT, LINE, CH, PAD, BAR, MARGIN = 14, 19, 8.4, 24, 38, 14
CANVAS = 740  # both cards share this width so they line up; the terminal only grows if a line needs it


def run(col, row, text, cls, top):
    """A monospace run pinned to a character grid, whatever font the viewer has."""
    x = PAD + MARGIN + col * CH
    y = top + row * LINE
    return (
        f'<text x="{x:.1f}" y="{y}" class="{cls}" textLength="{len(text) * CH:.1f}" '
        f'lengthAdjust="spacingAndGlyphs">{escape(text)}</text>'
    )


def sprite_rects(x, y, size):
    """SVG rects for each sprite row, merging runs of the same colour."""
    rows = []
    for r, line in enumerate(SPRITE):
        rects, c = [], 0
        while c < len(line):
            end = c
            while end < len(line) and line[end] == line[c]:
                end += 1
            if line[c] != ".":
                rects.append(f'<rect x="{x + c * size:.1f}" y="{y + r * size:.1f}" width="{(end - c) * size}" '
                             f'height="{size}" fill="{SPRITE_COLOURS[line[c]]}"/>')
            c = end
        rows.append("".join(rects))
    return rows


def neofetch(theme, live):
    t = THEMES[theme]
    info_col = math.ceil(len(SPRITE[0]) * LINE / CH) + 4
    title = PROMPT_USER
    info = [[(0, title.split("@")[0], "c1 b"), (len(title.split("@")[0]), "@", "fg"),
             (len(title.split("@")[0]) + 1, title.split("@")[1], "c1 b")],
            [(0, "-" * len(title), "fg")]]
    for key, value in INFO:
        value = live[key] if value is None else value
        info.append([(0, f"{key}:", "c1 b"), (len(key) + 2, value, "fg")])
    info.append([])
    colour_rows = len(info)
    info += [[], []]

    rows = max(len(SPRITE), len(info))
    body_lines = rows + 4  # prompt, gap, rows, gap, prompt
    longest = max(len(k) + 2 + len(live.get(k) or v) for k, v in INFO)
    width = max(CANVAS - MARGIN * 2, PAD * 2 + round((info_col + longest) * CH) + 8)
    height = BAR + PAD * 2 + body_lines * LINE - (LINE - FONT)
    top = MARGIN + BAR + PAD + FONT - 2
    logo = sprite_rects(PAD + MARGIN, top + 2 * LINE - FONT - .5, LINE)
    W, H = width + MARGIN * 2, height + MARGIN * 2

    prompt = f"{PROMPT_USER}:~$ "
    type_start, type_step = 0.5, 0.075
    out_start = type_start + len(COMMAND) * type_step + 0.35
    row_step = 0.035
    end = out_start + rows * row_step + 0.25

    def prompt_line(row):
        user_len = len(PROMPT_USER)
        return (run(0, row, PROMPT_USER, "c1 b", top) + run(user_len, row, ":", "fg", top)
                + run(user_len + 1, row, "~", "path", top) + run(user_len + 2, row, "$", "fg", top))

    parts = [prompt_line(0)]
    for i, ch in enumerate(COMMAND):
        parts.append(f'<g class="type" style="animation-delay:{type_start + i * type_step:.3f}s">'
                     f'{run(len(prompt) + i, 0, ch, "fg", top)}</g>')

    for r in range(rows):
        cells = []
        if r < len(logo):
            cells.append(f'<g shape-rendering="crispEdges">{logo[r]}</g>')
        if r < len(info):
            cells += [run(info_col + c, r + 2, s, cls, top) for c, s, cls in info[r]]
        for band in range(2):
            if r == colour_rows + band:
                y = top + (r + 2) * LINE - FONT + 1
                for k, colour in enumerate(ANSI[band]):
                    x = PAD + MARGIN + (info_col + k * 3) * CH
                    cells.append(f'<rect x="{x:.1f}" y="{y}" width="{3 * CH:.1f}" height="{LINE - 2}" fill="{colour}"/>')
        if cells:
            parts.append(f'<g class="row" style="animation-delay:{out_start + r * row_step:.3f}s">{"".join(cells)}</g>')

    last = rows + 3
    cursor_x = PAD + MARGIN + len(prompt) * CH
    parts.append(
        f'<g class="row" style="animation-delay:{end:.3f}s">{prompt_line(last)}'
        f'<rect class="cursor" x="{cursor_x:.1f}" y="{top + last * LINE - FONT + 1}" width="{CH:.1f}" '
        f'height="{LINE - 2}" style="animation-delay:{end:.3f}s, {end:.3f}s"/></g>'
    )

    cx = W / 2
    buttons = "".join(
        f'<circle cx="{W - MARGIN - 20 - i * 26}" cy="{MARGIN + BAR / 2}" r="7" fill="{t["muted"]}" fill-opacity=".22"/>'
        for i in range(3)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title">
<title id="title">{escape(PROMPT_USER)} running neofetch</title>
<style>
text {{ font: {FONT}px {MONO}; white-space: pre; }}
.fg {{ fill: {t["fg"]}; }} .c1 {{ fill: {t["c1"]}; }} .path {{ fill: {t["path"]}; }} .b {{ font-weight: 700; }}
.title {{ font: 600 13px {SANS}; fill: {t["muted"]}; }}
.type {{ animation: appear .01s steps(1) backwards; }}
.row {{ animation: fade .3s ease-out backwards; }}
.cursor {{ fill: {t["fg"]}; animation: appear .01s steps(1) backwards, blink 1.1s steps(1) infinite; }}
@keyframes appear {{ from {{ opacity: 0; }} }}
@keyframes fade {{ from {{ opacity: 0; transform: translateY(3px); }} }}
@keyframes blink {{ 50% {{ opacity: 0; }} }}
{REDUCED_MOTION}
</style>
<defs>
<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000" flood-opacity="{t["shadow"]}"/></filter>
<clipPath id="window"><rect x="{MARGIN}" y="{MARGIN}" width="{width}" height="{height}" rx="12"/></clipPath>
</defs>
<rect x="{MARGIN}" y="{MARGIN}" width="{width}" height="{height}" rx="12" fill="{t["window"]}" filter="url(#shadow)"/>
<g clip-path="url(#window)"><rect x="{MARGIN}" y="{MARGIN}" width="{width}" height="{BAR}" fill="{t["titlebar"]}"/></g>
<rect x="{MARGIN + .5}" y="{MARGIN + .5}" width="{width - 1}" height="{height - 1}" rx="11.5" fill="none" stroke="{t["border"]}"/>
<text class="title" x="{cx}" y="{MARGIN + BAR / 2 + 4.5}" text-anchor="middle">{escape(PROMPT_USER)}: ~</text>
{buttons}
{chr(10).join(parts)}
</svg>
"""


# ---- app switcher -----------------------------------------------------------

# Values from cosmic-ext-app-switcher's src/ui.rs.
ICON, CELL_PAD, SPACING, PANEL_PAD_Y, PANEL_PAD_X, CORNER = 60, 10, 4, 14, 18, 14
DWELL, MOVE = 2.0, 0.18


# (tile background, glyph fill) per icon. Gradients are defined in switcher().
TILES = {
    "popos": ("#1f2a2c", "#48b9c7"),
    "rust": ("url(#rust-bg)", "#ffffff"),
    "typescript": ("#f4f7fb", "#3178c6"),
    "python": ("#1d2633", "url(#py-glyph)"),
    "react": ("#20232a", "#61dafb"),
    "nodedotjs": ("url(#node-bg)", "#ffffff"),
}


def icon_tile(slug, x, y):
    """An app-icon style tile: a rounded square with the Simple Icons glyph on top."""
    bg, glyph = TILES[slug]
    size = 36
    scale = size / 24
    offset = (ICON - size) / 2
    return (
        f'<rect x="{x}" y="{y}" width="{ICON}" height="{ICON}" rx="14" fill="{bg}"/>'
        f'<rect x="{x + .5}" y="{y + .5}" width="{ICON - 1}" height="{ICON - 1}" rx="13.5" fill="none" stroke="#fff" stroke-opacity=".08"/>'
        f'<path transform="translate({x + offset} {y + offset}) scale({scale})" fill="{glyph}" d="{ICONS[slug]}"/>'
    )


def switcher(theme):
    t = THEMES[theme]
    n = len(SWITCHER)
    cell = ICON + CELL_PAD * 2
    panel_w = n * cell + (n - 1) * SPACING + PANEL_PAD_X * 2
    panel_h = cell + PANEL_PAD_Y * 2
    W, py = CANVAS, 44
    px = (W - panel_w) / 2
    H = py + panel_h + 96
    total = n * DWELL
    step = cell + SPACING
    pct = lambda s: f"{s / total * 100:.3f}%"

    frames = [f"0% {{ transform: translateX(0px); }}"]
    for i in range(n - 1):
        frames.append(f"{pct((i + 1) * DWELL - MOVE)} {{ transform: translateX({i * step}px); }}")
        frames.append(f"{pct((i + 1) * DWELL)} {{ transform: translateX({(i + 1) * step}px); }}")
    frames.append(f"100% {{ transform: translateX({(n - 1) * step}px); }}")

    label = [
        f"0% {{ opacity: 0; }}",
        f"{pct(0.22)} {{ opacity: 1; }}",
        f"{pct(DWELL - MOVE - 0.12)} {{ opacity: 1; }}",
        f"{pct(DWELL - MOVE)} {{ opacity: 0; }}",
        f"100% {{ opacity: 0; }}",
    ]

    cells, labels = [], []
    for i, (slug, name, caption) in enumerate(SWITCHER):
        cx = px + PANEL_PAD_X + i * step
        cells.append(icon_tile(slug, cx + CELL_PAD, py + PANEL_PAD_Y + CELL_PAD))
        labels.append(
            f'<g class="label" style="animation-delay:{i * DWELL:.2f}s{";opacity:1" if i == 0 else ""}">'
            f'<text class="name" x="{W / 2}" y="{py + panel_h + 44}" text-anchor="middle">{escape(name)}</text>'
            f'<text class="caption" x="{W / 2}" y="{py + panel_h + 68}" text-anchor="middle">{escape(caption)}</text></g>'
        )

    panel_fill, panel_alpha = t["panel"]
    sel_fill, sel_alpha = t["selected"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title">
<title id="title">App switcher cycling through {escape(", ".join(name for _, name, _ in SWITCHER))}</title>
<style>
.name {{ font: 600 16px {SANS}; fill: {t["label"]}; }}
.caption {{ font: 14px {SANS}; fill: {t["caption"]}; }}
.selection {{ animation: select {total}s cubic-bezier(.3, .7, .4, 1) infinite; }}
.label {{ opacity: 0; animation: label {total}s linear infinite backwards; }}
@keyframes select {{ {" ".join(frames)} }}
@keyframes label {{ {" ".join(label)} }}
{REDUCED_MOTION}
</style>
<defs>
<filter id="shadow" x="-20%" y="-60%" width="140%" height="220%"><feDropShadow dx="0" dy="8" stdDeviation="16" flood-color="#000" flood-opacity="{t["panel_shadow"]}"/></filter>
<linearGradient id="rust-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4743b"/><stop offset="1" stop-color="#b7410e"/></linearGradient>
<linearGradient id="node-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#76c257"/><stop offset="1" stop-color="#3e863d"/></linearGradient>
<linearGradient id="py-glyph" x1="0" y1="0" x2="1" y2="1"><stop offset=".45" stop-color="#4b8bbe"/><stop offset=".55" stop-color="#ffd43b"/></linearGradient>
</defs>
<rect x="{px}" y="{py}" width="{panel_w}" height="{panel_h}" rx="{CORNER}" fill="{panel_fill}" fill-opacity="{panel_alpha}" filter="url(#shadow)"/>
<rect class="selection" x="{px + PANEL_PAD_X}" y="{py + PANEL_PAD_Y}" width="{cell}" height="{cell}" rx="{CORNER - 2}" fill="{sel_fill}" fill-opacity="{sel_alpha}"/>
{chr(10).join(cells)}
{chr(10).join(labels)}
</svg>
"""


# ---- avatar -----------------------------------------------------------------


def avatar_png(bg=AVATAR_BG):
    """The sprite as a flat PNG, written with the standard library only."""
    rgb = lambda h: bytes(int(h[i:i + 2], 16) for i in (1, 3, 5))
    colours = {key: rgb(value) for key, value in SPRITE_COLOURS.items()}
    background = rgb(bg)
    top = (AVATAR_GRID - len(SPRITE)) // 2
    left = (AVATAR_GRID - len(SPRITE[0])) // 2
    rows = []
    for gy in range(AVATAR_GRID):
        sprite_row = SPRITE[gy - top] if 0 <= gy - top < len(SPRITE) else ""
        cells = [colours.get(sprite_row[gx - left], background) if 0 <= gx - left < len(sprite_row) else background
                 for gx in range(AVATAR_GRID)]
        scanline = b"\x00" + b"".join(c * AVATAR_CELL for c in cells)
        rows.append(scanline * AVATAR_CELL)
    size = AVATAR_GRID * AVATAR_CELL

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


def main():
    live = stats()
    ASSETS.mkdir(exist_ok=True)
    for theme in THEMES:
        (ASSETS / f"neofetch-{theme}.svg").write_text(neofetch(theme, live))
        (ASSETS / f"switcher-{theme}.svg").write_text(switcher(theme))
    (ASSETS / "avatar.png").write_bytes(avatar_png())
    print(json.dumps(live, indent=2))


if __name__ == "__main__":
    main()

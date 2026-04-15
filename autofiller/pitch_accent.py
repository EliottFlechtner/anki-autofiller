"""Pitch accent lookup and SVG rendering from the Migaku pitch addon databases."""

from __future__ import annotations

import csv
import html
import os
import re
from functools import lru_cache
from pathlib import Path

_JA_RUN_RE = re.compile(
    r"[\u3041-\u3096\u30A0-\u30FF\u3400-\u4DB5\u4E00-\u9FCB\uF900-\uFA6A々]+"
)
_HIRA_RE = re.compile(r"[\u3041-\u3096]+")
_VARIATION_SELECTORS_RE = re.compile(r"[\U000E0100-\U000E013D]+")
_BRACKETED_RE = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")

ADDON_ID = "148002038"
DEFAULT_COMMENT_START = "accent_start"
DEFAULT_COMMENT_END = "accent_end"


def _to_katakana(text: str) -> str:
    return "".join(chr(ord(ch) + 96) if "ぁ" <= ch <= "ゔ" else ch for ch in text)


def _is_katakana(text: str) -> bool:
    if not text:
        return False
    count = sum(1 for ch in text if ch == "ー" or "ァ" <= ch <= "ヴ")
    return count / max(1, len(text)) > 0.5


def _clean_orth(text: str) -> str:
    text = re.sub(r"[()△×･〈〉{}]", "", text)
    return text.replace("…", "〜")


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_expression(text: str) -> str:
    text = _strip_html(text)
    text = _BRACKETED_RE.sub("", text)
    text = _VARIATION_SELECTORS_RE.sub("", text)
    match = _JA_RUN_RE.search(text)
    return match.group(0) if match else ""


def _reading_hint(text: str) -> str:
    match = _HIRA_RE.search(text or "")
    return match.group(0) if match else ""


def _addon_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".local/share/Anki2/addons21" / ADDON_ID,
        home / "Anki2/addons21" / ADDON_ID,
        home / ".config/Anki2/addons21" / ADDON_ID,
    ]
    extra = os.environ.get("ANKI_PITCH_ADDON_DIR")
    if extra:
        roots.insert(0, Path(extra))
    return roots


@lru_cache(maxsize=1)
def _load_pitch_dict() -> dict[str, list[tuple[str, str]]]:
    """Load and merge user and wadoku pitch dictionaries from addon paths."""
    combined: dict[str, list[tuple[str, str]]] = {}

    def add_entry(orth: str, hira: str, patt: str) -> None:
        if orth not in combined:
            combined[orth] = []
        entry = (hira, patt)
        if entry not in combined[orth]:
            combined[orth].append(entry)

    for root in _addon_roots():
        user_db = root / "user_pitchdb.csv"
        if user_db.exists():
            with user_db.open(encoding="utf-8") as handle:
                for raw_line in handle:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    parts = raw_line.split("\t")
                    if len(parts) != 3:
                        continue
                    orth, hira, patt = parts
                    add_entry(orth, hira, patt)

        wadoku_db = root / "wadoku_pitchdb.csv"
        if wadoku_db.exists():
            with wadoku_db.open(encoding="utf-8") as handle:
                for raw_line in handle:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    parts = raw_line.split("␞")
                    if len(parts) != 5:
                        continue
                    orths_txt, hira, _hz, _accs_txt, patts_txt = parts
                    orths = orths_txt.split("␟")
                    if orths and _clean_orth(orths[0]) != orths[0]:
                        orths = [_clean_orth(orths[0])] + orths
                    if orths and _is_katakana(orths[0]):
                        hira = _to_katakana(hira)
                    patt = patts_txt.split(",")[0]
                    for orth in orths:
                        add_entry(orth, hira, patt)

    return combined


def _select_best_pattern(
    reading_hint: str, candidates: list[tuple[str, str]]
) -> tuple[str, str]:
    best = candidates[0]
    best_pos = 10**9
    for hira, patt in candidates:
        try:
            pos = reading_hint.index(hira) if reading_hint else 0
        except ValueError:
            continue
        if pos < best_pos:
            best = (hira, patt)
            best_pos = pos
    return best


def pitch_pattern(expression: str, reading: str) -> tuple[str, str] | None:
    """Return `(hira, pattern)` if pitch data exists for the expression."""
    expr = _clean_expression(expression)
    if not expr:
        return None

    reading_hint = _reading_hint(reading)
    pitch_dict = _load_pitch_dict()
    candidates = pitch_dict.get(expr)
    if not candidates:
        return None
    return _select_best_pattern(reading_hint, candidates)


def _morae(word: str) -> list[str]:
    morae: list[str] = []
    combo = {
        "ゃ",
        "ゅ",
        "ょ",
        "ぁ",
        "ぃ",
        "ぅ",
        "ぇ",
        "ぉ",
        "ャ",
        "ュ",
        "ョ",
        "ァ",
        "ィ",
        "ゥ",
        "ェ",
        "ォ",
    }
    i = 0
    while i < len(word):
        if i + 1 < len(word) and word[i + 1] in combo:
            morae.append(word[i] + word[i + 1])
            i += 2
        else:
            morae.append(word[i])
            i += 1
    return morae


def _draw_circle(x: int, y: int, hollow: bool) -> str:
    outer = f'<circle r="5" cx="{x}" cy="{y}" style="opacity:1;fill:#000;" />'
    if hollow:
        outer += f'<circle r="3.25" cx="{x}" cy="{y}" style="opacity:1;fill:#fff;" />'
    return outer


def _draw_text(x: int, mora: str) -> str:
    if len(mora) == 1:
        return f'<text x="{x}" y="67.5" style="font-size:20px;font-family:sans-serif;fill:#000;">{mora}</text>'
    return (
        f'<text x="{x - 5}" y="67.5" style="font-size:20px;font-family:sans-serif;fill:#000;">{mora[0]}</text>'
        f'<text x="{x + 12}" y="67.5" style="font-size:14px;font-family:sans-serif;fill:#000;">{mora[1]}</text>'
    )


def _draw_path(x: int, y: int, step_width: int, direction: str) -> str:
    if direction == "s":
        delta = f"{step_width},0"
    elif direction == "u":
        delta = f"{step_width},-25"
    else:
        delta = f"{step_width},25"
    return f'<path d="m {x},{y} {delta}" style="fill:none;stroke:#000;stroke-width:1.5;" />'


def render_pitch_svg(word: str, pattern: str) -> str:
    """Render a compact SVG pitch graph from morae and accent pattern symbols."""
    morae = _morae(word)
    if not morae or not pattern:
        return ""

    positions = max(len(morae), len(pattern))
    step_width = 35
    margin_lr = 16
    width = max(0, ((positions - 1) * step_width) + (margin_lr * 2))

    svg_parts = [
        f'<svg class="pitch" width="{width}px" height="75px" viewBox="0 0 {width} 75">'
    ]

    for index, mora in enumerate(morae):
        x = margin_lr + (index * step_width)
        svg_parts.append(_draw_text(x - 11, mora))

    previous: tuple[int, int] | None = None
    for index, accent in enumerate(pattern):
        x = margin_lr + (index * step_width)
        y = 5 if accent in {"H", "h", "1", "2"} else 30
        svg_parts.append(_draw_circle(x, y, index >= len(morae)))
        if previous is not None:
            prev_x, prev_y = previous
            if prev_y == y:
                direction = "s"
            elif prev_y < y:
                direction = "d"
            else:
                direction = "u"
            svg_parts.append(_draw_path(prev_x, prev_y, step_width, direction))
        previous = (x, y)

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def enrich_html_with_pitch(expression: str, reading: str) -> str | None:
    """Build HTML-safe pitch SVG snippet wrapped in sentinel comments."""
    match = pitch_pattern(expression, reading)
    if not match:
        return None

    hira, pitch = match
    svg = render_pitch_svg(hira, pitch)
    if not svg:
        return None

    return f"<!-- {DEFAULT_COMMENT_START} -->{svg}<!-- {DEFAULT_COMMENT_END} -->"

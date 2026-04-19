"""Jisho HTTP client and extractors for word candidates and example sentences."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .models import ExampleSentence, SearchCandidate

JISHO_API = "https://jisho.org/api/v1/search/words?keyword={query}"


class JishoClient:
    """Minimal client for Jisho dictionary search and example extraction."""

    def _request(self, url: str) -> str:
        """Perform a GET request and return decoded response body text.

        Args:
            url: HTTP URL to request.

        Returns:
            Response body decoded as UTF-8 with replacement for invalid bytes.
        """
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"jisho2anki/{__version__}",
                "Accept": "application/json,text/html",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    def _extract_candidates(self, payload: str, limit: int) -> list[SearchCandidate]:
        """Extract reading/meaning candidates from the Jisho API JSON payload.

        Args:
            payload: Raw JSON text returned by the Jisho API.
            limit: Maximum number of candidate entries to parse.

        Returns:
            Candidate list with normalized reading/meaning pairs.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []

        items = data.get("data") or []
        candidates: list[SearchCandidate] = []

        for item in items[: max(limit, 1)]:
            japanese_entries = item.get("japanese") or []
            senses = item.get("senses") or []

            reading = ""
            if japanese_entries:
                reading = japanese_entries[0].get("reading") or ""

            sense_chunks: list[str] = []
            for sense in senses[:2]:
                definitions = sense.get("english_definitions") or []
                if definitions:
                    sense_chunks.append(", ".join(definitions[:4]))

            meaning = "; ".join(sense_chunks)
            candidates.append(SearchCandidate(meaning=meaning, reading=reading))

        return candidates

    def _sense_text(self, sense: dict[str, object], *, def_limit: int = 4) -> str:
        """Convert a Jisho sense object into compact meaning text."""
        definitions = (
            sense.get("english_definitions") if isinstance(sense, dict) else []
        )
        if not isinstance(definitions, list):
            return ""
        clean_defs = [str(defn) for defn in definitions if str(defn).strip()]
        return ", ".join(clean_defs[:def_limit])

    def _item_reading(self, item: dict[str, object]) -> str:
        """Return preferred reading for one Jisho item."""
        japanese_entries = item.get("japanese") if isinstance(item, dict) else []
        if not isinstance(japanese_entries, list):
            return ""
        for entry in japanese_entries:
            if isinstance(entry, dict):
                reading = str(entry.get("reading") or "").strip()
                if reading:
                    return reading
        return ""

    def _item_word(self, item: dict[str, object]) -> str:
        """Return preferred surface form for one Jisho item."""
        japanese_entries = item.get("japanese") if isinstance(item, dict) else []
        if not isinstance(japanese_entries, list):
            return ""
        for entry in japanese_entries:
            if isinstance(entry, dict):
                word = str(entry.get("word") or "").strip()
                if word:
                    return word
        return ""

    def _item_is_exact_match(self, item: dict[str, object], query: str) -> bool:
        """Check whether item directly matches requested query word/reading."""
        japanese_entries = item.get("japanese") if isinstance(item, dict) else []
        if not isinstance(japanese_entries, list):
            return False
        for entry in japanese_entries:
            if not isinstance(entry, dict):
                continue
            word = str(entry.get("word") or "").strip()
            reading = str(entry.get("reading") or "").strip()
            if word == query or reading == query:
                return True
        return False

    def _extract_review_candidates(
        self, payload: str, query: str, limit: int
    ) -> tuple[list[SearchCandidate], list[dict[str, str]]]:
        """Build review options from exact-match entries + related compound entries."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return [], []

        items = data.get("data") or []
        if not isinstance(items, list) or not items:
            return [], []

        target_limit = max(limit, 1)
        related_limit = max(target_limit, 8)

        exact_items = [
            item
            for item in items
            if isinstance(item, dict) and self._item_is_exact_match(item, query)
        ]
        source_items = (
            exact_items
            if exact_items
            else ([items[0]] if isinstance(items[0], dict) else [])
        )

        options: list[SearchCandidate] = []
        seen_option_keys: set[tuple[str, str]] = set()
        for source_item in source_items:
            reading = self._item_reading(source_item)
            senses = source_item.get("senses")
            if not isinstance(senses, list):
                continue

            for sense in senses:
                if not isinstance(sense, dict):
                    continue
                meaning = self._sense_text(sense)
                if not meaning:
                    continue
                key = (meaning, reading)
                if key in seen_option_keys:
                    continue
                seen_option_keys.add(key)
                options.append(SearchCandidate(meaning=meaning, reading=reading))

        if not options:
            fallback_reading = (
                self._item_reading(source_items[0]) if source_items else ""
            )
            options = [SearchCandidate(meaning="", reading=fallback_reading)]

        related: list[dict[str, str]] = []
        seen_words: set[str] = set()
        skip_items = set(id(item) for item in source_items)
        for item in items:
            if not isinstance(item, dict):
                continue
            if id(item) in skip_items:
                continue

            related_word = self._item_word(item)
            related_reading = self._item_reading(item)
            display_word = related_word or related_reading
            if not display_word or display_word in seen_words:
                continue
            if display_word == query:
                continue
            if query not in display_word:
                continue

            senses = item.get("senses")
            related_chunks: list[str] = []
            if isinstance(senses, list):
                for sense in senses[:2]:
                    if isinstance(sense, dict):
                        text = self._sense_text(sense)
                        if text:
                            related_chunks.append(text)
            meaning = "; ".join(related_chunks)

            seen_words.add(display_word)
            related.append(
                {
                    "word": display_word,
                    "reading": related_reading,
                    "meaning": meaning,
                }
            )
            if len(related) >= related_limit:
                break

        return options, related

    def _strip_tags(self, value: str) -> str:
        """Convert a small HTML fragment to normalized plain text.

        Args:
            value: HTML fragment text.

        Returns:
            Plain text with entities unescaped and whitespace collapsed.
        """
        text = re.sub(r"<[^>]+>", "", value)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _strip_sentence_source(self, english: str) -> str:
        """Remove trailing source-attribution suffix from an English sentence."""
        # Typical scraped suffixes look like: "... — Jreibun".
        # Keep this conservative: only strip short trailing labels preceded by spaced dash.
        cleaned = re.sub(r"\s+[—―-]\s*[A-Za-z][A-Za-z0-9 ._]{1,60}$", "", english)
        return cleaned.strip()

    def _extract_sentences(
        self, html_payload: str, limit: int
    ) -> list[ExampleSentence]:
        """Extract deduplicated Japanese/English sentence pairs from search HTML.

        Args:
            html_payload: HTML page content from a Jisho search result.
            limit: Maximum sentence pairs to return.

        Returns:
            Sentence pairs preserving source ordering up to `limit`.
        """
        if limit <= 0:
            return []

        pattern = re.compile(
            r'<ul class="japanese_sentence[^>]*>(.*?)</ul>\s*<div class="english_sentence clearfix">(.*?)</div>',
            re.DOTALL,
        )

        sentences: list[ExampleSentence] = []
        seen: set[tuple[str, str]] = set()

        for japanese_raw, english_raw in pattern.findall(html_payload):
            japanese_no_furigana = re.sub(
                r'<span class="furigana">.*?</span>', "", japanese_raw, flags=re.DOTALL
            )
            japanese = self._strip_tags(japanese_no_furigana)
            english = self._strip_sentence_source(self._strip_tags(english_raw))
            if not japanese or not english:
                continue

            key = (japanese, english)
            if key in seen:
                continue

            seen.add(key)
            sentences.append(ExampleSentence(japanese=japanese, english=english))
            if len(sentences) >= limit:
                break

        return sentences

    def search(
        self, word: str, candidate_limit: int, sentence_limit: int
    ) -> tuple[list[SearchCandidate], list[ExampleSentence]]:
        """Search Jisho API/HTML endpoints for candidates and example sentences.

        Args:
            word: Source vocabulary term.
            candidate_limit: Max number of API candidates to keep.
            sentence_limit: Max number of example sentences to keep.

        Returns:
            Tuple of `(candidates, sentences)`.
        """
        query = urllib.parse.quote(word)
        api_url = JISHO_API.format(query=query)
        html_url = f"https://jisho.org/search/{query}"

        candidates: list[SearchCandidate] = []
        sentences: list[ExampleSentence] = []

        try:
            payload = self._request(api_url)
            candidates = self._extract_candidates(payload, limit=candidate_limit)
        except (urllib.error.URLError, TimeoutError):
            pass

        try:
            html_payload = self._request(html_url)
            sentences = self._extract_sentences(html_payload, limit=sentence_limit)
        except (urllib.error.URLError, TimeoutError):
            pass

        return candidates, sentences

    def search_review(
        self, word: str, candidate_limit: int
    ) -> tuple[list[SearchCandidate], list[dict[str, str]]]:
        """Return review options + related words for one query.

        Options come from senses of top exact Jisho entry.
        Related entries are separate compound/near entries containing query text.
        """
        query = urllib.parse.quote(word)
        api_url = JISHO_API.format(query=query)

        try:
            payload = self._request(api_url)
        except (urllib.error.URLError, TimeoutError):
            return [], []

        return self._extract_review_candidates(
            payload, query=word, limit=candidate_limit
        )

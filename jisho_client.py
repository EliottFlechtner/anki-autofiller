from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from models import ExampleSentence, SearchCandidate

JISHO_API = "https://jisho.org/api/v1/search/words?keyword={query}"


class JishoClient:
    """Minimal client for Jisho dictionary search and example extraction."""

    def _request(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "anki-autofiller/0.3",
                "Accept": "application/json,text/html",
            },
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    def _extract_candidates(self, payload: str, limit: int) -> list[SearchCandidate]:
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

    def _strip_tags(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", "", value)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_sentences(
        self, html_payload: str, limit: int
    ) -> list[ExampleSentence]:
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
            english = self._strip_tags(english_raw)
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

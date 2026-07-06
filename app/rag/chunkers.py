from __future__ import annotations

import re
from dataclasses import dataclass

_CLAUSE_HEADER_RE = re.compile(
    r"^(Article\s+\d+(?:\(\d+\))?|Annex\s+[IVXLC]+|Clause\s+\d+):?.*$",
    re.MULTILINE,
)


@dataclass
class Chunk:
    text: str
    source_id: str
    regulation_name: str
    chunk_index: int
    clause_id: str | None = None
    strategy: str = "fixed"


def clause_chunks(text: str, source_id: str, regulation_name: str) -> list[Chunk]:
    """Splits on legal-structure headers (Article N, Annex N, Clause N). Each chunk is
    exactly one clause's text, whatever its length -- optimizes for citation precision
    (a retrieved chunk IS a citable clause) at the cost of uneven chunk sizes."""
    matches = list(_CLAUSE_HEADER_RE.finditer(text))
    if not matches:
        return [Chunk(text=text.strip(), source_id=source_id, regulation_name=regulation_name,
                       chunk_index=0, clause_id=None, strategy="clause")]

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        clause_id = m.group(1).strip()
        chunks.append(Chunk(text=body, source_id=source_id, regulation_name=regulation_name,
                             chunk_index=i, clause_id=clause_id, strategy="clause"))
    return chunks


def fixed_window_chunks(
    text: str, source_id: str, regulation_name: str, window_words: int = 300, overlap_words: int = 50,
) -> list[Chunk]:
    """Fixed word-count window with overlap, agnostic to document structure -- robust to
    messy/OCR'd source text, but can split a clause mid-sentence or merge two unrelated
    clauses into one chunk, hurting citation precision."""
    words = text.split()
    if not words:
        return []
    step = max(window_words - overlap_words, 1)
    chunks = []
    idx = 0
    for i, start in enumerate(range(0, len(words), step)):
        window = words[start : start + window_words]
        if not window:
            break
        chunks.append(Chunk(
            text=" ".join(window), source_id=source_id, regulation_name=regulation_name,
            chunk_index=idx, clause_id=None, strategy="fixed",
        ))
        idx += 1
        if start + window_words >= len(words):
            break
    return chunks

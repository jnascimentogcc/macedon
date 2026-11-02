"""Structural chunking.

Blocks are grouped into sections (one per heading). Inside a section, blocks are packed into
small chunks, so search is precise; retrieval later hands the model the whole parent section.
Each chunk carries the document path ("Contract > Clause 5 > Termination") that is prepended
before embedding, which resolves ambiguous passages such as "the term will be 30 days".
"""

import hashlib
import re
from dataclasses import dataclass

from macedon.ingestion.extract import Block

TARGET_TOKENS = 200  # chunks are packed up to this size (small chunks, precise search)
MAX_TOKENS = 800  # a single paragraph above this is split by sentences
OVERLAP_RATIO = 0.12  # applied only when a paragraph has to be split

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Cheap estimate (about 4 characters per token); no tokenizer download is needed."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class Chunk:
    section_id: str
    position: int
    page: int | None
    path: str
    content: str

    @property
    def embedding_text(self) -> str:
        return f"{self.path}\n\n{self.content}"

    @property
    def content_hash(self) -> str:
        """Hash of the exact text that gets embedded, so equal text reuses its embedding."""
        return hashlib.sha256(self.embedding_text.encode()).hexdigest()


@dataclass
class _Section:
    section_id: str
    path: str
    blocks: list[Block]


def chunk_document(blocks: list[Block], document_name: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _sections(blocks, document_name):
        for content, page in _pack(section.blocks):
            chunks.append(Chunk(section.section_id, len(chunks), page, section.path, content))
    return chunks


def _sections(blocks: list[Block], document_name: str) -> list[_Section]:
    sections: list[_Section] = []
    headings: list[tuple[int, str]] = []  # (level, text) of the current heading path
    current = _Section("s0", document_name, [])

    def close() -> None:
        if current.blocks:
            sections.append(current)

    for block in blocks:
        if block.kind == "heading":
            close()
            while headings and headings[-1][0] >= block.level:
                headings.pop()
            headings.append((block.level, block.text))
            path = " > ".join([document_name, *_distinct_headings(headings, document_name)])
            current = _Section(f"s{len(sections) + 1}", path, [])
        else:
            current.blocks.append(block)
    close()
    return sections


def _distinct_headings(headings: list[tuple[int, str]], document_name: str) -> list[str]:
    """Heading texts for the path, without repeating the document name or a heading twice.

    Documents often open with a title equal to their name ("Travel Policy" inside the document
    "Travel Policy"), which would otherwise show up twice in every path.
    """
    texts: list[str] = []
    for _, heading in headings:
        previous = texts[-1] if texts else document_name
        if heading.strip().casefold() != previous.strip().casefold():
            texts.append(heading)
    return texts


def _pack(blocks: list[Block]) -> list[tuple[str, int | None]]:
    """Greedily pack blocks into chunks of about TARGET_TOKENS. Returns (text, first page)."""
    packed: list[tuple[str, int | None]] = []
    buffer: list[str] = []
    buffer_page: int | None = None
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer, buffer_page, buffer_tokens
        if buffer:
            packed.append(("\n\n".join(buffer), buffer_page))
        buffer, buffer_page, buffer_tokens = [], None, 0

    for block in blocks:
        tokens = estimate_tokens(block.text)
        if tokens > MAX_TOKENS and block.kind == "paragraph":
            flush()
            packed.extend((piece, block.page) for piece in _split_paragraph(block.text))
            continue
        if tokens >= TARGET_TOKENS or block.kind in ("table", "list"):
            # Big blocks, tables and lists are never merged with neighbours and never cut.
            flush()
            packed.append((block.text, block.page))
            continue
        if buffer and buffer_tokens + tokens > TARGET_TOKENS:
            flush()
        if not buffer:
            buffer_page = block.page
        buffer.append(block.text)
        buffer_tokens += tokens
    flush()
    return packed


def _split_paragraph(text: str) -> list[str]:
    """Split an oversized paragraph on sentence boundaries, repeating a short overlap."""
    sentences = [s for s in _SENTENCE_BOUNDARY.split(text) if s]
    # A "sentence" longer than the limit (no punctuation) is cut on whitespace.
    units: list[str] = []
    for sentence in sentences:
        if estimate_tokens(sentence) <= MAX_TOKENS:
            units.append(sentence)
        else:
            units.extend(_cut_on_words(sentence))

    pieces: list[str] = []
    current: list[str] = []
    for unit in units:
        if current and estimate_tokens(" ".join([*current, unit])) > MAX_TOKENS:
            pieces.append(" ".join(current))
            current = _overlap_tail(current)
            if current and estimate_tokens(" ".join([*current, unit])) > MAX_TOKENS:
                current = []  # no room for the overlap next to this unit
        current.append(unit)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap_tail(units: list[str]) -> list[str]:
    budget = int(MAX_TOKENS * OVERLAP_RATIO)
    tail: list[str] = []
    used = 0
    for unit in reversed(units):
        used += estimate_tokens(unit)
        if used > budget and tail:
            break
        tail.insert(0, unit)
    return tail


def _cut_on_words(text: str) -> list[str]:
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for word in words:
        if current and size + len(word) + 1 > MAX_TOKENS * 4:
            pieces.append(" ".join(current))
            current, size = [], 0
        current.append(word)
        size += len(word) + 1
    if current:
        pieces.append(" ".join(current))
    return pieces

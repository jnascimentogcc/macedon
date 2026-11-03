"""Turn a PDF, DOCX or TXT file into an ordered list of structural blocks.

This is the code that parses untrusted files, so it runs in an isolated subprocess (see
`macedon.ingestion.sandbox`). It must stay free of database, network and storage access.
"""

import io
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

import docx
import pymupdf
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

BlockKind = Literal["heading", "paragraph", "table", "list"]

HEADING_SIZE_RATIO = 1.15
MAX_HEADING_CHARS = 160


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str
    page: int | None = None
    level: int = 0  # heading depth, 1 is the top; 0 for non-headings

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Block":
        return cls(**data)


class ExtractionError(ValueError):
    pass


def extract_blocks(data: bytes, doc_type: str) -> list[Block]:
    extractors = {"pdf": _extract_pdf, "docx": _extract_docx, "txt": _extract_txt}
    try:
        extractor = extractors[doc_type]
    except KeyError:
        raise ExtractionError(f"unsupported document type: {doc_type}") from None
    blocks = extractor(data)
    if not blocks:
        raise ExtractionError("no text could be extracted from the document")
    return blocks


# ---- TXT ----


def _extract_txt(data: bytes) -> list[Block]:
    text = data.decode("utf-8-sig").replace("\r\n", "\n")
    paragraphs = (
        re.sub(r"[ \t]*\n[ \t]*", " ", part).strip() for part in re.split(r"\n\s*\n", text)
    )
    return [Block("paragraph", paragraph) for paragraph in paragraphs if paragraph]


# ---- DOCX ----


def _extract_docx(data: bytes) -> list[Block]:
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises a variety of errors on malformed files
        raise ExtractionError(f"could not read the DOCX file: {exc}") from exc

    blocks: list[Block] = []
    for child in _iter_body(document):
        if isinstance(child, Paragraph):
            block = _docx_paragraph(child)
        else:
            block = _docx_table(child)
        if block is not None:
            blocks.append(block)
    return blocks


def _iter_body(document: DocxDocument) -> list[Paragraph | Table]:
    items: list[Paragraph | Table] = []
    for element in document.element.body.iterchildren():
        if element.tag == qn("w:p"):
            items.append(Paragraph(element, document))
        elif element.tag == qn("w:tbl"):
            items.append(Table(element, document))
    return items


def _docx_paragraph(paragraph: Paragraph) -> Block | None:
    text = paragraph.text.strip()
    if not text:
        return None
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    if style == "Title":
        return Block("heading", text, level=1)
    heading = re.fullmatch(r"Heading (\d)", style)
    if heading:
        return Block("heading", text, level=int(heading.group(1)))
    if style.startswith("List"):
        return Block("list", text)
    return Block("paragraph", text)


def _docx_table(table: Table) -> Block | None:
    rows = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return Block("table", "\n".join(rows)) if rows else None


# ---- PDF ----


@dataclass
class _Line:
    text: str
    size: float
    page: int


def _extract_pdf(data: bytes) -> list[Block]:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"could not read the PDF file: {exc}") from exc
    if document.needs_pass:
        raise ExtractionError("the PDF is password protected")

    lines: list[_Line] = []
    for page_number in range(1, document.page_count + 1):
        page = document[page_number - 1]
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:  # 0 is a text block; skip images
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if spans:
                    text = "".join(s["text"] for s in spans).strip()
                    size = max(s["size"] for s in spans)
                    lines.append(_Line(text, size, page_number))
    return _pdf_lines_to_blocks(lines)


def _pdf_lines_to_blocks(lines: list[_Line]) -> list[Block]:
    if not lines:
        return []
    # The body size is the most common size, weighted by characters.
    weights: Counter[float] = Counter()
    for line in lines:
        weights[round(line.size, 1)] += len(line.text)
    body_size = weights.most_common(1)[0][0]
    heading_sizes = sorted(
        {
            round(line.size, 1)
            for line in lines
            if line.size >= body_size * HEADING_SIZE_RATIO and len(line.text) <= MAX_HEADING_CHARS
        },
        reverse=True,
    )
    level_of = {size: index + 1 for index, size in enumerate(heading_sizes[:6])}

    blocks: list[Block] = []
    paragraph: list[_Line] = []

    def flush() -> None:
        if paragraph:
            text = re.sub(r"-\n", "", " ".join(line.text for line in paragraph))
            blocks.append(Block("paragraph", " ".join(text.split()), page=paragraph[0].page))
            paragraph.clear()

    previous: _Line | None = None
    for line in lines:
        level = level_of.get(round(line.size, 1))
        if level is not None:
            flush()
            if (
                previous is not None
                and blocks
                and _is_continuation_heading(blocks[-1], previous, line)
            ):
                last = blocks[-1]
                blocks[-1] = Block("heading", f"{last.text} {line.text}", last.page, last.level)
            else:
                blocks.append(Block("heading", line.text, page=line.page, level=level))
        else:
            if paragraph and (
                line.page != paragraph[-1].page and _ends_sentence(paragraph[-1].text)
            ):
                flush()
            paragraph.append(line)
            if _ends_sentence(line.text) and len(" ".join(x.text for x in paragraph)) > 600:
                flush()
        previous = line
    flush()
    return blocks


def _is_continuation_heading(last: Block, previous: _Line, line: _Line) -> bool:
    """A heading wrapped over two lines arrives as two consecutive heading lines."""
    return (
        last.kind == "heading"
        and previous.size == line.size
        and previous.page == line.page
        and last.page == line.page
    )


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", ":", ";"))

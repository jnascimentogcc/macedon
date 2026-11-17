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

RUNNING_ZONE = 0.15  # a line in the top or bottom 15% of the page may be a running header/footer
MIN_PAGES_FOR_RUNNING_LINES = 4
MAX_BOLD_HEADING_CHARS = 100
BOLD_BODY_RATIO = 0.95  # a bold line this close to the body size counts as body-sized

# Structural labels that open a heading: "Cláusula 5.ª", "Artigo 10.º", "CAPÍTULO IV", "Annex A".
# The number matters: it keeps ordinary sentences such as "Part of the plan" out. The label decides
# the heading depth, because documents set the same kind of label in different sizes.
_LABEL_GROUPS: tuple[tuple[str, ...], ...] = (
    ("cap[ií]tulo", "parte", "t[ií]tulo", "anexo", "chapter", "part", "title", "annex", "appendix"),
    ("se[cç][aã]o", "section", "secci[oó]n"),
    ("artigo", "cl[aá]usula", "article", "clause", "art[ií]culo"),
)
_LABEL = re.compile(
    "^(?:" + "|".join(f"(?P<g{i}>{'|'.join(group)})" for i, group in enumerate(_LABEL_GROUPS)) + ")"
    r"\s+(?:\d+|[IVXLCDM]+|[A-Z])(?![^\W\d_])[\w.º°ª-]*(?=\s|$)",
    re.IGNORECASE,
)


@dataclass
class _Line:
    text: str
    size: float
    page: int
    bold: bool = False
    top: float = 0.5  # vertical position on the page: 0 is the top edge, 1 the bottom


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
        height = page.rect.height or 1.0
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:  # 0 is a text block; skip images
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if spans:
                    size = max(s["size"] for s in spans)
                    middle = (line["bbox"][1] + line["bbox"][3]) / 2 / height
                    lines.append(
                        _Line(_join_spans(spans), size, page_number, _all_bold(spans), middle)
                    )
    return _pdf_lines_to_blocks(_drop_running_lines(lines))


def _join_spans(spans: list[dict[str, Any]]) -> str:
    """The text of a line. Spans that sit apart but carry no space ("b)" then "Encargos") are
    separated, otherwise they would be glued into "b)Encargos"."""
    text: str = spans[0]["text"]
    for before, after in zip(spans, spans[1:], strict=False):
        gap = after["bbox"][0] - before["bbox"][2]
        no_space = not before["text"].endswith(" ") and not after["text"].startswith(" ")
        if gap > 0.15 * after["size"] and no_space:
            text += " "
        text += after["text"]
    return text.strip()


def _all_bold(spans: list[dict[str, Any]]) -> bool:
    return all(bool(s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)


def _running_key(text: str) -> str:
    """Page numbers change from page to page, so digits are masked before comparing lines."""
    return re.sub(r"\d+", "#", " ".join(text.split()).lower())


def _in_margin(line: _Line) -> bool:
    return line.top < RUNNING_ZONE or line.top > 1 - RUNNING_ZONE


def _drop_running_lines(lines: list[_Line]) -> list[_Line]:
    """Remove page headers and footers: lines in the page margins whose text (digits aside)
    repeats on at least half of the pages. They would otherwise be glued into the chunks."""
    pages = {line.page for line in lines}
    if len(pages) < MIN_PAGES_FOR_RUNNING_LINES:
        return lines
    seen: dict[str, set[int]] = {}
    for line in lines:
        if _in_margin(line):
            seen.setdefault(_running_key(line.text), set()).add(line.page)
    threshold = max(3, len(pages) // 2)
    running = {key for key, where in seen.items() if len(where) >= threshold}
    return [line for line in lines if not (_in_margin(line) and _running_key(line.text) in running)]


def _label(text: str) -> tuple[int, bool] | None:
    """For a line that opens with a structural label: (rank of the label, is it only the label)."""
    match = _LABEL.match(text.strip())
    if match is None:
        return None
    rank = next(i for i in range(len(_LABEL_GROUPS)) if match.group(f"g{i}"))
    return rank, match.end() >= len(text.strip())


def _is_bold_body_line(line: _Line, body_size: float) -> bool:
    return (
        line.bold
        and line.size >= body_size * BOLD_BODY_RATIO
        and len(line.text) <= MAX_BOLD_HEADING_CHARS
        and not _ends_sentence(line.text)
    )


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
    label_base = len(level_of)  # labelled headings sit below every heading found by size

    blocks: list[Block] = []
    paragraph: list[_Line] = []

    def flush() -> None:
        if paragraph:
            text = re.sub(r"-\n", "", " ".join(line.text for line in paragraph))
            blocks.append(Block("paragraph", " ".join(text.split()), page=paragraph[0].page))
            paragraph.clear()

    previous: _Line | None = None
    for line in lines:
        sized = level_of.get(round(line.size, 1))
        bold_title = _is_bold_body_line(line, body_size)
        label = _label(line.text)
        if (
            previous is not None
            and not paragraph
            and blocks
            and _extends_heading(blocks[-1], previous, line, sized is not None, bold_title, label)
        ):
            last = blocks[-1]
            blocks[-1] = Block("heading", f"{last.text} {line.text}", last.page, last.level)
        else:
            level = label_base + 1 + label[0] if label and (sized or bold_title) else sized
            if level is not None:
                flush()
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


def _extends_heading(
    last: Block,
    previous: _Line,
    line: _Line,
    sized: bool,
    bold_title: bool,
    label: tuple[int, bool] | None,
) -> bool:
    """Whether `line` continues the heading `last` instead of starting a new block.

    Three cases: a heading wrapped over two lines of the same size; a bare label ("Artigo 14.º")
    followed by its title, whatever the sizes (titles are often set larger or smaller than the
    label); and a bold heading wrapped over two bold lines.
    """
    if last.kind != "heading" or label is not None:
        return False
    if previous.page != line.page or last.page != line.page:
        return False
    if len(last.text) + len(line.text) > MAX_HEADING_CHARS:
        return False
    last_label = _label(last.text)
    if last_label is not None and last_label[1] and (sized or bold_title):
        return True
    if sized and previous.size == line.size:
        return True
    return bold_title and previous.bold and abs(previous.size - line.size) < 0.1


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", ":", ";"))

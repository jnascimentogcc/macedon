import io

import docx
import pymupdf
import pytest

from macedon.ingestion.extract import Block, ExtractionError, extract_blocks


def make_pdf(pages: list[list[tuple[str, int]]]) -> bytes:
    """Each page is a list of (text, font size) lines, written top to bottom."""
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        y = 72.0
        for text, size in lines:
            page.insert_text((72, y), text, fontsize=size)
            y += size * 1.8
    return bytes(document.tobytes())


def test_txt_splits_on_blank_lines_and_joins_wrapped_lines() -> None:
    data = b"First line\nwrapped here.\n\n\nSecond paragraph.\r\n\r\nThird."

    blocks = extract_blocks(data, "txt")

    assert [b.text for b in blocks] == ["First line wrapped here.", "Second paragraph.", "Third."]
    assert all(b.kind == "paragraph" for b in blocks)


def test_txt_with_only_whitespace_is_an_error() -> None:
    with pytest.raises(ExtractionError):
        extract_blocks(b"  \n\n \n", "txt")


def test_docx_reads_headings_paragraphs_lists_and_tables_in_order() -> None:
    document = docx.Document()
    document.add_heading("Contract", level=1)
    document.add_paragraph("Intro paragraph.")
    document.add_heading("Termination", level=2)
    document.add_paragraph("Item one", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Plan"
    table.cell(0, 1).text = "Price"
    table.cell(1, 0).text = "Basic"
    table.cell(1, 1).text = "10"
    document.add_paragraph("Closing.")
    buffer = io.BytesIO()
    document.save(buffer)

    blocks = extract_blocks(buffer.getvalue(), "docx")

    assert blocks == [
        Block("heading", "Contract", level=1),
        Block("paragraph", "Intro paragraph."),
        Block("heading", "Termination", level=2),
        Block("list", "Item one"),
        Block("table", "Plan | Price\nBasic | 10"),
        Block("paragraph", "Closing."),
    ]


def test_broken_docx_is_an_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_blocks(b"PK\x03\x04 not really a docx", "docx")


def test_pdf_detects_headings_by_font_size_and_records_pages() -> None:
    pdf = make_pdf(
        [
            [
                ("Annual Report", 24),
                ("Revenue", 16),
                ("Revenue grew by ten percent in the year.", 11),
                ("Costs stayed flat across all regions.", 11),
            ],
            [("Outlook", 16), ("We expect further growth next year.", 11)],
        ]
    )

    blocks = extract_blocks(pdf, "pdf")

    assert [(b.kind, b.text, b.level, b.page) for b in blocks] == [
        ("heading", "Annual Report", 1, 1),
        ("heading", "Revenue", 2, 1),
        (
            "paragraph",
            "Revenue grew by ten percent in the year. Costs stayed flat across all regions.",
            0,
            1,
        ),
        ("heading", "Outlook", 2, 2),
        ("paragraph", "We expect further growth next year.", 0, 2),
    ]


def test_pdf_without_text_is_an_extraction_error() -> None:
    document = pymupdf.open()
    document.new_page()

    with pytest.raises(ExtractionError):
        extract_blocks(bytes(document.tobytes()), "pdf")


def test_garbage_pdf_is_an_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_blocks(b"%PDF-1.7 this is not a pdf", "pdf")


def test_unknown_type_is_an_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_blocks(b"x", "rtf")

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


def make_styled_pdf(
    pages: list[list[tuple[str, float, bool]]],
    header: str | None = None,
    footer: str | None = None,
) -> bytes:
    """Pages of (text, size, bold) lines, plus an optional running header and footer.

    "{n}" in the header or footer is replaced by the page number.
    """
    document = pymupdf.open()
    for number, lines in enumerate(pages, start=1):
        page = document.new_page()
        if header:
            page.insert_text((72, 30), header.format(n=number), fontsize=8)
        if footer:
            page.insert_text((72, 820), footer.format(n=number), fontsize=8)
        y = 200.0
        for text, size, bold in lines:
            page.insert_text((72, y), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += size * 1.8
    return bytes(document.tobytes())


def test_pdf_running_headers_and_footers_are_dropped() -> None:
    body = [("The supplier shall deliver the goods on time.", 10.0, False)]
    pdf = make_styled_pdf(
        [body] * 6, header="ACME Agency | Page {n} of 6", footer="Confidential {n}"
    )

    texts = [b.text for b in extract_blocks(pdf, "pdf")]

    assert texts
    assert not any("ACME" in t or "Confidential" in t or "Page" in t for t in texts)


def test_pdf_short_documents_keep_their_margin_lines() -> None:
    body = [("The supplier shall deliver the goods on time.", 10.0, False)]
    pdf = make_styled_pdf([body] * 2, header="ACME Agency | Page {n} of 2")

    assert any("ACME" in b.text for b in extract_blocks(pdf, "pdf"))


def test_pdf_a_line_that_is_not_in_the_margin_is_kept_even_when_repeated() -> None:
    line = ("See the annex for the price table of each lot.", 10.0, False)
    pdf = make_styled_pdf([[line]] * 6)  # same text on every page, but in the body of the page

    assert sum("price table" in b.text for b in extract_blocks(pdf, "pdf")) >= 1


def test_pdf_bold_clause_labels_become_headings_with_their_title() -> None:
    body = "The payment is made within thirty days of receiving each invoice."
    pdf = make_styled_pdf(
        [
            [
                ("Clause 5", 10.0, True),
                ("Payment terms", 10.0, True),
                (body, 10.0, False),
                (body, 10.0, False),
                ("Clause 6", 10.0, True),
                ("Intellectual property", 10.0, True),
                (body, 10.0, False),
            ]
        ]
    )

    blocks = extract_blocks(pdf, "pdf")

    headings = [(b.text, b.level) for b in blocks if b.kind == "heading"]
    assert headings == [("Clause 5 Payment terms", 3), ("Clause 6 Intellectual property", 3)]


def test_pdf_label_and_title_in_different_sizes_stay_one_heading_of_the_same_depth() -> None:
    body = "The committee answers questions in writing through the platform."
    pdf = make_styled_pdf(
        [
            [
                ("Article 10", 13.0, False),
                ("Variant proposals", 13.0, False),
                (body, 10.0, False),
                ("Article 11", 12.0, False),  # same kind of label, another size
                ("Deadline for proposals", 13.0, False),
                (body, 10.0, False),
                (body, 10.0, False),
                (body, 10.0, False),
            ]
        ]
    )

    blocks = extract_blocks(pdf, "pdf")

    headings = [(b.text, b.level) for b in blocks if b.kind == "heading"]
    assert [text for text, _ in headings] == [
        "Article 10 Variant proposals",
        "Article 11 Deadline for proposals",
    ]
    assert headings[0][1] == headings[1][1]  # siblings, not nested


def test_pdf_a_bold_sentence_that_only_starts_like_a_label_is_not_a_heading() -> None:
    pdf = make_styled_pdf(
        [
            [
                ("Part of the plan is to ship early.", 10.0, True),
                ("Section a bit later in the text, we explain why.", 10.0, False),
                ("The rest of the paragraph is ordinary body text here.", 10.0, False),
            ]
        ]
    )

    assert [b.kind for b in extract_blocks(pdf, "pdf")] == ["paragraph"]


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

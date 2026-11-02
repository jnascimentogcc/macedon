from macedon.ingestion.chunking import (
    MAX_TOKENS,
    TARGET_TOKENS,
    chunk_document,
    estimate_tokens,
)
from macedon.ingestion.extract import Block


def paragraph(words: int, page: int | None = None, seed: str = "word") -> Block:
    return Block("paragraph", " ".join(f"{seed}{i}" for i in range(words)), page=page)


def test_path_prefix_follows_the_heading_hierarchy() -> None:
    blocks = [
        Block("heading", "Clause 5", level=1),
        Block("heading", "Termination", level=2),
        Block("paragraph", "The term will be 30 days."),
        Block("heading", "Payment", level=2),
        Block("paragraph", "Invoices are due in 15 days."),
        Block("heading", "Clause 6", level=1),
        Block("paragraph", "Confidentiality applies."),
    ]

    chunks = chunk_document(blocks, "Contract X")

    assert [c.path for c in chunks] == [
        "Contract X > Clause 5 > Termination",
        "Contract X > Clause 5 > Payment",
        "Contract X > Clause 6",
    ]
    assert chunks[0].embedding_text == (
        "Contract X > Clause 5 > Termination\n\nThe term will be 30 days."
    )


def test_text_before_any_heading_uses_the_document_name() -> None:
    chunks = chunk_document([Block("paragraph", "Intro text.")], "Notes")

    assert chunks[0].path == "Notes"


def test_each_section_gets_its_own_id_and_positions_are_global() -> None:
    blocks = [
        Block("heading", "A", level=1),
        Block("paragraph", "a1"),
        Block("heading", "B", level=1),
        Block("paragraph", "b1"),
    ]

    chunks = chunk_document(blocks, "Doc")

    assert [(c.section_id, c.position) for c in chunks] == [("s1", 0), ("s2", 1)]


def test_small_paragraphs_are_packed_up_to_the_target() -> None:
    blocks = [paragraph(20, seed=f"p{n}_") for n in range(30)]

    chunks = chunk_document(blocks, "Doc")

    assert len(chunks) > 1
    assert all(estimate_tokens(c.content) <= TARGET_TOKENS + 40 for c in chunks)
    assert {b.text for b in blocks} == {
        part for c in chunks for part in c.content.split("\n\n")
    }  # nothing lost, nothing cut


def test_a_paragraph_over_the_target_stays_whole() -> None:
    big = paragraph(300)  # well over the target, under the maximum
    assert TARGET_TOKENS < estimate_tokens(big.text) < MAX_TOKENS

    chunks = chunk_document([paragraph(5), big, paragraph(5)], "Doc")

    assert [c.content for c in chunks][1] == big.text
    assert len(chunks) == 3


def test_tables_and_lists_are_never_merged_or_cut() -> None:
    table = Block("table", "\n".join(f"row{i} | value{i}" for i in range(500)))
    assert estimate_tokens(table.text) > MAX_TOKENS
    blocks = [paragraph(5), table, Block("list", "- one\n- two"), paragraph(5)]

    chunks = chunk_document(blocks, "Doc")

    assert [c.content for c in chunks][1] == table.text
    assert [c.content for c in chunks][2] == "- one\n- two"
    assert len(chunks) == 4


def test_a_huge_paragraph_is_split_on_sentences_with_overlap() -> None:
    sentences = [f"This is sentence number {n} of a very long paragraph." for n in range(400)]
    text = " ".join(sentences)
    assert estimate_tokens(text) > MAX_TOKENS * 3

    chunks = chunk_document([Block("paragraph", text)], "Doc")

    assert len(chunks) >= 3
    assert all(estimate_tokens(c.content) <= MAX_TOKENS for c in chunks)
    assert all(c.content.endswith(".") for c in chunks)  # cut on sentence boundaries
    for previous, following in zip(chunks, chunks[1:], strict=False):
        last_sentence = previous.content.rsplit(". ", 1)[-1]
        assert last_sentence in following.content  # the overlap repeats the tail
    covered = " ".join(c.content for c in chunks)
    assert all(s in covered for s in sentences)


def test_text_without_punctuation_is_still_split() -> None:
    text = " ".join(f"w{i}" for i in range(5000))

    chunks = chunk_document([Block("paragraph", text)], "Doc")

    assert len(chunks) > 1
    assert all(estimate_tokens(c.content) <= MAX_TOKENS for c in chunks)


def test_chunk_keeps_the_first_page() -> None:
    blocks = [paragraph(10, page=3), paragraph(10, page=4)]

    chunks = chunk_document(blocks, "Doc")

    assert chunks[0].page == 3


def test_equal_text_in_different_sections_hashes_differently() -> None:
    blocks = [
        Block("heading", "A", level=1),
        Block("paragraph", "same words"),
        Block("heading", "B", level=1),
        Block("paragraph", "same words"),
    ]

    first, second = chunk_document(blocks, "Doc")

    assert first.content == second.content
    assert first.content_hash != second.content_hash  # the path is part of the embedded text


def test_empty_sections_produce_no_chunks() -> None:
    assert chunk_document([Block("heading", "Only a title", level=1)], "Doc") == []

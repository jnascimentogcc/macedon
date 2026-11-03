import pytest

from macedon.ingestion.extract import ExtractionError
from macedon.ingestion.sandbox import extract_isolated


async def test_text_is_extracted_in_a_separate_process() -> None:
    blocks = await extract_isolated(b"First.\n\nSecond.", "txt")

    assert [b.text for b in blocks] == ["First.", "Second."]


async def test_extraction_errors_cross_the_process_boundary() -> None:
    with pytest.raises(ExtractionError, match="no text"):
        await extract_isolated(b"  \n ", "txt")


async def test_a_corrupt_file_cannot_crash_the_caller() -> None:
    with pytest.raises(ExtractionError):
        await extract_isolated(b"%PDF-1.7 broken", "pdf")


async def test_a_slow_extraction_is_killed() -> None:
    with pytest.raises(ExtractionError, match="timed out"):
        await extract_isolated(b"text", "txt", time_limit=0.001)

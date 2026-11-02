"""Upload validation. The file type comes from the bytes, never from the name or content type."""

import io
import zipfile

MAX_UNCOMPRESSED_DOCX_BYTES = 500 * 1024 * 1024  # guards against zip bombs


class UnsupportedFileError(ValueError):
    """The bytes are not a PDF, a DOCX or a UTF-8 text file."""


def detect_document_type(data: bytes) -> str:
    """Return 'pdf', 'docx' or 'txt', or raise UnsupportedFileError."""
    if not data:
        raise UnsupportedFileError("the file is empty")
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        if _is_docx(data):
            return "docx"
        raise UnsupportedFileError("only DOCX is accepted among zip-based formats")
    if _is_text(data):
        return "txt"
    raise UnsupportedFileError("unsupported file type; expected PDF, DOCX or UTF-8 text")


def _is_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_DOCX_BYTES:
                return False
            return "[Content_Types].xml" in names and "word/document.xml" in names
    except zipfile.BadZipFile:
        return False


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True

"""Run extraction, which parses untrusted files, in a separate process with limits."""

import asyncio
import json
import os
import sys

from macedon.ingestion.extract import Block, ExtractionError

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_MEMORY_BYTES = 2 * 1024**3
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


def _limit_resources() -> None:  # pragma: no cover - runs in the child, POSIX only
    if sys.platform == "win32":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))


def _child_env() -> dict[str, str]:
    """No inherited secrets (API keys, database URLs); Windows needs SYSTEMROOT to start Python."""
    return {"SYSTEMROOT": os.environ["SYSTEMROOT"]} if sys.platform == "win32" else {}


async def extract_isolated(
    data: bytes, doc_type: str, *, time_limit: float = DEFAULT_TIMEOUT_SECONDS
) -> list[Block]:
    """Extract blocks in a child interpreter. Any failure becomes an ExtractionError."""
    # -I: isolated mode, ignoring PYTHON* variables and the user site directory.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "macedon.ingestion.extract_main",
        doc_type,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_child_env(),
        preexec_fn=_limit_resources if sys.platform != "win32" else None,
    )
    try:
        async with asyncio.timeout(time_limit):
            stdout, stderr = await process.communicate(data)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ExtractionError(f"extraction timed out after {time_limit:g}s") from None

    if len(stdout) > MAX_OUTPUT_BYTES:
        raise ExtractionError("extraction produced too much output")
    try:
        result = json.loads(stdout)
    except ValueError:
        detail = stderr.decode(errors="replace")[-300:]
        raise ExtractionError(f"the extraction process failed: {detail}") from None
    if "error" in result:
        raise ExtractionError(result["error"])
    return [Block.from_json(item) for item in result["blocks"]]

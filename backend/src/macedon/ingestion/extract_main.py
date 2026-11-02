"""Entry point of the isolated extraction process: `python -I -m macedon.ingestion.extract_main`.

Reads the file from stdin and writes a JSON result to stdout. It never touches the database,
the network or the object store, and it is started with a timeout (and, where the OS allows it,
memory and CPU limits) by `macedon.ingestion.sandbox`.
"""

import json
import sys

from macedon.ingestion.extract import ExtractionError, extract_blocks


def main() -> int:
    doc_type = sys.argv[1]
    data = sys.stdin.buffer.read()
    try:
        blocks = extract_blocks(data, doc_type)
    except ExtractionError as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}))
        return 2
    sys.stdout.write(json.dumps({"blocks": [block.to_json() for block in blocks]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

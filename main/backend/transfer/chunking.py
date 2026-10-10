"""Single-file chunking and reading operations for 64 KB TCP stream.

CRITICAL RULE:
Files must be read directly from their original location.
Never copy source files into the project or duplicate disk data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator, Tuple

from backend.transfer.security import sanitize_filename

CHUNK_SIZE_64KB = 64 * 1024  # 64 KB constant chunk size


def scan_source_item(source_path: Path | str) -> Tuple[str, int]:
    """Scan a single file at source_path without copying any data.

    Returns:
        (item_name, total_bytes)
    """
    path = Path(source_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")

    if not path.is_file():
        raise ValueError(f"Path must be a regular file: {source_path}")

    item_name = sanitize_filename(path.name)
    total_bytes = path.stat().st_size
    return item_name, total_bytes


def stream_file_chunks(
    file_path: Path | str,
    chunk_size: int = CHUNK_SIZE_64KB,
) -> Generator[Tuple[int, int, bytes], None, None]:
    """Stream 64 KB chunks from file.

    Yields:
        (chunk_index, offset, chunk_bytes)
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(path, "rb") as f:
        offset = 0
        chunk_index = 0
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            yield chunk_index, offset, data
            offset += len(data)
            chunk_index += 1

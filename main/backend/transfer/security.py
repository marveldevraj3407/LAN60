"""Safe path utilities preventing directory traversal and sanitizing file paths."""

from __future__ import annotations

import os
from pathlib import Path
import re


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters, drive letters, and relative traversal tokens.

    Example:
        '../../evil.exe' -> 'evil.exe'
        'C:\\Windows\\system.ini' -> 'system.ini'
    """
    # Remove leading drive letters like C:
    filename = re.sub(r"^[a-zA-Z]:[\\/]*", "", filename)
    # Convert backslashes to forward slashes for uniform splitting
    filename = filename.replace("\\", "/")
    # Take the base file name if purely a single file
    parts = [p for p in filename.split("/") if p and p not in (".", "..")]
    if not parts:
        return "unnamed_file"
    # Filter out illegal Windows characters <>:"/\|?*
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", parts[-1])
    return cleaned or "unnamed_file"


def resolve_safe_target_path(base_dir: Path, relative_path: str) -> Path:
    """Resolve and verify that relative_path strictly stays within base_dir.

    Raises ValueError if path attempts directory traversal.
    """
    base_resolved = base_dir.resolve()

    # Normalize slashes and eliminate traversal sequences
    clean_parts: list[str] = []
    normalized = relative_path.replace("\\", "/")
    for part in normalized.split("/"):
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError(f"Directory traversal detected in path: {relative_path}")
        # Clean illegal characters in path segment
        sanitized_part = re.sub(r'[<>:"|?*\x00-\x1f]', "_", part)
        clean_parts.append(sanitized_part)

    if not clean_parts:
        target_path = base_resolved / "downloaded_file"
    else:
        target_path = base_resolved.joinpath(*clean_parts).resolve()

    # Verify boundary
    try:
        target_path.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Target path {target_path} escapes download root {base_resolved}")

    return target_path

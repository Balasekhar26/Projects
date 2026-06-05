#!/usr/bin/env python3
"""Audit ZIP archives without extracting or executing their contents.

This intentionally reads only archive metadata: names, sizes, extensions, CRCs,
and timestamps. It does not inspect source contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


RISKY_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".jar",
    ".msi",
    ".ps1",
    ".scr",
    ".sh",
    ".vbs",
}

RISKY_NAME_RE = re.compile(
    r"(^|/)(install|setup|bootstrap|postinstall|preinstall|curl|wget|token|secret|credential|key)",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_zip(path: Path, risk_limit: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "ok": False,
    }
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            files = [entry for entry in entries if not entry.is_dir()]
            dirs = [entry for entry in entries if entry.is_dir()]
            extensions = Counter(Path(entry.filename).suffix.lower() for entry in files)
            extensions.pop("", None)
            top_level = sorted({entry.filename.split("/", 1)[0] for entry in entries if entry.filename})

            risky = []
            for entry in files:
                suffix = Path(entry.filename).suffix.lower()
                if suffix in RISKY_EXTENSIONS or RISKY_NAME_RE.search(entry.filename):
                    risky.append(
                        {
                            "path": entry.filename,
                            "size_bytes": entry.file_size,
                            "compressed_bytes": entry.compress_size,
                        }
                    )
                if len(risky) >= risk_limit:
                    break

            report.update(
                {
                    "ok": True,
                    "entry_count": len(entries),
                    "file_count": len(files),
                    "directory_count": len(dirs),
                    "top_level": top_level,
                    "extensions": dict(extensions.most_common(25)),
                    "risky_metadata_matches": risky,
                }
            )
    except Exception as exc:
        report["error"] = str(exc)
    return report


def find_archives(paths: list[str]) -> list[Path]:
    archives: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            archives.extend(sorted(path.glob("*.zip")))
        elif path.is_file() and path.suffix.lower() == ".zip":
            archives.append(path)
    return archives


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ZIP archive metadata safely")
    parser.add_argument("paths", nargs="+", help="ZIP files or directories containing ZIP files")
    parser.add_argument("--risk-limit", type=int, default=80, help="maximum risky metadata matches per ZIP")
    args = parser.parse_args()

    reports = [audit_zip(path.resolve(), args.risk_limit) for path in find_archives(args.paths)]
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

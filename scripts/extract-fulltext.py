#!/usr/bin/env python3
"""Extract text from the matched full-text PDFs, one text file per record.

Usage:
    python3 scripts/extract-fulltext.py                 # all records with a PDF
    python3 scripts/extract-fulltext.py --batch 1       # one batch only
    python3 scripts/extract-fulltext.py --pdf-dir "<pdf folder>"

The PDF folder defaults to the path in .fulltext-dir (one line, git-ignored,
set once per machine), normally the Google Drive for desktop folder, e.g.
    ~/Library/CloudStorage/GoogleDrive-<you>/My Drive/GSD-III

Reads raw sources/fulltext-manifest.csv (from match-fulltext.py) and writes
    .fulltext-cache/<record key>.txt      the extracted text, page by page
    .fulltext-cache/extraction-report.csv pages, characters and a quality flag

.fulltext-cache/ is in .gitignore: the text is a copy of each paper and
must not be committed. Anyone with access to the PDFs can rebuild it with
this script.

Quality flags:
    ok          normal text layer
    low-text    little text per page; probably a scan without OCR
    no-text     no text at all; the PDF is an image scan
    error       the PDF could not be opened

Requires: pip3 install pymupdf pandas
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import pandas as pd

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        sys.exit("PyMuPDF is not installed. Run: pip3 install pymupdf --break-system-packages")

CACHE = Path(".fulltext-cache")
LOW_TEXT_CHARS_PER_PAGE = 400


def resolve_pdf_dir(given):
    if not given:
        cfg = Path(".fulltext-dir")
        if not cfg.exists():
            sys.exit("No PDF folder: pass --pdf-dir or put the folder path in .fulltext-dir")
        given = cfg.read_text().strip()
    folder = Path(given).expanduser()
    if not folder.is_dir():
        sys.exit(f"PDF folder not reachable: {folder} (is Google Drive for desktop running?)")
    return folder


def safe_name(record_key):
    return re.sub(r"[^A-Za-z0-9._-]", "_", record_key)


def extract(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages


def main():
    parser = argparse.ArgumentParser(description="Extract full text from matched PDFs.")
    parser.add_argument("--pdf-dir", help="folder holding the PDFs (default: contents of .fulltext-dir)")
    parser.add_argument("--batch", help="only this batch number")
    parser.add_argument("--force", action="store_true", help="re-extract files already in the cache")
    args = parser.parse_args()

    pdf_dir = resolve_pdf_dir(args.pdf_dir)
    manifest = pd.read_csv("raw sources/fulltext-manifest.csv", dtype=str)
    if args.batch:
        manifest = manifest[manifest["batch"] == str(args.batch)]
    CACHE.mkdir(exist_ok=True)

    report_path = CACHE / "extraction-report.csv"
    report = {}
    if report_path.exists():
        for row in csv.DictReader(report_path.open()):
            report[row["record_key"]] = row

    done = 0
    for row in manifest.to_dict("records"):
        out = CACHE / f"{safe_name(row['record_key'])}.txt"
        if out.exists() and not args.force and row["record_key"] in report:
            continue
        pdf = pdf_dir / row["pdf_filename"]
        try:
            pages = extract(pdf)
        except Exception as exc:
            report[row["record_key"]] = {"record_key": row["record_key"], "batch": row["batch"],
                                         "pdf_filename": row["pdf_filename"], "pages": 0,
                                         "chars": 0, "quality": "error", "note": str(exc)[:200]}
            print(f"  ERROR  {row['pdf_filename']}: {exc}")
            continue
        chars = sum(len(p.strip()) for p in pages)
        per_page = chars / max(len(pages), 1)
        quality = "no-text" if chars == 0 else "low-text" if per_page < LOW_TEXT_CHARS_PER_PAGE else "ok"
        with out.open("w", encoding="utf-8") as fh:
            fh.write(f"# record_key: {row['record_key']}\n# pdf: {row['pdf_filename']}\n"
                     f"# pages: {len(pages)}  quality: {quality}\n\n")
            for i, text in enumerate(pages, start=1):
                fh.write(f"\n===== page {i} =====\n{text}")
        report[row["record_key"]] = {"record_key": row["record_key"], "batch": row["batch"],
                                     "pdf_filename": row["pdf_filename"], "pages": len(pages),
                                     "chars": chars, "quality": quality, "note": ""}
        done += 1
        if done % 25 == 0:
            print(f"  extracted {done} ...")

    fields = ["record_key", "batch", "pdf_filename", "pages", "chars", "quality", "note"]
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for key in sorted(report):
            writer.writerow(report[key])

    counts = pd.Series([r["quality"] for r in report.values()]).value_counts().to_dict()
    print(f"Extracted this run: {done}.  Totals by quality: {counts}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()

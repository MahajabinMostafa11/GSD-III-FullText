#!/usr/bin/env python3
"""Read a batch file one record at a time.

List the records in a batch:
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --list

Show one record in full (every field), by its position in the list or by key:
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --index 7
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --key pmid:13627929

The full view prints every column of the record. It also pulls every abstract
version found inside Raw Data (JSON) to the top, labelled by source and
length, so the fullest abstract is easy to find. Last, it prints the paper's
extracted full text from .fulltext-cache/ with its quality flag, or says why
there is none.

Requires: pip3 install pandas
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd


def load(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def text_of(value):
    if isinstance(value, list):
        return " ".join(text_of(v) for v in value)
    if isinstance(value, dict):
        return text_of(value.get("content") or value.get("p") or "")
    return str(value or "").strip()


def abstract_versions(row):
    versions = []
    if row.get("Abstract", "").strip():
        versions.append(("Abstract column", row["Abstract"].strip()))
    raw = row.get("Raw Data (JSON)", "").strip()
    if not raw:
        return versions
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return versions
    gs = data.get("google_scholar") or {}
    for label, value in [
        ("Google Scholar full_abstract", gs.get("full_abstract")),
        ("Google Scholar parsed abstract", (gs.get("parsed") or {}).get("abstract")),
        ("Google Scholar snippet", gs.get("abstract_snippet")),
    ]:
        if text_of(value):
            versions.append((label, text_of(value)))
    wos = (((data.get("web_of_science") or {}).get("wos_json") or {})
           .get("static_data", {}).get("fullrecord_metadata", {}).get("abstracts", {}))
    wos_abs = ((wos.get("abstract") or {}).get("abstract_text") or {}).get("p")
    if text_of(wos_abs):
        versions.append(("Web of Science abstract", text_of(wos_abs)))
    pm = data.get("pubmed") or {}
    for key in ("abstract", "Abstract"):
        if text_of(pm.get(key)):
            versions.append(("PubMed abstract", text_of(pm.get(key))))
    return versions


def show(row):
    print(f"=== {row['record_key']}  (batch {row['batch']}) ===\n")
    print("--- Abstract versions found (fullest first) ---")
    versions = sorted(abstract_versions(row), key=lambda v: -len(v[1]))
    if not versions:
        print("(no abstract in any field)")
    seen = set()
    for label, text in versions:
        if text in seen:
            print(f"[{label}] identical to a version above")
            continue
        seen.add(text)
        print(f"[{label}] ({len(text)} chars)\n{text}\n")
    print("--- All fields ---")
    for col, value in row.items():
        if col in ("Raw Data (JSON)", "Claude Enrichment (JSON)"):
            continue
        print(f"{col}: {value}")
    print("\n--- Claude Enrichment (JSON) — LLM-generated metadata, NOT evidence ---")
    print(pretty(row.get("Claude Enrichment (JSON)", "")))
    print("\n--- Raw Data (JSON) ---")
    print(pretty(row.get("Raw Data (JSON)", "")))
    show_fulltext(row["record_key"])


def show_fulltext(key):
    print("\n--- Full text ---")
    manifest = Path("raw sources/fulltext-manifest.csv")
    entry = None
    if manifest.exists():
        for m in csv.DictReader(manifest.open(encoding="utf-8")):
            if m["record_key"] == key:
                entry = m
                break
    if entry is None:
        print("No full text for this record: write an abstract (or metadata-only) page.")
        return
    quality = "unknown"
    report = Path(".fulltext-cache/extraction-report.csv")
    if report.exists():
        for m in csv.DictReader(report.open(encoding="utf-8")):
            if m["record_key"] == key:
                quality = m["quality"]
    print(f"PDF: {entry['pdf_filename']}   pointer: gdrive:{entry['drive_path']}   quality: {quality}")
    text_file = Path(".fulltext-cache") / (re.sub(r"[^A-Za-z0-9._-]", "_", key) + ".txt")
    if not text_file.exists():
        print("Full text not extracted yet. Run: python3 scripts/extract-fulltext.py --batch <N>")
        return
    if quality in ("no-text", "error"):
        print("The PDF has no readable text: write an abstract page tagged status/fulltext-unreadable.")
        return
    print(text_file.read_text(encoding="utf-8"))


def pretty(raw):
    raw = (raw or "").strip()
    if not raw:
        return "(empty)"
    try:
        return json.dumps(json.loads(raw), indent=1, ensure_ascii=False)
    except json.JSONDecodeError:
        return raw


def main():
    parser = argparse.ArgumentParser(description="Read a batch file one record at a time.")
    parser.add_argument("batch_file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--index", type=int, help="1-based position, as shown by --list")
    group.add_argument("--key", help="record_key, e.g. pmid:13627929")
    args = parser.parse_args()

    df = load(args.batch_file)
    if args.list:
        for i, row in enumerate(df.to_dict("records"), start=1):
            has_abs = "abstract" if abstract_versions(row) else "NO ABSTRACT"
            author = row.get("Authors", "").split(";")[0].strip()
            print(f"{i:4d}  {row['record_key']:<30} {row.get('Publication Year', ''):>6}  "
                  f"{author[:25]:<25}  {has_abs:<11}  {row.get('Title', '')[:80]}")
        print(f"\n{len(df)} records")
        return
    if args.key:
        match = df[df["record_key"] == args.key]
        if match.empty:
            sys.exit(f"No record with key {args.key} in this batch")
        show(match.iloc[0].to_dict())
        return
    if not 1 <= args.index <= len(df):
        sys.exit(f"Index out of range: this batch has {len(df)} records")
    show(df.iloc[args.index - 1].to_dict())


if __name__ == "__main__":
    main()

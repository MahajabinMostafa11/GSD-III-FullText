#!/usr/bin/env python3
"""Flag likely duplicate records and shared abstracts before a batch starts.

Compares every record in batch N against every record in the corpus (all
batches), so problems are caught even when the other record was ingested in
an earlier batch or comes in a later one.

Usage:
    python3 scripts/precheck-batch.py 3

Writes .batch-work/flags.csv (git-ignored), read by scripts/show-record.py:
    record_key, flag, other_key, other_batch, detail

Flags:
    same-id          same DOI or PubMed ID as another record
    similar-title    near-identical title, publication years within one year
    shared-abstract  the same abstract text appears under a different title
                     (a scraping error: one of the two abstracts is not its own)

Requires: pip3 install pandas
"""

import csv
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


def norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit(__doc__)
    batch = sys.argv[1]
    batch_dir = Path("raw sources/batches")
    parts = []
    for f in sorted(batch_dir.glob("batch-*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        parts.append(df)
    corpus = pd.concat(parts, ignore_index=True)
    corpus["t"] = corpus["Title"].map(norm)
    corpus["a"] = corpus["Abstract"].map(norm)
    corpus["doi_n"] = corpus["DOI"].map(norm)
    corpus["pmid_n"] = corpus["PubMed ID"].str.replace(r"\.0$", "", regex=True).str.strip()
    corpus["year"] = pd.to_numeric(corpus["Publication Year"], errors="coerce")

    rows = corpus.to_dict("records")
    mine = [r for r in rows if str(r["batch"]) == batch]
    if not mine:
        sys.exit(f"No records in batch {batch}")

    flags = []

    def add(r, other, flag, detail):
        flags.append({"record_key": r["record_key"], "flag": flag, "other_key": other["record_key"],
                      "other_batch": other["batch"], "detail": detail})

    for r in mine:
        for o in rows:
            if o["record_key"] == r["record_key"]:
                continue
            same_doi = r["doi_n"] and r["doi_n"] == o["doi_n"]
            same_pmid = r["pmid_n"] and r["pmid_n"] == o["pmid_n"]
            if same_doi or same_pmid:
                add(r, o, "same-id", f"same {'DOI' if same_doi else 'PubMed ID'}; other title: {o['Title'][:120]}")
                continue
            close_year = (pd.isna(r["year"]) or pd.isna(o["year"]) or abs(r["year"] - o["year"]) <= 1)
            if r["t"] and o["t"] and close_year:
                if r["t"] == o["t"] or (min(len(r["t"]), len(o["t"])) > 25 and
                                        SequenceMatcher(None, r["t"], o["t"]).ratio() >= 0.9):
                    add(r, o, "similar-title", f"other title: {o['Title'][:120]} ({o['Publication Year']})")
                    continue
            if len(r["a"]) >= 200 and len(o["a"]) >= 200 and r["a"][:200] == o["a"][:200] \
                    and SequenceMatcher(None, r["t"], o["t"]).ratio() < 0.9:
                add(r, o, "shared-abstract", f"same abstract text as: {o['Title'][:120]} ({o['Publication Year']})")

    out_dir = Path(".batch-work")
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "flags.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["record_key", "flag", "other_key", "other_batch", "detail"])
        writer.writeheader()
        writer.writerows(flags)
    counts = pd.Series([f["flag"] for f in flags]).value_counts().to_dict() if flags else {}
    print(f"Batch {batch}: {len(mine)} records checked against {len(rows)}; "
          f"flags: {counts or 'none'}; written to .batch-work/flags.csv")


if __name__ == "__main__":
    main()

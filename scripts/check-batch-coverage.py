#!/usr/bin/env python3
"""Check that every record in a batch has exactly one source-summary page.

Reads `record_key:` and `ingestion_depth:` from the frontmatter of every page
in the wiki and compares them with the batch file. Records whose full text is
readable (quality ok) must have a `full-text` page.

Usage:
    python3 scripts/check-batch-coverage.py "raw sources/batches/batch-1.csv" wiki/GSD-III-FullText.wiki

Exit code 0 only when every record has exactly one page.

Requires: pip3 install pandas
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

KEY_LINE = re.compile(r'^record_key:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
DEPTH_LINE = re.compile(r'^ingestion_depth:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)


def readable_fulltext():
    report = Path(".fulltext-cache/extraction-report.csv")
    if not report.exists():
        return None
    df = pd.read_csv(report, dtype=str, keep_default_na=False)
    return set(df[df["quality"] == "ok"]["record_key"])


def page_keys(wiki_dir):
    keys = defaultdict(list)
    for page in Path(wiki_dir).glob("*.md"):
        text = page.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        frontmatter = text.split("---", 2)[1] if text.count("---") >= 2 else ""
        depth = DEPTH_LINE.findall(frontmatter)
        for key in KEY_LINE.findall(frontmatter):
            keys[key.strip()].append((page.name, depth[0].strip() if depth else ""))
    return keys


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    batch = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
    keys = page_keys(sys.argv[2])

    readable = readable_fulltext()
    missing, doubled, wrong_depth = [], [], []
    for row in batch.to_dict("records"):
        pages = keys.get(row["record_key"], [])
        if not pages:
            missing.append(row)
        elif len(pages) > 1:
            doubled.append((row, [p for p, _ in pages]))
        elif readable is not None and row["record_key"] in readable and pages[0][1] != "full-text":
            wrong_depth.append((row, pages[0]))

    print(f"Batch: {sys.argv[1]}")
    print(f"Records: {len(batch)}   with a page: {len(batch) - len(missing)}   "
          f"missing: {len(missing)}   more than one page: {len(doubled)}   "
          f"full text available but page not full-text: {len(wrong_depth)}")
    if readable is None:
        print("  NOTE  no .fulltext-cache/extraction-report.csv: depth not checked "
              "(run scripts/extract-fulltext.py)")
    for row in missing:
        print(f"  MISSING  {row['record_key']}  {row.get('Publication Year', '')}  {row.get('Title', '')[:80]}")
    for row, pages in doubled:
        print(f"  DOUBLED  {row['record_key']}  -> {', '.join(pages)}")
    for row, (page, depth) in wrong_depth:
        print(f"  DEPTH    {row['record_key']}  {page} is '{depth}', full text is readable")
    sys.exit(0 if not missing and not doubled and not wrong_depth else 1)


if __name__ == "__main__":
    main()

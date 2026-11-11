#!/usr/bin/env python3
"""List concept and treatment pages by number of claims and size.

Usage:
    python3 scripts/claim-counts.py wiki/<repo>.wiki [--over 25]

Pages over the limit (default 25 claims) are marked SPLIT: the schema's Page
splitting rule applies to them at the end of the batch.
"""

import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
parser.add_argument("wiki_dir")
parser.add_argument("--over", type=int, default=25)
args = parser.parse_args()

rows = []
for path in Path(args.wiki_dir).glob("*.md"):
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^type:\s*(concept|treatment)\s*$", text, re.M):
        continue
    claims = len(re.findall(r"^\*\*C\d+\.", text, re.M))
    rows.append((claims, len(text), path.stem))
rows.sort(reverse=True)
over = [r for r in rows if r[0] > args.over]
for claims, size, name in rows:
    mark = "  SPLIT" if claims > args.over else ""
    print(f"{claims:4d} claims  {size:7d} chars  {name}{mark}")
print(f"\n{len(over)} page(s) over {args.over} claims.")

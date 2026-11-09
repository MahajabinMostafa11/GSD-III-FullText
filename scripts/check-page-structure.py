#!/usr/bin/env python3
"""Check that every source-summary page has the required structure.

Checks, for each page with `type: source-summary`:
  - the 11 section headings from CLAUDE.md, exactly, in order, none merged,
    none missing, no extra `##` sections;
  - the required frontmatter fields from the schema.

Usage:
    python3 scripts/check-page-structure.py wiki/<repo>.wiki
    python3 scripts/check-page-structure.py wiki/<repo>.wiki --pages A.md B.md

Exit code 0 only when every page passes.
"""

import argparse
import re
import sys
from pathlib import Path

SECTIONS = [
    "Citation",
    "Study type and design",
    "Population or sample",
    "Key findings",
    "Methods detail",
    "Authors' conclusions",
    "Limitations and caveats",
    "Connections",
    "Ontology terms",
    "Source link",
    "Record metadata",
]
REQUIRED_FIELDS = ["type", "title", "description", "up", "tags", "evidence", "lifecycle",
                   "sources", "updated", "record_key", "source", "ingestion_depth",
                   "study_design", "subject", "subtype_scope"]
FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def check(path):
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    if not m:
        return None, []
    front, body = m.groups()
    if not re.search(r"^type:\s*source-summary\s*$", front, re.M):
        return None, []
    problems = []
    for field in REQUIRED_FIELDS:
        if not re.search(rf"^{field}:\s*\S", front, re.M):
            problems.append(f"missing frontmatter field `{field}`")
    headings = [h.strip() for h in re.findall(r"^## (.+)$", body, re.M)]
    if headings != SECTIONS:
        missing = [s for s in SECTIONS if s not in headings]
        extra = [h for h in headings if h not in SECTIONS]
        if missing:
            problems.append("missing sections: " + "; ".join(missing))
        if extra:
            problems.append("sections not in the layout: " + "; ".join(extra))
        if not missing and not extra:
            problems.append("sections out of order")
    return True, problems


def main():
    parser = argparse.ArgumentParser(description="Check source-summary page structure.")
    parser.add_argument("wiki_dir")
    parser.add_argument("--pages", nargs="+", help="only these page files")
    args = parser.parse_args()

    wiki = Path(args.wiki_dir)
    files = [wiki / p for p in args.pages] if args.pages else sorted(wiki.glob("*.md"))
    checked, failed = 0, 0
    for path in files:
        is_source, problems = check(path)
        if is_source is None and not problems:
            continue
        checked += 1
        if problems:
            failed += 1
            print(f"  FAIL  {path.name}")
            for p in problems:
                print(f"        - {p}")
    print(f"Source-summary pages checked: {checked}   failing: {failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

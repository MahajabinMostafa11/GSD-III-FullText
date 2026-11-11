#!/usr/bin/env python3
"""List the wiki pages a new paper most likely connects to.

Used by the per-paper helper so it reads the right pages instead of the whole
wiki. Prints, for one record:
  1. every concept, treatment, entity and synthesis page, with its one-line
     description and its number of claims (these pages are few, so all of them
     are listed);
  2. the source-summary pages already in the wiki that are most similar to
     this record (title, keywords, MeSH terms and abstract against each page's
     title, description and tags), most similar first.

Usage:
    python3 scripts/related-pages.py "raw sources/batches/batch-3.csv" --key pmid:10982190 [--top 10]
"""

import argparse
import importlib.util
import math
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
STOP = set("""a an the of and or in on at to for with by from as is are was were be been this that these
those it its into than then there their which who whom whose not no but also may can using use used
study studies case cases patient patients report reports type types disease diseases glycogen storage
gsd iii ii i iv v vi vii ix et al new two one three""".split())


def words(text):
    return [w for w in re.findall(r"[a-z][a-z0-9]{2,}", str(text).lower()) if w not in STOP]


def field(front, name):
    m = re.search(rf"^{name}:\s*(.*)$", front, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def load_show_record():
    spec = importlib.util.spec_from_file_location("show_record", Path(__file__).with_name("show-record.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("batch_file")
    parser.add_argument("--key", required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--wiki", help="wiki folder (default: the only wiki/*.wiki folder)")
    args = parser.parse_args()

    wiki = Path(args.wiki) if args.wiki else next(iter(sorted(Path("wiki").glob("*.wiki"))), None)
    if wiki is None or not wiki.is_dir():
        sys.exit("Wiki folder not found; pass --wiki")
    df = pd.read_csv(args.batch_file, dtype=str, keep_default_na=False)
    match = df[df["record_key"] == args.key]
    if match.empty:
        sys.exit(f"No record {args.key} in {args.batch_file}")
    row = match.iloc[0].to_dict()
    sr = load_show_record()
    extra = " ".join(v for k, v in sr.raw_extract(row) if "MeSH" in k or "keywords" in k.lower())
    query = Counter(words(" ".join([row["Title"], row["Title"], row.get("Keywords", ""), extra,
                                    row.get("Abstract", "")])))

    topic, sources = [], []
    for path in sorted(wiki.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = FM.match(text)
        if not m:
            continue
        front = m.group(1)
        ptype = field(front, "type")
        if ptype in ("concept", "treatment", "entity", "synthesis"):
            claims = len(re.findall(r"^\*\*C\d+\.", text, re.M))
            topic.append((ptype, path.stem, field(front, "title"), field(front, "description"), claims))
        elif ptype == "source-summary" and field(front, "record_key") != args.key:
            doc = " ".join([field(front, "title"), field(front, "description"), field(front, "tags")])
            sources.append((path.stem, field(front, "title"), Counter(words(doc))))

    n = len(sources) or 1
    df_count = Counter()
    for _, _, c in sources:
        df_count.update(set(c))

    def score(c):
        s = 0.0
        for w, q in query.items():
            if w in c:
                s += q * c[w] * math.log((n + 1) / (df_count[w] + 1)) ** 2
        return s / math.sqrt(sum(c.values()) + 1)

    ranked = sorted(((score(c), stem, title) for stem, title, c in sources), reverse=True)
    ranked = [r for r in ranked if r[0] > 0][: args.top]

    print(f"=== Related pages for {args.key} ===\n")
    print("--- Concept, treatment, entity and synthesis pages (all) ---")
    for ptype, stem, title, desc, claims in sorted(topic, key=lambda t: (t[0], t[2].lower())):
        c = f", {claims} claims" if claims else ""
        print(f"[{ptype}{c}] {stem}: {title} — {desc}")
    print(f"\n--- Most similar source-summary pages already in the wiki (top {args.top}) ---")
    if not ranked:
        print("None found.")
    for s, stem, title in ranked:
        print(f"{stem}: {title}")


if __name__ == "__main__":
    main()

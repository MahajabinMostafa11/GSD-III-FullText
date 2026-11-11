#!/usr/bin/env python3
"""Read a batch file one record at a time.

List the records in a batch:
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --list

Show one record in full (every field), by its position in the list or by key:
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --index 7
    python3 scripts/show-record.py "raw sources/batches/batch-1.csv" --key pmid:13627929

The full view prints, in order:
  - every abstract version found (Abstract column and inside Raw Data),
    fullest first;
  - every CSV column except the two JSON columns;
  - the useful contents of Raw Data (JSON) as labelled lines: MeSH terms,
    affiliations, full author names, language, substances, grants, conflicts
    of interest, dates, Web of Science keywords, categories, addresses and
    funding, Google Scholar links. Only JSON structure, internal IDs and
    values already shown from their own column are left out;
  - the Claude Enrichment notes (LLM-generated, not evidence);
  - flags from the batch's pre-check (likely duplicates, shared abstracts);
  - the paper's full text, in repos that have full text.
Add --raw to print the complete Raw Data JSON as well.

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


def joined(value, sep="; "):
    if value is None:
        return ""
    if isinstance(value, list):
        return sep.join(joined(v, sep) for v in value if joined(v, sep))
    if isinstance(value, dict):
        for key in ("content", "full_address", "display_name", "full_name", "keyword", "subject"):
            if key in value:
                return joined(value[key], sep)
        return ""
    return str(value).strip()


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def raw_extract(row):
    """Useful Raw Data fields as (label, text) pairs, without JSON structure."""
    raw = row.get("Raw Data (JSON)", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [("Raw Data", "(not valid JSON; use --raw)")]
    out = []
    pm = (data.get("pubmed") or {}).get("medline") or {}
    for code, label in [("MH", "PubMed MeSH terms"), ("OT", "PubMed author keywords"),
                        ("LA", "PubMed language"), ("FAU", "PubMed full author names"),
                        ("AD", "PubMed affiliations"), ("RN", "PubMed substances"),
                        ("GR", "PubMed grants"), ("COIS", "PubMed conflict of interest"),
                        ("DP", "PubMed publication date"), ("DEP", "PubMed electronic publication"),
                        ("VI", "PubMed volume"), ("IP", "PubMed issue"), ("PG", "PubMed pages"),
                        ("PL", "PubMed place of publication"), ("PST", "PubMed publication status"),
                        ("CI", "PubMed copyright"), ("TT", "PubMed original-language title"),
                        ("CON", "PubMed comment on"), ("CIN", "PubMed comment in"),
                        ("EIN", "PubMed erratum in"), ("RIN", "PubMed retraction in")]:
        value = joined(pm.get(code))
        if value and value.lower() != "none":
            out.append((label, value))
    wos = (data.get("web_of_science") or {}).get("wos_json") or {}
    static = wos.get("static_data") or {}
    fm = static.get("fullrecord_metadata") or {}
    item = static.get("item") or {}
    summary = static.get("summary") or {}
    kw = joined((fm.get("keywords") or {}).get("keyword"))
    if kw:
        out.append(("WoS author keywords", kw))
    kwp = joined((item.get("keywords_plus") or {}).get("keyword"))
    if kwp:
        out.append(("WoS Keywords Plus", kwp))
    cat = fm.get("category_info") or {}
    subjects = [s.get("content") for s in as_list((cat.get("subjects") or {}).get("subject"))
                if isinstance(s, dict) and s.get("ascatype") == "traditional"]
    if subjects:
        out.append(("WoS subject categories", "; ".join(subjects)))
    headings = joined((cat.get("headings") or {}).get("heading"))
    if headings:
        out.append(("WoS research area heading", headings))
    addresses = []
    for a in as_list((fm.get("addresses") or {}).get("address_name")):
        spec = a.get("address_spec") or {} if isinstance(a, dict) else {}
        if spec.get("full_address"):
            addresses.append(spec["full_address"])
    if addresses:
        out.append(("WoS addresses", " | ".join(dict.fromkeys(addresses))))
    countries = []
    for a in as_list((fm.get("addresses") or {}).get("address_name")):
        spec = a.get("address_spec") or {} if isinstance(a, dict) else {}
        if spec.get("country"):
            countries.append(spec["country"])
    if countries:
        out.append(("WoS countries", "; ".join(dict.fromkeys(countries))))
    fund = fm.get("fund_ack") or {}
    fund_text = joined(((fund.get("fund_text") or {}).get("p")))
    if fund_text:
        out.append(("WoS funding text", fund_text))
    langs = joined((fm.get("languages") or {}).get("language"))
    if langs:
        out.append(("WoS language", langs))
    refs = (fm.get("refs") or {}).get("count")
    if refs:
        out.append(("WoS cited reference count", str(refs)))
    pub = (summary.get("pub_info") or {})
    if pub:
        bits = [f"{k}={pub.get(k)}" for k in ("pubyear", "pubmonth", "vol", "issue", "pubtype") if pub.get(k)]
        page = pub.get("page") or {}
        if isinstance(page, dict) and page.get("content"):
            bits.append(f"pages={page['content']}")
        if bits:
            out.append(("WoS publication info", ", ".join(bits)))
    publisher = joined((((summary.get("publishers") or {}).get("publisher") or {})
                        .get("names") or {}).get("name"))
    if publisher:
        out.append(("WoS publisher", publisher))
    gs = data.get("google_scholar") or {}
    for key, label in [("paper_url", "Google Scholar link"), ("source", "Google Scholar source"),
                       ("main_abstract_source", "Google Scholar abstract source"),
                       ("has_full_abstract", "Google Scholar has full abstract")]:
        value = joined(gs.get(key))
        if value:
            out.append((label, value))
    return out


def norm_value(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def show_flags(key):
    flags = Path(".batch-work/flags.csv")
    if not flags.exists():
        return
    found = [f for f in csv.DictReader(flags.open(encoding="utf-8")) if f["record_key"] == key]
    print("\n--- Pre-check flags ---")
    if not found:
        print("None.")
    for f in found:
        print(f"[{f['flag']}] with {f['other_key']} (batch {f['other_batch']}): {f['detail']}")


def show(row, raw=False):
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
        if col == "Abstract" and str(value).strip():
            value = "(shown above as [Abstract column])"
        print(f"{col}: {value if str(value).strip() else '(empty)'}")
    print("\n--- From Raw Data (JSON) ---")
    shown = {norm_value(v) for k, v in row.items() if k not in ("Raw Data (JSON)",)}
    extracted = [(label, value) for label, value in raw_extract(row)
                 if norm_value(value) not in shown]
    if not extracted:
        print("(empty)")
    for label, value in extracted:
        print(f"{label}: {value}")
    print("\n--- Claude Enrichment (JSON) — LLM-generated metadata, NOT evidence ---")
    print(compact_json(row.get("Claude Enrichment (JSON)", "")))
    show_flags(row["record_key"])
    if raw:
        print("\n--- Raw Data (JSON), complete ---")
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
    cfg = Path(".fulltext-dir")
    if cfg.exists():
        print(f"Original PDF on this machine: {Path(cfg.read_text().strip()).expanduser() / entry['pdf_filename']}")
    text_file = Path(".fulltext-cache") / (re.sub(r"[^A-Za-z0-9._-]", "_", key) + ".txt")
    if not text_file.exists():
        print("Full text not extracted yet. Run: python3 scripts/extract-fulltext.py --batch <N>")
        return
    if quality in ("no-text", "low-text", "error"):
        print("The PDF has no readable text: write an abstract page tagged status/fulltext-unreadable.")
        return
    if quality == "non-english":
        print("The paper is not in English: its full text is not used. Write an abstract page "
              "tagged status/fulltext-non-english.")
        return
    print(text_file.read_text(encoding="utf-8"))


def compact_json(raw):
    raw = (raw or "").strip()
    if not raw:
        return "(empty)"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict):
        return "\n".join(f"{k}: {joined(v) if not isinstance(v, (dict, list)) or joined(v) else json.dumps(v, ensure_ascii=False)}"
                         for k, v in data.items())
    return json.dumps(data, ensure_ascii=False)


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
    parser.add_argument("--raw", action="store_true", help="also print the complete Raw Data JSON")
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
        show(match.iloc[0].to_dict(), args.raw)
        return
    if not 1 <= args.index <= len(df):
        sys.exit(f"Index out of range: this batch has {len(df)} records")
    show(df.iloc[args.index - 1].to_dict(), args.raw)


if __name__ == "__main__":
    main()

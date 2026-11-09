#!/usr/bin/env python3
"""Match full-text PDFs to corpus records and write the full-text manifest.

PDF filenames are <year>_<Surname>_<id>.pdf, where <id> is one of:
    pmid<PubMed ID>             1959_DiSantAgnese_pmid13627929.pdf
    gs<Google Scholar ID>       2006_MVorgerd_gs2hqRGsJubX8J.pdf
    gs<start of the title>      1962_Hug_gsglucagontoleranc.pdf
    <DOI with . and / as ->     2007_Chen_10-1016-j-jhep-2007-05-008.pdf

Matching order, first that succeeds:
    1. manual override         raw sources/fulltext-overrides.csv (pdf_filename,record_key)
    2. PubMed ID
    3. DOI                     the DOI column, BibTeX or Raw Data
    4. Google Scholar ID       the Google Scholar ID column, BibTeX or Raw Data
    5. year + title start      (+ surname when several titles start alike)
    6. year + surname          only when exactly one record fits   [check]
    7. surname, undated record only when exactly one fits          [check]
    8. a record's title found in the PDF's first two pages         [check]
       (needs PyMuPDF; covers filenames whose author or ID is not in the corpus)

Matches from 6-8 are marked "check": open the PDF and confirm.
If one PDF fits several records (e.g. the same paper indexed twice), it is
linked to all of them. If several PDFs fit one record, the best-matched PDF
is used and the others are listed as duplicates.

Usage:
    python3 scripts/match-fulltext.py "raw sources/batches/manifest.csv" ["<pdf folder>"]

The PDF folder defaults to the path in .fulltext-dir (one line, git-ignored).

Writes raw sources/fulltext-manifest.csv:
    record_key, batch, pdf_filename, drive_path, match_method
PDFs of papers that are not in the corpus are listed, with a reason, in
raw sources/fulltext-excluded.csv (pdf_filename,reason); they are reported as
EXCLUDED, not as failures.

Exit code 0 when every PDF is matched or excluded (duplicates and "check" are
reported, not counted as failures).

Requires: pip3 install pandas
"""

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

NAME = re.compile(r"^(?P<year>\d{4})_(?P<surname>[^_]+)_(?P<ident>.+)$")
DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"'}<>,]+", re.I)
RANK = {"override": 0, "pmid": 1, "doi": 2, "gs-id": 3, "year+title": 4,
        "year+title (shared)": 5, "year+surname [check]": 6, "surname, undated [check]": 7,
        "title in PDF [check]": 8}


def ascii_fold(text):
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()


def norm(text):
    return re.sub(r"[^a-z0-9]", "", ascii_fold(text).lower())


def norm_dropped(text):
    """Letters with accents removed entirely (how some filenames were made)."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def surname_forms(first_author):
    first_author = str(first_author or "")
    raw = first_author.split(",")[0] if "," in first_author else (first_author.split() or [""])[-1]
    return {f for f in (norm(raw), norm_dropped(raw)) if f}


def surname_fits(file_surname, forms):
    a = {norm(file_surname), norm_dropped(file_surname)}
    return any(x and y and (x.startswith(y) or y.startswith(x)
                            or (len(y) >= 4 and x.endswith(y)))
               for x in a for y in forms)


def first_pages_text(pdf_path):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            return ""
    try:
        doc = pymupdf.open(pdf_path)
        text = " ".join(doc[i].get_text("text") for i in range(min(2, len(doc))))
        doc.close()
        return norm(text)
    except Exception:
        return ""


def load_records(manifest_path):
    batch_dir = manifest_path.parent
    parts = [pd.read_csv(f, dtype=str, keep_default_na=False) for f in sorted(batch_dir.glob("batch-*.csv"))]
    if not parts:
        sys.exit(f"No batch files in {batch_dir}")
    df = pd.concat(parts, ignore_index=True)
    df["year"] = df["Publication Year"].str.replace(r"\.0$", "", regex=True)
    df["title_norm"] = df["Title"].map(norm)
    df["surnames"] = df["Authors"].map(lambda a: surname_forms(str(a).split(";")[0]))
    df["pmid"] = df["PubMed ID"].str.replace(r"\.0$", "", regex=True).str.strip()

    def dois(row):
        found = {norm(row["DOI"])} if row["DOI"].strip() else set()
        for m in DOI_IN_TEXT.findall(row.get("Google Scholar BibTeX", "") + " " + row.get("Raw Data (JSON)", "")):
            found.add(norm(m))
        return found

    def gs_ids(row):
        ids = {row["Google Scholar ID"].strip()} if row["Google Scholar ID"].strip() else set()
        return ids

    df["dois"] = df.apply(dois, axis=1)
    df["gs_ids"] = df.apply(gs_ids, axis=1)
    df["blob"] = df["Google Scholar BibTeX"] + " " + df["Raw Data (JSON)"]
    return df


def match_one(pdf_stem, records, overrides, pdf_path=None):
    if pdf_stem + ".pdf" in overrides:
        return [overrides[pdf_stem + ".pdf"]], "override", None
    m = NAME.match(pdf_stem)
    if not m:
        return [], None, "filename does not follow <year>_<Surname>_<id>"
    year, surname, ident = m["year"], m["surname"], m["ident"]

    def keys(hit):
        return list(hit["record_key"])

    if re.fullmatch(r"pmid\d+", ident):
        hit = records[records["pmid"] == ident[4:]]
        if len(hit) >= 1:
            return keys(hit), "pmid", None
    elif ident.startswith("10-"):
        target = norm(ident)
        hit = records[records["dois"].map(lambda ds: any(d.startswith(target) or target.startswith(d)
                                                         for d in ds if len(d) > 6))]
        if len(hit) >= 1:
            return keys(hit), "doi", None
    elif ident.startswith("gs"):
        gid = ident[2:]
        hit = records[records["gs_ids"].map(lambda ids: gid in ids)]
        if hit.empty and len(gid) >= 10:
            hit = records[records["blob"].str.contains(re.escape(gid), regex=True)]
        if len(hit) >= 1:
            return keys(hit), "gs-id", None
        start = norm(gid)
        if start:
            hit = records[(records["year"] == year) & records["title_norm"].str.startswith(start)]
            if len(hit) > 1:
                narrowed = hit[hit["surnames"].map(lambda f: surname_fits(surname, f))]
                hit = narrowed if not narrowed.empty else hit
            if len(hit) == 1:
                return keys(hit), "year+title", None
            if len(hit) > 1:
                return keys(hit), "year+title (shared)", None

    hit = records[(records["year"] == year) & records["surnames"].map(lambda f: surname_fits(surname, f))]
    if len(hit) == 1:
        return keys(hit), "year+surname [check]", None
    undated = records[(records["year"] == "") & records["surnames"].map(lambda f: surname_fits(surname, f))]
    if len(undated) == 1:
        return keys(undated), "surname, undated [check]", None
    if pdf_path is not None:
        text = first_pages_text(pdf_path)
        if text:
            # Only distinctive titles: short generic ones ("Glycogen storage
            # disease type III") appear inside many papers.
            near = records[records["title_norm"].str.len() >= 40]
            found = near[near["title_norm"].map(lambda t: t[:80] in text)]
            if len(found) >= 1 and found["title_norm"].str[:80].nunique() == 1:
                return keys(found), "title in PDF [check]", None
    if len(hit) > 1:
        return [], None, "several records by this author that year: " + ", ".join(hit["record_key"])
    return [], None, "no matching record (open the PDF and add an override)"


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    manifest_path = Path(sys.argv[1])
    if len(sys.argv) == 3:
        pdf_dir = Path(sys.argv[2]).expanduser()
    elif Path(".fulltext-dir").exists():
        pdf_dir = Path(Path(".fulltext-dir").read_text().strip()).expanduser()
    else:
        sys.exit("No PDF folder: pass it as the second argument or put it in .fulltext-dir")
    if not pdf_dir.is_dir():
        sys.exit(f"PDF folder not reachable: {pdf_dir}")

    records = load_records(manifest_path)
    batch_of = dict(zip(records["record_key"], records["batch"]))

    overrides = {}
    override_path = manifest_path.parent.parent / "fulltext-overrides.csv"
    if override_path.exists():
        for row in pd.read_csv(override_path, dtype=str).to_dict("records"):
            overrides[row["pdf_filename"].strip()] = row["record_key"].strip()

    excluded = {}
    excluded_path = manifest_path.parent.parent / "fulltext-excluded.csv"
    if excluded_path.exists():
        for row in pd.read_csv(excluded_path, dtype=str).to_dict("records"):
            excluded[row["pdf_filename"].strip()] = row["reason"].strip()

    candidates, problems = [], []
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    for pdf in pdfs:
        if pdf.name in excluded:
            continue
        found, method, why = match_one(pdf.stem, records, overrides, pdf)
        found = [k for k in found if k in batch_of]
        if not found:
            problems.append((pdf.name, why or "override names an unknown record_key"))
            continue
        for key in found:
            candidates.append({"record_key": key, "batch": batch_of[key], "pdf_filename": pdf.name,
                               "drive_path": f"{pdf_dir.name}/{pdf.name}", "match_method": method})

    cand = pd.DataFrame(candidates, columns=["record_key", "batch", "pdf_filename", "drive_path", "match_method"])
    cand["rank"] = cand["match_method"].map(RANK)
    cand = cand.sort_values(["record_key", "rank", "pdf_filename"])
    kept = cand.drop_duplicates("record_key", keep="first")
    extra = cand[~cand.index.isin(kept.index)]
    kept.drop(columns="rank").sort_values(["batch", "record_key"]).to_csv(
        manifest_path.parent.parent / "fulltext-manifest.csv", index=False)

    matched_pdfs = cand["pdf_filename"].nunique()
    print(f"PDFs found: {len(pdfs)}   matched: {matched_pdfs}   excluded: "
          f"{sum(1 for p in pdfs if p.name in excluded)}   not matched: {len(problems)}")
    print(f"Records with full text: {len(kept)}   per batch: "
          f"{kept['batch'].value_counts().sort_index().to_dict()}")
    print("Matched by:", kept["match_method"].value_counts().to_dict())
    for name, why in problems:
        print(f"  UNMATCHED   {name}: {why}")
    for pdf in pdfs:
        if pdf.name in excluded:
            print(f"  EXCLUDED    {pdf.name}: {excluded[pdf.name]}")
    for row in kept[kept["match_method"].str.contains("check|shared")].to_dict("records"):
        print(f"  CHECK       {row['pdf_filename']} -> {row['record_key']} ({row['match_method']})")
    for row in extra.to_dict("records"):
        used = kept[kept["record_key"] == row["record_key"]]["pdf_filename"].iloc[0]
        print(f"  DUPLICATE   {row['pdf_filename']} not used: {row['record_key']} already has {used}")
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()

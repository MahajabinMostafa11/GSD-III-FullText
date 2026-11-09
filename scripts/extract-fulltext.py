#!/usr/bin/env python3
"""Extract text from the matched full-text PDFs, one text file per record.

Usage:
    python3 scripts/extract-fulltext.py                 # all records with a PDF
    python3 scripts/extract-fulltext.py --batch 1       # one batch only
    python3 scripts/extract-fulltext.py --pdf-dir "<pdf folder>"
    python3 scripts/extract-fulltext.py --ocr           # OCR the no-text / low-text scans
    python3 scripts/extract-fulltext.py --ocr --ocr-lang eng+rus
    python3 scripts/extract-fulltext.py --ocr --force --ocr-lang rus --only 2017_X_pmid1.pdf
    python3 scripts/extract-fulltext.py --relabel       # re-check quality and language of cached text
    python3 scripts/extract-fulltext.py --fix-ocr       # repair misread Roman numerals in OCR'd text

The PDF folder defaults to the path in .fulltext-dir (one line, git-ignored,
set once per machine), normally the Google Drive for desktop folder, e.g.
    ~/Library/CloudStorage/GoogleDrive-<you>/My Drive/GSD-III

Reads raw sources/fulltext-manifest.csv (from match-fulltext.py) and writes
    .fulltext-cache/<record key>.txt      the extracted text, page by page
    .fulltext-cache/extraction-report.csv pages, characters and a quality flag

.fulltext-cache/ is in .gitignore: the text is a copy of each paper and
must not be committed. Anyone with access to the PDFs can rebuild it with
this script.

OCR (--ocr) runs ocrmypdf on records whose quality is no-text or low-text
(with --force, also on records already OCR'd, e.g. to redo them in another
language; --only limits it to the named PDF files),
writes the searchable copy to .fulltext-ocr/ (git-ignored; the Drive
originals are never changed) and re-extracts from it. Install once with:
    brew install ocrmypdf            (add  brew install tesseract-lang  for non-English)

Quality flags:
    ok          normal text layer: the only quality used as full text
    low-text    little text per page; a scan whose only text is a cover sheet
    no-text     no text at all; the PDF is an image scan
    error       the PDF could not be opened
    non-english the paper's text is mainly not in English; it is not used,
                and the record is ingested at abstract depth

Requires: pip3 install pymupdf pandas
"""

import argparse
import csv
import re
import shutil
import subprocess
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
OCR_DIR = Path(".fulltext-ocr")
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


ENGLISH_WORDS = set("""the of and in to with a was is were for by that this on as are from
at an be or which these patients patient disease not have has had it its than
also between after but all may we our their been study case results""".split())


# OCR reads the Roman numeral III as "Ill", "IIl", "lII", "111" or Cyrillic "Ш".
# Only these unambiguous forms are repaired, and only after a disease or type
# word. "Il"/"Ila" could be II or III, so they are left alone and reported.
OCR_CONTEXT = r"(?P<pre>\b(?:GSD|GSDs|type|Type|TYPE|types|glycogenosis|Glycogenosis|disease|Disease)[\s-]{0,2})"
OCR_FIXES = [
    (OCR_CONTEXT + r"(?:Ill|IIl|lII|lIl|lll|111|Ш)(?P<sub>[abcdABCD]?)\b", "III"),
]
OCR_AMBIGUOUS = re.compile(r"\b(?:GSD|type|Type)[\s-]{0,2}(?:Il|lI|Ila|Ilb|lIa)\b")


def fix_ocr(text):
    """Repair unambiguous Roman-numeral misreads; return text, fixes, ambiguous spots.

    Ambiguous spots are returned as "page N: <text>" so the agent can look at
    exactly that page of the PDF. They are also written into the text file's
    header (# ocr-check: ...), replacing any earlier check line.
    """
    fixes = 0
    for pattern, numeral in OCR_FIXES:
        text, n = re.subn(pattern, lambda m: m.group("pre") + numeral + m.group("sub").lower(), text)
        fixes += n
    ambiguous = []
    for chunk in text.split("===== page ")[1:]:
        number, _, body = chunk.partition(" =====")
        for spot in sorted(set(OCR_AMBIGUOUS.findall(body))):
            ambiguous.append(f"page {number.strip()}: {spot}")
    header, sep, rest = text.partition("\n\n")
    header = "\n".join(l for l in header.splitlines() if not l.startswith("# ocr-check:"))
    if ambiguous:
        header += "\n# ocr-check: " + "; ".join(ambiguous) + \
                  " -- view these pages of the original PDF before relying on them"
    return header + sep + rest, fixes, ambiguous


def apply_ocr_fixes(text_file, row):
    fixed, n, ambiguous = fix_ocr(text_file.read_text(encoding="utf-8"))
    text_file.write_text(fixed, encoding="utf-8")
    row["note"] = re.sub(r";.*$", "", row.get("note", "")) + \
        (f"; numeral fixes {n}" if n else "") + (f"; check {len(ambiguous)}" if ambiguous else "")
    return n, ambiguous


def classify(text):
    """ok / low-text / no-text / non-english, from the extracted text."""
    n_pages = len(re.findall(r"^===== page \d+ =====$", text, re.M))
    text = re.sub(r"^===== page \d+ =====$", "", text, flags=re.M)
    chars = len("".join(text.split()))
    if chars == 0:
        return "no-text"
    letters = [c for c in text if c.isalpha()]
    latin = sum(1 for c in letters if c.isascii())
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
    english = sum(1 for w in words if w in ENGLISH_WORDS) / max(len(words), 1)
    if letters and (latin / len(letters) < 0.6 or english < 0.12):
        return "non-english"
    per_page = chars / max(n_pages, 1)
    return "low-text" if per_page < LOW_TEXT_CHARS_PER_PAGE else "ok"


def safe_name(record_key):
    return re.sub(r"[^A-Za-z0-9._-]", "_", record_key)


def extract(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages


def write_report(report_path, report):
    fields = ["record_key", "batch", "pdf_filename", "pages", "chars", "quality", "note"]
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for key in sorted(report):
            writer.writerow(report[key])
    write_scanned_list(report)


SCANNED_LIST = Path("raw sources/fulltext-scanned.csv")


def write_scanned_list(report):
    """Committed list of records whose PDF is an image scan (no usable text layer).

    These are ingested at abstract depth until the team decides on OCR. The
    list is regenerated on every run; OCR'd records stay on it, marked as such.
    """
    titles = {}
    manifest = Path("raw sources/batches/manifest.csv")
    if manifest.exists():
        for row in csv.DictReader(manifest.open(encoding="utf-8")):
            titles[row["record_key"]] = (row["Publication Year"], row["Title"])
    rows = []
    for key, row in sorted(report.items(), key=lambda kv: (kv[1]["batch"], kv[1]["pdf_filename"])):
        scanned = row["quality"] in ("no-text", "low-text") or row.get("note", "").startswith("ocr")
        if not scanned:
            continue
        year, title = titles.get(key, ("", ""))
        if row["quality"] == "non-english":
            status = "non-English; full text not used"
        elif row.get("note", "").startswith("ocr"):
            status = "OCR'd; used as full text"
        else:
            status = "image scan; abstract depth until OCR is decided"
        rows.append({"record_key": key, "batch": row["batch"], "year": year, "title": title,
                     "pdf_filename": row["pdf_filename"], "pages": row["pages"],
                     "quality": row["quality"], "status": status})
    with SCANNED_LIST.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["record_key", "batch", "year", "title", "pdf_filename",
                                                "pages", "quality", "status"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Extract full text from matched PDFs.")
    parser.add_argument("--pdf-dir", help="folder holding the PDFs (default: contents of .fulltext-dir)")
    parser.add_argument("--batch", help="only this batch number")
    parser.add_argument("--force", action="store_true", help="re-extract files already in the cache")
    parser.add_argument("--ocr", action="store_true",
                        help="OCR the records whose quality is no-text or low-text, then re-extract")
    parser.add_argument("--ocr-lang", default="eng", help="tesseract languages, e.g. eng or eng+rus")
    parser.add_argument("--only", nargs="+", metavar="PDF", help="process only these PDF filenames")
    parser.add_argument("--fix-ocr", action="store_true",
                        help="repair misread Roman numerals in OCR'd text already in the cache, then stop")
    parser.add_argument("--relabel", action="store_true",
                        help="recompute quality and language for text already in the cache, then stop")
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

    if args.fix_ocr:
        for key, row in report.items():
            if not row.get("note", "").startswith("ocr"):
                continue
            text_file = CACHE / f"{safe_name(key)}.txt"
            if not text_file.exists():
                continue
            n, ambiguous = apply_ocr_fixes(text_file, row)
            line = f"  {row['pdf_filename']}: {n} fixed"
            if ambiguous:
                line += f"; flagged for the agent to check: {', '.join(ambiguous)}"
            print(line)
        write_report(report_path, report)
        return

    if args.relabel:
        changed = 0
        for key, row in report.items():
            text_file = CACHE / f"{safe_name(key)}.txt"
            if row.get("quality") == "error" or not text_file.exists():
                continue
            body = text_file.read_text(encoding="utf-8").split("\n\n", 1)[-1]
            new = classify(body)
            if new != row["quality"]:
                print(f"  {row['pdf_filename']}: {row['quality']} -> {new}")
                row["quality"] = new
                changed += 1
        write_report(report_path, report)
        counts = pd.Series([r["quality"] for r in report.values()]).value_counts().to_dict()
        print(f"Relabelled: {changed}.  Totals by quality: {counts}")
        return

    if args.ocr and not shutil.which("ocrmypdf"):
        sys.exit("ocrmypdf is not installed. Run: brew install ocrmypdf")

    done = 0
    for row in manifest.to_dict("records"):
        out = CACHE / f"{safe_name(row['record_key'])}.txt"
        previous = report.get(row["record_key"], {})
        note = ""
        if args.only and row["pdf_filename"] not in args.only:
            continue
        if args.ocr:
            already_ocr = previous.get("note", "").startswith("ocr")
            if already_ocr and not args.force:
                continue
            if not already_ocr and previous.get("quality") not in ("no-text", "low-text"):
                continue
        elif out.exists() and not args.force and row["record_key"] in report:
            continue
        pdf = pdf_dir / row["pdf_filename"]
        if args.ocr:
            OCR_DIR.mkdir(exist_ok=True)
            ocr_pdf = OCR_DIR / f"{safe_name(row['record_key'])}.pdf"
            print(f"  OCR  {row['pdf_filename']} ...")
            result = subprocess.run(["ocrmypdf", "--force-ocr", "-l", args.ocr_lang, "--quiet",
                                     str(pdf), str(ocr_pdf)], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  OCR FAILED  {row['pdf_filename']}: {result.stderr.strip()[:200]}")
                continue
            pdf, note = ocr_pdf, f"ocr ({args.ocr_lang})"
        try:
            pages = extract(pdf)
        except Exception as exc:
            report[row["record_key"]] = {"record_key": row["record_key"], "batch": row["batch"],
                                         "pdf_filename": row["pdf_filename"], "pages": 0,
                                         "chars": 0, "quality": "error", "note": str(exc)[:200]}
            print(f"  ERROR  {row['pdf_filename']}: {exc}")
            continue
        chars = sum(len(p.strip()) for p in pages)
        quality = classify("".join(f"===== page {i} =====\n{p}" for i, p in enumerate(pages, 1)))
        with out.open("w", encoding="utf-8") as fh:
            fh.write(f"# record_key: {row['record_key']}\n# pdf: {row['pdf_filename']}\n"
                     f"# pages: {len(pages)}  quality: {quality}"
                     f"{'  ' + note + ' (machine-read: check numbers against the PDF)' if note else ''}\n\n")
            for i, text in enumerate(pages, start=1):
                fh.write(f"\n===== page {i} =====\n{text}")
        report[row["record_key"]] = {"record_key": row["record_key"], "batch": row["batch"],
                                     "pdf_filename": row["pdf_filename"], "pages": len(pages),
                                     "chars": chars, "quality": quality, "note": note}
        if note.startswith("ocr"):
            apply_ocr_fixes(out, report[row["record_key"]])
        done += 1
        if done % 25 == 0:
            print(f"  extracted {done} ...")

    write_report(report_path, report)

    counts = pd.Series([r["quality"] for r in report.values()]).value_counts().to_dict()
    print(f"Extracted this run: {done}.  Totals by quality: {counts}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()

---
name: wiki-batch
description: Ingest one batch of the publication corpus into the wiki, record by record, following CLAUDE.md and the schema. Use when the user asks to ingest, run, or continue a batch (e.g. "ingest batch 2", "/wiki-batch 2").
---

# Batch ingest

Ingest one batch from `raw sources/batches/` into the wiki. The batch number
comes from the user's request (e.g. `/wiki-batch 3`). If no number is given,
use the lowest-numbered batch that has no `batch-N` tag in the wiki repo:

```bash
git -C wiki/GSD-III-FullText.wiki tag --list "batch-*"
```

This skill replaces `/wiki-source` for corpus records. Its rules come from
`CLAUDE.md` and `SCHEMA_GSD-III-FullText.md`; where this skill is silent,
those files decide.

## Rules that apply throughout

- Read only the current batch file. Never open the full corpus CSV or a later
  batch.
- Every record in the batch gets exactly one source-summary page. Nothing is
  skipped, merged or summarized together with another record.
- Do not stop to discuss records with the user. Keep a running list of
  questions and doubts, and put it in the batch log entry.
- Claims come only from the paper's full text (where it exists) and the
  record's title, abstract and keywords. No fetching online, no details from
  memory. Never copy long passages of a paper into the wiki.

## 1. Start

1. Read `CLAUDE.md` and `wiki/GSD-III-FullText.wiki/SCHEMA_GSD-III-FullText.md`.
2. Read `wiki/GSD-III-FullText.wiki/index_GSD-III-FullText.md` and the theme
   hub pages, so you know which concept, treatment and entity pages and which
   claims already exist.
3. List the batch:

   ```bash
   python3 scripts/show-record.py "raw sources/batches/batch-N.csv" --list
   ```

4. Check which records already have pages (relevant when resuming a batch):

   ```bash
   python3 scripts/check-batch-coverage.py "raw sources/batches/batch-N.csv" wiki/GSD-III-FullText.wiki
   ```

   Work through the records reported MISSING, in list order. It also reports
   pages whose depth does not match the available full text.

5. Make sure the batch's full text is extracted (a no-op if it already is):

   ```bash
   python3 scripts/extract-fulltext.py --batch N
   ```

   It reads the PDF folder from `.fulltext-dir`. If it reports the folder is
   not reachable, stop and tell the user rather than ingesting full-text
   records at abstract depth.

## 2. For each record, one at a time

1. Show the full record:

   ```bash
   python3 scripts/show-record.py "raw sources/batches/batch-N.csv" --index <i>
   ```

   It prints every abstract version found (fullest first), every field, the
   Claude Enrichment notes (LLM-generated, not evidence), the Raw Data, and,
   last, the paper's full text with its quality flag.
2. Decide the depth:
   - full text present with quality `ok`: read all of it and
     write a `full-text` page. Use the methods, results, tables and
     discussion; ignore the reference list except to attribute what the
     authors cite. Add the `fulltext:` pointer fields.
   - full text listed but `no-text`, `low-text` or `error` (a scan), or no full text: an
     `abstract` page from the fullest abstract version (tag
     `status/fulltext-unreadable` in the first case).
   - full text marked `non-english`: do not read or use it. Write an
     `abstract` page from the record's abstract, tagged
     `status/fulltext-non-english`.
   - no full text and no abstract: `metadata-only`.
   If the page relies on an abstract that is still cut off, tag
   `status/truncated-abstract`.
   If the full text is OCR'd (its header says `ocr`), confirm every spot on
   its `# ocr-check:` line, and any subtype, number, dose or variant you take
   from it, by viewing that page of the original PDF (Read tool, the PDF path
   shown by `show-record.py`, `pages: <N>`). Leave out what stays unclear.
3. Write the source-summary page with the 11 sections from `CLAUDE.md`, in
   order, and every required frontmatter field from the schema, including
   `record_key:` copied exactly from the record.
4. Update the wiki around it:
   - add the paper to existing claims it supports or complicates, or create a
     new claim (with a new ID) if none fits;
   - create or update the concept, treatment and entity pages it informs;
   - any new disease page gets a MONDO binding through the ontology-binding
     skill; phenotypes get HPO where clear;
   - link the page to its theme hub, and the hub to the page;
   - fix links in both directions.
5. Move to the next record. Do not batch several records into one step.

Commit in the wiki repo every 10 records or so, staging files by name, so a
long batch is never at risk of losing work:

```bash
git -C wiki/GSD-III-FullText.wiki add <files>
git -C wiki/GSD-III-FullText.wiki commit -m "ingest: batch N records <i>-<j>"
```

## 3. Finish the batch

1. Confirm coverage. This must report 0 missing and 0 doubled:

   ```bash
   python3 scripts/check-batch-coverage.py "raw sources/batches/batch-N.csv" wiki/GSD-III-FullText.wiki
   ```

2. Check page structure and link reciprocity, and fix until both report
   nothing:

   ```bash
   python3 scripts/check-page-structure.py wiki/GSD-III-FullText.wiki
   python3 scripts/wiki-reciprocity.py wiki/GSD-III-FullText.wiki
   ```

   Fix one-way links as the schema's Cross-Referencing section says: add the
   paper to the target's claims or its "Further papers" line, add later
   papers to the earlier paper's "Later papers in this wiki" line, and never
   list citing pages on a `hub: true` page. Then run `/wiki-lint` and fix
   what it finds.
3. Run the Verification Gate (`wiki/agents/verification-gate.md`) over the
   pages created or edited in this batch.
4. Update `index_GSD-III-FullText.md` and the Categories section of
   `Home_GSD-III-FullText.md` where a new representative page appeared.
5. Commit the pages and index, then append the batch log entry and commit it
   on its own:

   ```markdown
   ## [YYYY-MM-DD] batch | Batch N (<first year>–<last year>)
   - by: <git config user.name> via claude-code
   - model: <your true model identifier>
   - records ingested: <n>; pages created: <n>; pages updated: <n>
   - flags: needs-review <n>, needs-ontology <n>, truncated-abstract <n>, metadata-only <n>, full-text <n>, fulltext-unreadable <n>, fulltext-non-english <n>, possible-duplicate <n>
   - new claims: <n>; claims extended: <n>
   - questions for the user: <list, or "none">
   ```

6. Tag and push:

   ```bash
   git -C wiki/GSD-III-FullText.wiki tag batch-N
   ```

   Then push following `wiki/agents/wiki-write-protocol.md`, including the tag
   (`git push origin batch-N`).
7. Report to the user: records ingested, pages created and updated, flags,
   and the questions list.

## If the session ends mid-batch

Nothing special is needed. The next session runs this skill for the same
batch; the coverage check in step 1.4 shows which records are left.

---
name: wiki-batch
description: Ingest one batch of the publication corpus into the wiki, in runs of 5 consecutive records per wiki-paper helper agent, following CLAUDE.md and the schema. Use when the user asks to ingest, run, or continue a batch (e.g. "ingest batch 2", "/wiki-batch 2", "/wiki-batch 3 pilot").
---

# Batch ingest (coordinator)

You coordinate. Records are ingested by the `wiki-paper` agent in runs of 5
consecutive records per agent, each run in a fresh context; you stay small.
Do not read records, wiki pages, the index or the schema yourself during the
batch.

The batch number comes from the request (e.g. `/wiki-batch 3`). If none is
given, use the lowest batch with no `batch-N` tag:

```bash
git -C wiki/GSD-III-FullText.wiki tag --list "batch-*"
```

**Pilot mode** (`/wiki-batch N pilot`): do only the first 10 missing records,
then run section 3 steps 2–4, commit, and stop: no log entry, no tag, no
push. Report for review.

## 1. Start

```bash
mkdir -p .batch-work
python3 scripts/precheck-batch.py N
python3 scripts/check-batch-coverage.py "raw sources/batches/batch-N.csv" wiki/GSD-III-FullText.wiki
```

If `scripts/extract-fulltext.py` exists (full-text repo), also run
`python3 scripts/extract-fulltext.py --batch N`; if it says the PDF folder is
not reachable, stop and tell the user.

The coverage check lists the records still MISSING, in batch order. Those
are your work list. If `.batch-work/questions.md` exists from a session that
stopped mid-batch, keep it.

## 2. Runs of 5 records

Split the missing records, in order, into runs of 5 (the last run may be
shorter). For each run, launch the `wiki-paper` agent with this prompt, and
wait for it to finish before launching the next:

> Batch file: `raw sources/batches/batch-N.csv`. Records, in this order:
> `<key 1>`, `<key 2>`, `<key 3>`, `<key 4>`, `<key 5>`. Ingest them.

Never run two agents at once: they edit the same concept pages.

Keep a running list of the one-line reports. After each run, rebuild the
back-link lines, then commit what changed, staging files by name:

```bash
python3 scripts/update-backlinks.py wiki/GSD-III-FullText.wiki
```


```bash
git -C wiki/GSD-III-FullText.wiki status --porcelain
git -C wiki/GSD-III-FullText.wiki add <each changed file by name>
git -C wiki/GSD-III-FullText.wiki commit -m "ingest: batch N records <i>-<j>"
```

If a report says a step failed, or the agent did not report, run the
coverage check: records of that run still MISSING go into one more run; a
record that fails twice is added to `.batch-work/questions.md` and skipped.

## 3. Finish the batch

1. Coverage must report 0 missing and 0 doubled:

   ```bash
   python3 scripts/check-batch-coverage.py "raw sources/batches/batch-N.csv" wiki/GSD-III-FullText.wiki
   ```

2. Split oversized pages, then rebuild the back-link lines, the index and the
   theme hubs' page lists:

   ```bash
   python3 scripts/claim-counts.py wiki/GSD-III-FullText.wiki
   ```

   For each concept or treatment page it lists with more than 25 claims,
   launch the `wiki-paper` agent with: "Split <page> following the schema's
   Page splitting rule; do not ingest anything." One page per agent, one at
   a time. Then:

   ```bash
   python3 scripts/update-backlinks.py wiki/GSD-III-FullText.wiki
   python3 scripts/build-index.py wiki/GSD-III-FullText.wiki
   ```

3. Structure and reciprocity must both report nothing:

   ```bash
   python3 scripts/check-page-structure.py wiki/GSD-III-FullText.wiki
   python3 scripts/wiki-reciprocity.py wiki/GSD-III-FullText.wiki
   ```

   Fix what they report. For a structure failure on a page, or one-way links
   the back-link script does not cover, launch the `wiki-paper` agent with a
   prompt naming the pages and the findings ("Fix only these findings; do
   not ingest anything").
4. Run `/wiki-lint` and fix what it finds.
5. Update the Categories section of `Home_GSD-III-FullText.md` only if a new page is
   significant enough to be a representative link.
6. Commit the pages and index. Then append the batch log entry and commit it
   on its own:

   ```markdown
   ## [YYYY-MM-DD] batch | Batch N (<first year>–<last year>)
   - by: <git config user.name> via claude-code
   - model: <your true model identifier>
   - process: coordinator + wiki-paper agent per run of 5 records (fresh context each run)
   - records ingested: <n>; pages created: <n>; pages updated: <n>
   - flags: needs-review <n>, needs-ontology <n>, truncated-abstract <n>, metadata-only <n>, possible-duplicate <n>
   - new claims: <n>; claims extended: <n>
   - questions for the user: <the contents of .batch-work/questions.md, or "none">
   ```

7. Tag and push:

   ```bash
   git -C wiki/GSD-III-FullText.wiki tag batch-N
   ```

   Push following `wiki/agents/wiki-write-protocol.md`, including the tag
   (`git push origin batch-N`). Then delete `.batch-work/questions.md`.
8. Report to the user: records ingested, pages created and updated, flags,
   and the questions list.

## If the session ends mid-batch

Run `/wiki-batch N` again. The coverage check shows which records are left;
the questions file is kept.

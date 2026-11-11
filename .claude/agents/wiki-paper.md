---
name: wiki-paper
description: Ingests a short run of consecutive corpus records (usually 5) into the wiki, one record after another, then stops. Launched by /wiki-batch; never run two at once.
model: inherit
---

You ingest a short run of records of the publication corpus into the wiki at
`wiki/GSD-III-FullText.wiki/`, following `CLAUDE.md` and
`wiki/GSD-III-FullText.wiki/SCHEMA_GSD-III-FullText.md`. The prompt gives you the batch file
and the `record_key`s, in order. Do them one after another, then report and
stop.

You start with an empty memory: the wiki is the memory. Earlier papers are
already on its pages; read what you need from there. Every tool call you make
re-sends everything you have read so far, so read only what you need and make
each call count.

## 0. Once, before the first record

Read `CLAUDE.md`, the schema and `wiki/agents/verification-gate.md` in full.
They decide everything below. Do not read them again for later records.

## For each record, in the order given

### 1. One brief

```bash
python3 scripts/paper-brief.py "<batch file>" --key <record_key>
```

It prints every abstract version (fullest first), every field, the useful
Raw Data fields, the Claude Enrichment notes (not evidence), pre-check flags,
the paper's full text in the full-text repo, then every concept, treatment,
entity and synthesis page and the most similar papers already in the wiki.
Add `--raw` only if you need a Raw Data detail it did not print.

Pre-check flags: `same-id` / `similar-title` mean a likely duplicate record
(follow CLAUDE.md's duplicate rule and link the two pages);
`shared-abstract` means the same abstract appears under another title, so
check whether it belongs to this paper; if not, build the page from title and
metadata only and tag `status/needs-review`.

### 2. Read only what you will change

- Concept and treatment pages are long. Find what you need with Grep first
  (for example `^\*\*C[0-9]` for the claims, or a key term), then Read only
  those lines with offset and limit. Read a whole page only if you must edit
  its overview.
- A page you already read for an earlier record in this run is in your
  context: do not read it again unless you changed it and need the new lines.
- Never open `index_GSD-III-FullText.md` or the theme hubs' page lists: a script
  rebuilds them at the end of the batch.

### 3. Write the source-summary page

All 11 sections, exactly as CLAUDE.md lists them, with every required
frontmatter field, including `record_key` copied exactly, and the depth
CLAUDE.md requires for this record. The first author comes from the source
order CLAUDE.md gives.

### 4. Update the wiki around it

- Add the paper to existing claims it supports or complicates; create a new
  claim (next free ID on that page) only when no existing claim fits.
- Create a concept, treatment or entity page only when the paper needs one
  and none exists; give any new disease page its MONDO binding through the
  ontology-binding skill.
- Link freely from the new page to the earlier papers and pages it relates
  to. Do not edit any "Later papers in this wiki" or "Further papers" line,
  on any page: `scripts/update-backlinks.py` writes them from the links.
- Do not edit `index_GSD-III-FullText.md` or the theme hubs' "## Pages" sections.

### 5. Check

Apply the Verification Gate criteria to the pages you created or edited. The
structure script stands in for re-reading your new page from disk:

```bash
python3 scripts/check-page-structure.py wiki/GSD-III-FullText.wiki --pages <your page>.md
```

Fix anything it reports. Do not commit; the coordinator commits.

### 6. Doubts

Append any question for the user to `.batch-work/questions.md`, one line
each: `` `<record_key>`: <question> ``.

## Report

When every record in the run is done, reply with one line per record and
nothing else:

`<record_key> | <page name> | depth: <depth> | claims extended: <n>, new: <n> | pages edited: <n> | flags: <tags or none>`

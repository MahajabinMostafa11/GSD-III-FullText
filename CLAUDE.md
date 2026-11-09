# CLAUDE.md

Guidance for AI coding assistants working on this repository.

## What this repository is

GSD-III-FullText is a source-grounded, LLM-maintained wiki on glycogen
storage disease type III (GSD III; Cori/Forbes disease), an autosomal
recessive deficiency of the glycogen debranching enzyme (AGL). It covers the
disease's molecular genetics, mechanisms, clinical manifestations (hepatic,
cardiac, skeletal muscle and other), diagnosis, and treatments. It is built
from full-text publications, with the corpus records (abstracts and
metadata) for papers whose full text is not available. The wiki lives at `wiki/GSD-III-FullText.wiki/`
(a separate git repo with its own remote).

**NOT MEDICAL ADVICE.** This wiki summarizes research. It must never give
individualized diagnosis, dosing, or treatment recommendations.

It is populated two ways: the publication corpus in `raw sources/`, ingested
in batches; and single sources handed over interactively (`/wiki-source`).

The authoritative conventions reference is
`wiki/GSD-III-FullText.wiki/SCHEMA_GSD-III-FullText.md` (page types, evidence
grading, tag taxonomy, epistemic safeguards, operations). Read it before
non-trivial wiki work. The rules below are this project's additions to the
schema; where the two disagree, this file wins. The underlying pattern is
`llm-wiki.md`; the knowledge graph is `scripts/kg/` (rebuild:
`./scripts/kg/build-graph.sh`).

## Disease grounding (mandatory)

- GSD III is `MONDO:0009291` ("glycogen storage disease III"). This ID must
  appear in the `Home_GSD-III-FullText.md` frontmatter (`mondo:`) and on the
  `GSD-III` entity page (`ontology_id:` / `ontology_label:`).
- Every other disease that gets its own page (e.g. GSD I, Pompe disease,
  McArdle disease) must also carry its MONDO ID and exact MONDO label.
- Never type an ontology ID from memory. Look up every ID with the
  ontology-binding skill (`.claude/skills/ontology-binding/SKILL.md`), which
  runs:

  ```bash
  python3 scripts/kg/lookup-ontology-term.py lookup --prefix mondo --query "<disease name>" --exact
  ```

  Copy the returned ID and label verbatim. Use `--prefix hp` for phenotypes.
  If the exact lookup returns nothing, try a fuzzy lookup (drop `--exact`) and
  pick a candidate only if it clearly matches. If nothing matches, leave the
  field off, tag the page `status/needs-ontology`, and note it in the log. A
  missing ID can be added later; a wrong one corrupts the knowledge graph.

## Sources

- Use only the publication corpus in `raw sources/`, every field of each
  record, and the paper's full text where one exists. Do not fetch papers or
  abstracts online, and do not add details about a paper from memory. If
  neither the record nor the paper's full text states it, the wiki does not
  claim it.
- Full text: `raw sources/fulltext-manifest.csv` lists which records have a
  PDF (stored in Google Drive, never in git; the local path to the Drive
  folder is in the git-ignored file `.fulltext-dir`). Their text is extracted by
  `scripts/extract-fulltext.py` into `.fulltext-cache/`, and
  `scripts/show-record.py` prints it with the record. Never commit
  `.fulltext-cache/` or copy long passages of a paper into the wiki: the
  papers are copyrighted. Summarize in your own words; quote at most a short
  phrase, with its page number.
- Fields are used according to what they are:
  - **Content** (full text where available; title, abstract, keywords): the
    only basis for claims about what a paper studied or found. Claims about
    other studies that the paper merely cites are the paper's citations, not
    its findings: attribute them as "the authors cite …", or leave them out.
  - **Bibliographic** (authors, year, journal and source titles, DOI, PubMed
    ID, Web of Science ID, Google Scholar ID, BibTeX): the Record metadata
    section.
  - **Classification** (WoS, PubMed and Google Scholar document types,
    PubMed publication types, Diseases, Disease Codes, Times Cited): recorded
    in Record metadata. Times Cited is a snapshot; report it as of the
    record's Created At date.
  - **Pipeline** (Sources, Overlap Category, Needs Review and its reasons,
    Corpus Excluded and its reasons, Created At): recorded in Record
    metadata. A record with Needs Review set to true gets the
    `status/needs-review` tag.
  - **Raw Data (JSON)**: the original PubMed, Web of Science and Google
    Scholar entries for the record. If the Abstract column is a short or
    cut-off snippet and Raw Data holds a fuller abstract for the same paper,
    use the fullest version and say which source it came from.
  - **Claude Enrichment (JSON)**: notes written by an earlier model. Record
    them as LLM-generated metadata, labelled as such. Never treat them as
    evidence or base a claim on them.
- `ingestion_depth:` on every source-summary page says what was actually
  read:
  - `full-text` when the paper's extracted text was read in full. Required
    whenever the record has full text of quality `ok`.
  - `abstract` when there is no full text, or its text could not be read
    (quality `no-text`, `low-text` or `error`: an image-only scan, or a scan
    whose only text is a cover sheet). Tag such pages
    `status/fulltext-unreadable` and say so on the page. Scanned papers are
    listed in `raw sources/fulltext-scanned.csv`; OCR for them is not used
    for now.
  - `abstract` also when the paper is not written in English (quality
    `non-english`). Its full text is not used at all; the page is built from
    the record's English title and abstract, tagged
    `status/fulltext-non-english`, and says so. The paper still gets its page.
  - `metadata-only` when there is neither full text nor a usable abstract in
    any field; the page says plainly that only bibliographic information was
    available.
- If OCR is adopted later: OCR'd papers (marked `ocr` in the text header) can contain
  misread characters. Before stating a subtype, Roman numeral, number, dose
  or variant taken from OCR'd text, and for every spot listed on the header's
  `# ocr-check:` line, view that page of the original PDF (the Read tool on
  the PDF path printed by `scripts/show-record.py`, with `pages: <N>`) and
  use what the page image shows. If it is still unclear, leave the detail out
  of the page rather than guess.
- An abstract that is still cut off after checking Raw Data gets the
  `status/truncated-abstract` tag when the page relies on it.
- Full-text pages carry the pointer fields `fulltext:` (the PDF's Drive path
  from the manifest, e.g. `gdrive:GSD-III/<file>.pdf`), `fulltext_by:` and
  `fulltext_access:` (see the schema's Full-text store section).

## Every paper gets a page (no skipping)

- Every record in the corpus gets exactly one source-summary page. This
  overrides the "When to skip" section of the `/wiki-source` skill.
- That includes records with no abstract, off-topic papers, case reports, and
  records with garbled titles. Tag doubtful records `status/needs-review`
  rather than leaving them out.
- If two records look like the same paper, still create both pages, link them
  to each other with `related:`, and flag the pair in the log. Do not merge.
- Each page records the corpus record it came from, so coverage can be
  checked: `record_key:` holds the record's key exactly as it appears in the
  batch file, and `sources:` includes the DOI or PubMed ID when present,
  otherwise the title.

## Rich pages, one paper per page

Never combine two papers on one source-summary page, and never compress a
paper's separate findings into one sentence. A paper that makes several
points gets a separate bullet or section for each.

Every source-summary page uses these sections, in this order:

1. **Citation**: authors, title, journal, year, DOI, PubMed ID.
2. **Study type and design**: case report, cohort, trial, review, animal
   model, in vitro, and so on.
3. **Population or sample**: who or what was studied, with numbers.
4. **Key findings**: one bullet per distinct finding, with numbers exactly as
   the source states them.
5. **Methods detail**: only what the source states. If it is not stated,
   write "Not stated in the paper" (full-text pages) or "Not stated in the
   abstract" (abstract pages).
6. **Authors' conclusions**.
7. **Limitations and caveats**: those the source states, plus obvious scope
   limits (e.g. single case, small sample).
8. **Connections**: links to the concept and entity pages this paper informs,
   and a "Later papers in this wiki" line listing later source-summary pages
   that link to this one (kept up to date as later papers arrive).
9. **Ontology terms**: diseases (MONDO), and phenotypes and genes where clear.
10. **Source link**.
11. **Record metadata**: every remaining field of the corpus record, grouped
    as described under Sources, so no field is dropped.

The 11 sections are fixed. Every source-summary page has all of them, with
exactly these headings, in this order: none merged, none renamed, none added.
A section with nothing to report says so in one line (for example "Not
stated in the abstract."). A record that duplicates another keeps the same 11
sections: explain the duplication under Citation, link the companion page
under Connections, and fill the other sections from this record as usual.
`scripts/check-page-structure.py` enforces this.

On concept and synthesis pages, attribute every claim to the paper it comes
from, with a link to that paper's page. When papers disagree, show each one's
result side by side. Never blend several papers into one unattributed claim.

Name source-summary pages `Surname-Year-Short-Topic.md`.

## Conventions when editing

- **Medical epistemics are hard rules** (SCHEMA Epistemics), enforced by the
  Verification Gate on every claim-bearing page:
  - an `evidence:` grade is required;
  - state the study design, and whether a finding is an association or a
    causal result;
  - keep subtype claims (IIIa, IIIb, IIIc, IIId) tied to the subtype studied,
    and do not generalize a single case or a single founder population to all
    patients;
  - show contested findings with the strongest case on each side, each
    attributed to its paper;
  - never delete superseded content: mark it `lifecycle: superseded`;
  - no hype. A treatment that failed does not by itself refute the mechanism
    it targeted.
- **Honest reporting**: report only what cited sources state. Negative
  results, null findings and contradicted claims are filed truthfully, not
  softened.
- **Style**: prose over tables for explanations; tables are fine for
  numbers, mutation lists and comparisons. Avoid em-dash tics where a comma
  or period reads cleaner.

## Batch ingestion

- The corpus is ingested in chronological batches, `raw sources/batches/batch-N.csv`,
  each holding complete records. Run a batch with the `/wiki-batch` skill
  (`.claude/skills/wiki-batch/SKILL.md`). Use `/wiki-source` only for a single
  source handed over interactively, never for corpus records.
- Ingest only the current batch. Never open the full corpus file or a later
  batch.
- Within a batch, handle papers one at a time: read the record with
  `scripts/show-record.py`, write the paper's page, update the concept and
  entity pages it affects, then move on.
- A batch is finished only when `scripts/check-batch-coverage.py` reports no
  missing and no doubled records, `scripts/check-page-structure.py` reports
  no failing pages, and `scripts/wiki-reciprocity.py` reports no one-way
  links (see the schema's Cross-Referencing rules for hub pages).
- Do not stop to discuss individual papers with the user during a batch. Keep
  questions in a list and report them in the batch's log entry.
- After each batch: run `/wiki-lint`, fix what it finds, update the index and
  log, commit in the wiki repo, then tag the wiki repo `batch-N`.
- Each batch's log entry records: the date, the model used, the batch number,
  the number of papers ingested, the pages created and updated, and any
  `needs-review` or `needs-ontology` flags.

## Commit and push

Every wiki edit ends with a commit. First run the Verification Gate
(`wiki/agents/verification-gate.md`) over every page created or edited; then,
without asking, stage by name and commit:

```bash
git -C wiki/GSD-III-FullText.wiki add <files-by-name>
git -C wiki/GSD-III-FullText.wiki commit -m "<descriptive message>"
```

Push at the end of each batch, and otherwise only when asked. When pushing,
follow `wiki/agents/wiki-write-protocol.md` rather than a plain `git push`.

Wiki commit trailer: `Co-Authored-By: Claude <model> <noreply@anthropic.com>`,
substituting your harness's true model identifier for `<model>`. Never copy a
version string from this file.

## Rule changes

- Do not change these rules or the schema in the middle of a batch.
- Record any rule change in the log before the next batch starts.

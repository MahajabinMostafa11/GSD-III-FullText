# GSD-III-FullText

A knowledge base tracking glycogen storage disease type III (GSD III; Cori/Forbes disease), built from full-text publications, with abstracts for papers whose full text is not available. GSD III is an autosomal recessive deficiency of the glycogen debranching enzyme (AGL), spanning subtypes IIIa–IIId, with liver, cardiac, and skeletal muscle involvement. Disease grounding: [MONDO:0009291](http://purl.obolibrary.org/obo/MONDO_0009291).

> **Not medical advice.** This wiki summarizes research and does not give individualized diagnosis, dosing, or treatment recommendations.

## This repository uses LLM wiki memory

GSD-III-FullText keeps a persistent, LLM-maintained knowledge base under `wiki/GSD-III-FullText.wiki/` (a separate git repo), following the llm-wiki pattern (`llm-wiki.md` in the project repo). It is the project's durable memory: every publication in `raw sources/` gets its own source-summary page, and findings accumulate into linked concept, entity, and synthesis pages over time. The corpus is ingested in batches, and the wiki is tagged `batch-N` after each one.

Three operations, **Query** (read it), **Ingest** (write to it), and **Lint** (health-check it), are codified in `CLAUDE.md`, in `wiki/GSD-III-FullText.wiki/SCHEMA_GSD-III-FullText.md`, and in the `.claude/` skills (`/wiki-source`, `/wiki-experiment`, `/wiki-lint`). See also [llm-wiki.md](llm-wiki.md) in this repo for the underlying pattern.

## Quick start for collaborators

New to GSD-III-FullText? Clone the project repo, clone the wiki as a sibling sub-repo, then seed your local Claude Code memory:

```bash
git clone https://github.com/MahajabinMostafa11/GSD-III-FullText.git
cd GSD-III-FullText
[ -d wiki/GSD-III-FullText.wiki ] || \
    git clone https://github.com/MahajabinMostafa11/GSD-III-FullText.wiki.git wiki/GSD-III-FullText.wiki
./wiki/agents/claude-code/setup.sh --seed-memory
```

The wiki clone is guarded with `[ -d … ] ||` because the Claude Code overlay's `SessionStart` hook (`ensure-wiki.py`, installed by `setup.sh --hook`) auto-clones the wiki on first session start. If you opened Claude Code before running these commands, the wiki is already in place and the inner `git clone` does nothing.

After this, open Claude Code inside the repo. It picks up the project's slash commands (`/wiki-source` to ingest a single source, `/wiki-experiment` to file experiment results, `/wiki-lint` to health-check the wiki) along with the conventions in `CLAUDE.md`.

The wiki at `wiki/GSD-III-FullText.wiki/` is a separate git repo with its own history and its own remote. After any wiki edit, commit in the wiki repo (not the project repo):

```bash
git -C wiki/GSD-III-FullText.wiki add <files>
git -C wiki/GSD-III-FullText.wiki commit -m "..."
```

Push the wiki only when you intend to publish the changes:

```bash
git -C wiki/GSD-III-FullText.wiki push origin master
```

## About the template

This project was instantiated from [crcresearch/llm-wiki-memory-template](https://github.com/crcresearch/llm-wiki-memory-template). Maintainers who need to pull template updates, add a new agent overlay, or understand the instantiate/update scripts should read the template repo's documentation.

---
name: ontology-binding
description: Add or check ontology_id/ontology_label frontmatter on wiki pages about a disease, phenotype, gene, or other ontology-indexed concept. Use whenever such a page is created or edited, including during batch ingestion and /wiki-source.
---

# Ontology Binding

Pages about a disease, phenotype, gene, or similar concept carry an ontology
binding in their frontmatter. This skill makes sure every binding comes from a
reproducible lookup, never from memory.

## When to use

- Creating a page for a disease, phenotype, gene, or other ontology-indexed
  concept (including during batch ingestion and `/wiki-source`).
- Adding a binding to an existing page that lacks one.
- Re-checking an existing binding on request.

Every disease page must have a MONDO binding (see `CLAUDE.md`, "Disease
grounding"). Phenotype and gene bindings are encouraged where the concept is
clear.

## Rule

Never type an `ontology_id` or `ontology_label` by hand. Run the lookup script
and copy its output verbatim. If it returns nothing, leave the fields off, tag
the page `status/needs-ontology`, and note it in the log. A missing binding
can be added later; a wrong one silently corrupts the knowledge graph.

## How to look up a term

```bash
python3 scripts/kg/lookup-ontology-term.py lookup --prefix <prefix> --query "<term>" --exact
```

Common prefixes: `mondo` (disease), `hp` (phenotype), `go` (biological
process), `uberon` (anatomy), `cl` (cell type), `ncit` (treatment or
procedure).

If the exact lookup returns nothing, drop `--exact` and review the candidates.
Pick one only if it clearly means the same thing as the page's concept; never
take the first result blindly. Also try the term's common synonyms.

## Writing the result into frontmatter

Copy the script's `id` and `label` exactly:

```yaml
ontology_id: MONDO:0009291
ontology_label: glycogen storage disease III
```

`ontology_id` and `ontology_label` always come from the same lookup and are
always added together. Add `ontology_xrefs` only if a lookup actually returns
cross-references; never fill them in from memory.

## Subtypes

Clinical subtypes (for GSD III: IIIa, IIIb, IIIc, IIId) may not have their own
ontology terms. Look each one up before assuming it does. If no term exists,
bind only the parent disease and say in the page body that the subtype is
distinguished clinically or genetically, not by a separate ontology term.

## Mistakes to avoid

- Using an ID because it "looks right." A remembered ID is a guess to verify
  with the script, not a fact.
- Reusing an ID from a similar-sounding page without running the lookup for
  this page's own term.
- Binding a related but different concept (a broader parent, a different
  species, a different subtype) just because it was the closest result.

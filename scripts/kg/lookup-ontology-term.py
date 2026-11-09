#!/usr/bin/env python3
"""Look up ontology terms (MONDO, HP, GO, ...) on EBI's Ontology Lookup Service.

Uses OAK's OLS adapter, so it queries OLS live and needs no local ontology
download. Wiki frontmatter IDs must come from this script's output, never
from memory.

Requires:
    pip3 install oaklib --break-system-packages

Usage:
    python3 scripts/kg/lookup-ontology-term.py lookup --prefix mondo --query "glycogen storage disease III" --exact
    python3 scripts/kg/lookup-ontology-term.py lookup --prefix hp --query "hepatomegaly" --exact

Output is JSON. Exit code is 0 when at least one term matched, 1 otherwise.
"""

import argparse
import json
import sys


def get_adapter(prefix):
    try:
        from oaklib import get_adapter as oak_get_adapter
    except ImportError:
        sys.exit("oaklib is not installed. Run: pip3 install oaklib --break-system-packages")
    try:
        return oak_get_adapter(f"ols:{prefix}")
    except Exception as exc:
        sys.exit(f"Could not reach ontology '{prefix}' on OLS: {exc}")


def lookup(prefix, query, exact):
    adapter = get_adapter(prefix)
    wanted = query.strip().lower()
    results = []
    seen = set()
    for curie in adapter.basic_search(query):
        if curie in seen:
            continue
        seen.add(curie)
        label = adapter.label(curie)
        if not label:
            continue
        if exact and label.strip().lower() != wanted:
            continue
        results.append({"id": curie, "label": label})
    return results


def main():
    parser = argparse.ArgumentParser(description="Look up ontology terms on EBI OLS.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("lookup", help="search one ontology for a term")
    p.add_argument("--prefix", required=True, help="ontology prefix: mondo, hp, go, uberon, ncit ...")
    p.add_argument("--query", required=True, help="term to search for")
    p.add_argument("--exact", action="store_true", help="keep only labels that match the query exactly")
    args = parser.parse_args()

    results = lookup(args.prefix, args.query, args.exact)
    print(json.dumps({
        "query": args.query,
        "prefix": args.prefix,
        "exact": args.exact,
        "results": results,
    }, indent=2))
    sys.exit(0 if results else 1)


if __name__ == "__main__":
    main()

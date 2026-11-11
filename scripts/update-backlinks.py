#!/usr/bin/env python3
"""Write the "Later papers in this wiki" and "Further papers" lines from the links.

These two lines are bookkeeping: they list who links to a page. The agents no
longer edit them by hand; this script rebuilds them from the links that exist.

  - Source-summary page B, Connections section:
        - Later papers in this wiki: <every source-summary page of the same
          year or later that links to B>
  - Source-summary page P, Connections section:
        - Also cited on: <every concept, treatment, entity or synthesis page
          (not hub: true) that links to P, where P does not already link to
          it elsewhere, e.g. a sub-page created when a large page was split>
  - Concept or treatment page C (not hub: true), Related section:
        - Further papers (passing mentions, no distinct claim): <every
          source-summary page that links to C but that C links to nowhere
          else, i.e. not in a claim or its text>

A page's own "Later papers" / "Further papers" line never counts as a link
from that page. Lines are listed by year, then name. If a page has no such
line yet, it is added at the end of the section. Running it twice changes
nothing the second time.

Usage:
    python3 scripts/update-backlinks.py wiki/<repo>.wiki [--check]
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\]\(([A-Za-z0-9][^)#\s]*)(?:#[^)]*)?\)")
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
LATER = "- Later papers in this wiki:"
FURTHER = "- Further papers (passing mentions, no distinct claim):"
ALSO = "- Also cited on:"
TOPIC = ("concept", "treatment", "entity", "synthesis")
YEAR = re.compile(r"-(1[89]\d\d|20\d\d)(?:-|$)")


def field(front, name):
    m = re.search(rf"^{name}:\s*(.*)$", front, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def strip_line(text, prefix):
    return "\n".join(l for l in text.split("\n") if not l.startswith(prefix))


def section_bounds(text, heading):
    m = re.search(rf"^## {re.escape(heading)}\s*$", text, re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return m.end(), (m.end() + nxt.start()) if nxt else len(text)


def set_line(text, heading, prefix, items):
    line = f"{prefix} {', '.join(items) if items else 'none yet.'}"
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(prefix):
            if l == line:
                return text
            lines[i] = line
            return "\n".join(lines)
    bounds = section_bounds(text, heading)
    if bounds is None:
        return text
    start, end = bounds
    body = text[start:end].rstrip("\n")
    return text[:start] + body + "\n" + line + "\n\n" + text[end:].lstrip("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wiki_dir")
    parser.add_argument("--check", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()
    wiki = Path(args.wiki_dir)

    pages = {}
    for path in sorted(wiki.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = FM.match(text)
        if not m:
            continue
        front = m.group(1)
        year = YEAR.search(path.stem)
        title = field(front, "title") or path.stem
        pages[path.stem] = {
            "path": path, "text": text, "front": front,
            "type": field(front, "type"), "hub": field(front, "hub") == "true",
            "year": int(year.group(1)) if year else 9999,
            "label": title.split(" — ")[0].strip(),
        }

    def links_from(name, ignore_prefix):
        p = pages[name]
        body = strip_line(p["text"], ignore_prefix)
        targets = set(LINK.findall(body)) | set(WIKILINK.findall(p["front"]))
        return {t for t in targets if t in pages and t != name}

    # who links to whom, ignoring each source's own "Later papers" line
    cited_by = defaultdict(set)
    for name, p in pages.items():
        if p["type"] != "source-summary":
            continue
        for t in links_from(name, LATER):
            cited_by[t].add(name)

    # which topic pages link to each paper, ignoring the topic's own Further line
    topic_links = defaultdict(set)
    for name, p in pages.items():
        if p["type"] in TOPIC and not p["hub"]:
            for t in links_from(name, FURTHER):
                if pages[t]["type"] == "source-summary":
                    topic_links[t].add(name)

    def fmt(names):
        ordered = sorted(names, key=lambda n: (pages[n]["year"], n.lower()))
        return [f"[{pages[n]['label']}]({n})" for n in ordered]

    changed = []
    for name, p in pages.items():
        new = p["text"]
        if p["type"] == "source-summary":
            later = {a for a in cited_by.get(name, ()) if pages[a]["year"] >= p["year"]}
            new = set_line(new, "Connections", LATER, fmt(later))
            own = links_from(name, ALSO) - set()
            also = {c for c in topic_links.get(name, ()) if c not in own}
            if also or ALSO in p["text"]:
                new = set_line(new, "Connections", ALSO,
                               [f"[{pages[c]['label']}]({c})" for c in sorted(also, key=str.lower)])
        elif p["type"] in ("concept", "treatment") and not p["hub"]:
            elsewhere = set(LINK.findall(strip_line(p["text"], FURTHER)))
            further = {a for a in cited_by.get(name, ()) if a not in elsewhere}
            if further or FURTHER in p["text"]:
                new = set_line(new, "Related", FURTHER, fmt(further))
        if new != p["text"]:
            changed.append(name)
            if not args.check:
                p["path"].write_text(new, encoding="utf-8")

    verb = "would change" if args.check else "updated"
    print(f"Back-link lines {verb} on {len(changed)} page(s).")
    for n in changed[:40]:
        print(f"  {n}")
    if len(changed) > 40:
        print(f"  ... and {len(changed) - 40} more")


if __name__ == "__main__":
    main()

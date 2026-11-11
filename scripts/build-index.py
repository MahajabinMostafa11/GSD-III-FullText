#!/usr/bin/env python3
"""Rebuild the wiki index and the page lists on the theme hubs from frontmatter.

The agent no longer edits these by hand. Run at the end of every batch (and any
time after pages change):

    python3 scripts/build-index.py wiki/<repo>.wiki

What it writes:
  - index_<repo>.md: every page, grouped by theme (from `theme/` tags), then by
    page type; a "Pages with no theme group" section; "Flagged pages" by
    `status/` tag; and counts.
  - each theme hub (`type: theme`): its "## Pages" section, between "## Pages"
    and the next "## " heading. The hub's own text above and below is kept.

Entries are `[title](Page) — description`, taken from each page's frontmatter.
Source summaries are listed by year, the others alphabetically.
Use --check to report what would change without writing.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
TYPE_ORDER = [("concept", "Concepts"), ("treatment", "Treatments"), ("entity", "Entities"),
              ("synthesis", "Syntheses"), ("analysis", "Analyses"), ("decision", "Decisions"),
              ("source-summary", "Source summaries")]


def field(front, name):
    m = re.search(rf"^{name}:\s*(.*)$", front, re.M)
    if not m:
        return ""
    value = m.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].replace('\\"', '"')
    return value


def tags_of(front):
    m = re.search(r"^tags:\s*\[(.*?)\]\s*$", front, re.M)
    if m:
        return [t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()]
    m = re.search(r"^tags:\s*\n((?:\s*-\s*.*\n)+)", front + "\n", re.M)
    if m:
        return [l.strip()[1:].strip().strip("\"'") for l in m.group(1).splitlines() if l.strip()]
    return []


def load(wiki):
    pages = {}
    for path in sorted(wiki.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = FM.match(text)
        if not m:
            continue
        front = m.group(1)
        ptype = field(front, "type")
        if ptype in ("index", "reference", "") or path.stem.startswith(("index_", "log_", "Home")):
            continue
        tags = tags_of(front)
        year = re.search(r"-(1[89]\d\d|20\d\d)-", path.stem)
        pages[path.stem] = {
            "type": ptype,
            "title": field(front, "title") or path.stem,
            "description": field(front, "description"),
            "tags": tags,
            "themes": [t for t in tags if t.startswith("theme/")],
            "status": [t for t in tags if t.startswith("status/")],
            "year": int(year.group(1)) if year else 9999,
        }
    return pages


def entry(name, page):
    desc = f" — {page['description']}" if page["description"] else ""
    return f"- [{page['title']}]({name}){desc}"


def sort_key(item):
    name, page = item
    if page["type"] == "source-summary":
        return (page["year"], name.lower())
    return (0, page["title"].lower())


def grouped_lists(members, pages, heading_level="###"):
    lines = []
    for ptype, label in TYPE_ORDER:
        group = sorted(((n, pages[n]) for n in members if pages[n]["type"] == ptype), key=sort_key)
        if group:
            lines += ["", f"{heading_level} {label}", ""] + [entry(n, p) for n, p in group]
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wiki_dir")
    parser.add_argument("--check", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    wiki = Path(args.wiki_dir)
    schema = sorted(wiki.glob("SCHEMA_*.md"))
    schema = [s for s in schema if not s.stem.endswith("_HISTORY")]
    if not schema:
        sys.exit(f"No SCHEMA_<repo>.md in {wiki}")
    repo = schema[0].stem[len("SCHEMA_"):]
    pages = load(wiki)
    hubs = {n: p for n, p in pages.items() if p["type"] == "theme"}
    theme_of_hub = {}
    for name, hub in hubs.items():
        for t in hub["themes"]:
            theme_of_hub[t] = name

    members = defaultdict(list)
    no_theme = []
    for name, page in pages.items():
        if page["type"] == "theme":
            continue
        if not page["themes"]:
            no_theme.append(name)
        for t in page["themes"]:
            members[t].append(name)

    changed = []

    # ---- theme hubs ----
    for theme, hub_name in sorted(theme_of_hub.items(), key=lambda kv: kv[1]):
        path = wiki / f"{hub_name}.md"
        text = path.read_text(encoding="utf-8")
        block = "## Pages\n" + "\n".join(grouped_lists(members.get(theme, []), pages)) + "\n\n"
        if "## Pages" in text:
            new = re.sub(r"## Pages\n.*?(?=^## |\Z)", lambda m: block, text, count=1, flags=re.S | re.M)
        else:
            new = re.sub(r"(?=^## See also)", lambda m: block, text, count=1, flags=re.M) \
                if "## See also" in text else text.rstrip() + "\n\n" + block
        if new != text:
            changed.append(path.name)
            if not args.check:
                path.write_text(new, encoding="utf-8")

    # ---- index ----
    index_path = wiki / f"index_{repo}.md"
    out = [
        "---", "type: index", f'up: "[[Home_{repo}]]"', "---", "",
        f"# Index — {repo}", "",
        "Catalog of every wiki page, organized by theme group and then by page type.",
        "Generated by `scripts/build-index.py` from page frontmatter; do not edit by hand.",
        f"The authoritative conventions are in [SCHEMA](SCHEMA_{repo}).", "",
        "A page appears under every theme group it is tagged with, so cross-cutting",
        "pages are listed more than once.", "",
        "## Navigation and schema", "",
        f"- [Home](Home_{repo}) — human-facing entry point",
        f"- [SCHEMA](SCHEMA_{repo}) — page types, evidence grading, epistemics",
        f"- [Log](log_{repo}) — chronological record of wiki activity",
        "- [Edge-Types](Edge-Types) — typed-edge predicate vocabulary",
    ]
    for theme, hub_name in sorted(theme_of_hub.items(), key=lambda kv: kv[1]):
        hub = pages[hub_name]
        heading = re.sub(r"^Theme\s*[—-]\s*", "", hub["title"])
        out += ["", f"## {heading}", "", f"- **[{hub['title']}]({hub_name})** — theme hub. {hub['description']}"]
        out += grouped_lists(members.get(theme, []), pages)
    out += ["", "## Pages with no theme group", ""]
    out += [entry(n, pages[n]) for n in sorted(no_theme)] or \
        ["None — every content page carries at least one theme group."]
    flags = defaultdict(list)
    for name, page in pages.items():
        for s in page["status"]:
            flags[s].append(name)
    out += ["", "## Flagged pages", ""]
    for s in sorted(flags):
        links = ", ".join(f"[{n}]({n})" for n in sorted(flags[s]))
        out.append(f"- `{s}` ({len(flags[s])}): {links}")
    if not flags:
        out.append("None.")
    counts = defaultdict(int)
    for page in pages.values():
        counts[page["type"]] += 1
    out += ["", "## Counts", ""]
    for ptype, label in TYPE_ORDER + [("theme", "Theme hubs")]:
        if counts.get(ptype):
            out.append(f"- {label.lower()}: **{counts[ptype]}**" if ptype == "source-summary"
                       else f"- {label.lower()}: {counts[ptype]}")
    new_index = "\n".join(out) + "\n"
    old_index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if new_index != old_index:
        changed.append(index_path.name)
        if not args.check:
            index_path.write_text(new_index, encoding="utf-8")

    verb = "would change" if args.check else "updated"
    print(f"Pages: {len(pages)}   theme hubs: {len(hubs)}   {verb}: {len(changed)} file(s)")
    for name in changed:
        print(f"  {name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Everything a helper needs about one record, in a single call.

Prints the record (scripts/show-record.py) followed by the pages it most
likely connects to (scripts/related-pages.py), so ingesting a paper starts
with one tool call instead of two.

Usage:
    python3 scripts/paper-brief.py "raw sources/batches/batch-3.csv" --key pmid:10982190
    (add --raw to include the complete Raw Data JSON)
"""

import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
args = sys.argv[1:]
if len(args) < 3 or "--key" not in args:
    sys.exit(__doc__)
related_args = [a for a in args if a != "--raw"]
for script, extra in (("show-record.py", args), ("related-pages.py", related_args)):
    result = subprocess.run([sys.executable, str(here / script)] + extra)
    if result.returncode != 0:
        sys.exit(result.returncode)
    print()

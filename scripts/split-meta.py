#!/usr/bin/env python3
"""Split Meta.yaml into per-service rule files.

Meta.yaml is the single source of truth (self-reviewed bucket).
This script derives Facebook.yaml, Instagram.yaml, WhatsApp.yaml,
Threads.yaml and Messenger.yaml from it, so the per-service files
update automatically whenever the bucket changes. The old Repcz
per-service files are NOT used: Instagram had 4 entries, Threads 1,
and FaceBook's 570 were mostly typosquat domains.

Section comments are the authority for existing entries. Entries
appended by merge-meta.py land at the end of the file, after the
last section; those are classified by domain name instead.
Unclassifiable trailing entries stay bucket-only and are warned
about, never silently dropped into a wrong file.

Run: python3 scripts/split-meta.py [--file Meta.yaml] [--out-dir .]
Exit 0. A file is written only when its content changed.
"""

import argparse
import sys
from pathlib import Path

SECTION_FILES = {
    "Facebook 主站与短链": "Facebook.yaml",
    "Facebook 区域域名": "Facebook.yaml",
    "Instagram": "Instagram.yaml",
    "Messenger": "Messenger.yaml",
    "WhatsApp": "WhatsApp.yaml",
    "Threads": "Threads.yaml",
}

# Exact hosts in domain_set, mapped by name.
EXACT_FILES = {
    "fbstatic-a.akamaihd.net": "Facebook.yaml",
    "fbexternal-a.akamaihd.net": "Facebook.yaml",
    "fbcdn-a.akamaihd.net": "Facebook.yaml",
    "instagramstatic-a.akamaihd.net": "Instagram.yaml",
}

# Shared Meta infra suffixes, kept with the flagship service file.
INFRA_FILES = {
    "tfbnw.net": "Facebook.yaml",
    "internalfb.com": "Facebook.yaml",
    "mcrouter.net": "Facebook.yaml",
}

# Name keywords for section-less trailing entries, in priority order.
# A keyword matches a dot-separated label that equals it or starts
# with it (fbcdn.net -> fb, igtv.com -> ig). facebook is checked
# before threads, so facebookthreads.net stays with Facebook.
NAME_KEYWORDS = [
    ("facebook", "Facebook.yaml"),
    ("instagram", "Instagram.yaml"),
    ("whatsapp", "WhatsApp.yaml"),
    ("threads", "Threads.yaml"),
    ("messenger", "Messenger.yaml"),
    ("msngr", "Messenger.yaml"),
    ("fb", "Facebook.yaml"),
    ("ig", "Instagram.yaml"),
]

EXACT_NAME = {
    "m.me": "Messenger.yaml",
    "wa.me": "WhatsApp.yaml",
}

TARGETS = ["Facebook.yaml", "Instagram.yaml", "WhatsApp.yaml",
           "Threads.yaml", "Messenger.yaml"]


def classify(name):
    if name in EXACT_NAME:
        return EXACT_NAME[name]
    labels = name.split(".")
    for kw, fname in NAME_KEYWORDS:
        if any(lab == kw or lab.startswith(kw) for lab in labels):
            return fname
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="Meta.yaml")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    exact = {f: set() for f in TARGETS}
    suffix = {f: set() for f in TARGETS}
    seen_sections = set()
    current_key = None
    current_section = None
    warnings = []

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            current_section = s.lstrip("# ").strip()
            seen_sections.add(current_section)
            continue
        if s.startswith("domain_set:"):
            current_key, current_section = "domain_set", None
            continue
        if s.startswith("domain_suffix_set:"):
            current_key, current_section = "domain_suffix_set", None
            continue
        if not s.startswith("- "):
            continue
        value = s[2:].strip()
        if current_key == "domain_set":
            fname = EXACT_FILES.get(value)
            if fname:
                exact[fname].add(value)
            else:
                warnings.append(f"exact host not mapped, stays bucket-only: {value}")
        elif current_key == "domain_suffix_set":
            fname = None
            if current_section in SECTION_FILES:
                fname = SECTION_FILES[current_section]
            elif current_section == "CDN 与基础设施":
                fname = INFRA_FILES.get(value)
                if fname is None:
                    fname = classify(value)
                    if fname is None:
                        warnings.append(f"trailing entry unclassified, stays bucket-only: {value}")
            elif current_section is None:
                # Entry appended after the last section by merge-meta.py.
                fname = classify(value)
                if fname is None:
                    warnings.append(f"trailing entry unclassified, stays bucket-only: {value}")
            # Entries in other sections (Meta AI, Oculus, Workplace,
            # developer) stay bucket-only by design.
            if fname:
                suffix[fname].add(value)

    missing = [s for s in SECTION_FILES if s not in seen_sections]
    if missing:
        print(f"ERROR: Meta.yaml is missing sections: {missing}", file=sys.stderr)
        return 1
    empty = [f for f in TARGETS if not suffix[f]]
    if empty:
        print(f"ERROR: refusing to write empty files: {empty}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for fname in TARGETS:
        parts = []
        if exact[fname]:
            parts.append("domain_set:\n" +
                         "".join(f"  - {d}\n" for d in sorted(exact[fname])))
        parts.append("domain_suffix_set:\n" +
                     "".join(f"  - {d}\n" for d in sorted(suffix[fname])))
        content = "\n".join(parts)
        path = out_dir / fname
        if path.exists() and path.read_text(encoding="utf-8") == content:
            print(f"UNCHANGED {fname}: {len(exact[fname]) + len(suffix[fname])} rules")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"WROTE {fname}: {len(exact[fname])} exact + "
                  f"{len(suffix[fname])} suffix = "
                  f"{len(exact[fname]) + len(suffix[fname])} rules")
    for w in warnings:
        print(f"WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

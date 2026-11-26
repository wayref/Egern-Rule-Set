#!/usr/bin/env python3
"""Merge w8626734 Muse.lsr additions into Meta.yaml (add-only).

Run daily from .github/workflows/sync-rules.yml, after convert.py.
Rules:
  - Only ADD entries that are genuinely new. Never delete, reorder or
    rewrite existing entries; the file's comments and order are kept
    byte-for-byte when nothing is added (no rewrite at all in that case).
  - An upstream entry is skipped when it is already listed, or when an
    existing domain_suffix_set entry already covers it (e.g.
    graph.facebook.com is covered by facebook.com).
  - Upstream removals are ignored: a domain the author drops stays in
    Meta.yaml until a human removes it.
  - Fetch failure / empty / implausibly small upstream: do nothing,
    exit 0, so a bad upstream day never touches the file.
Usage:
  python3 scripts/merge-meta.py [--file Meta.yaml]
                                [--upstream URL | --upstream-file PATH]
"""
import argparse
import os
import re
import sys
import urllib.request

DEFAULT_UPSTREAM = (
    'https://raw.githubusercontent.com/w8626734/muse-rules/main/Muse.lsr'
)
ENTRY_RE = re.compile(r'^(\s*)- (\S+)\s*$')

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode('utf-8', errors='replace')

def parse_meta_yaml(text):
    """Return {key: set(values)} for domain_set / domain_suffix_set."""
    result = {'domain_set': set(), 'domain_suffix_set': set()}
    current = None
    for line in text.splitlines():
        if line.startswith('domain_set:'):
            current = 'domain_set'
            continue
        if line.startswith('domain_suffix_set:'):
            current = 'domain_suffix_set'
            continue
        if re.match(r'^[a-z_]+:', line):
            current = None
            continue
        if current:
            m = ENTRY_RE.match(line)
            if m:
                result[current].add(m.group(2).lower())
    return result

def parse_lsr(text):
    """Parse Loon .lsr into {key: set(values)}; only DOMAIN types."""
    result = {'domain_set': set(), 'domain_suffix_set': set()}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 2:
            continue
        rtype, value = parts[0].upper(), parts[1].lower()
        if rtype == 'DOMAIN-SUFFIX' and value:
            result['domain_suffix_set'].add(value)
        elif rtype == 'DOMAIN' and value:
            result['domain_set'].add(value)
    return result

def is_covered(domain, suffixes):
    """True when `domain` equals or is a subdomain of any suffix."""
    return any(domain == s or domain.endswith('.' + s) for s in suffixes)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default=None,
                        help='Meta.yaml path (default: repo root Meta.yaml)')
    parser.add_argument('--upstream', default=DEFAULT_UPSTREAM)
    parser.add_argument('--upstream-file', default=None,
                        help='Read upstream from a local file instead (testing)')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    meta_path = args.file or os.path.join(repo_root, 'Meta.yaml')
    if not os.path.exists(meta_path):
        print(f'SKIP: {meta_path} not found', file=sys.stderr)
        return 0

    with open(meta_path, 'r', encoding='utf-8') as f:
        original = f.read()
    current = parse_meta_yaml(original)
    current_total = sum(len(v) for v in current.values())
    if current_total == 0:
        print('SKIP: no entries parsed from Meta.yaml', file=sys.stderr)
        return 0

    if args.upstream_file:
        with open(args.upstream_file, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        try:
            text = fetch(args.upstream)
        except Exception as e:
            print(f'SKIP: upstream fetch failed: {e}', file=sys.stderr)
            return 0
    upstream = parse_lsr(text)
    upstream_total = sum(len(v) for v in upstream.values())
    if upstream_total < 10:
        print(f'SKIP: upstream implausibly small ({upstream_total} rules)',
              file=sys.stderr)
        return 0
    print(f'fetched Muse.lsr: {upstream_total} rules '
          f'({len(upstream["domain_suffix_set"])} suffix + '
          f'{len(upstream["domain_set"])} exact)')

    suffixes = current['domain_suffix_set']
    new = {'domain_set': [], 'domain_suffix_set': []}
    for key in ('domain_set', 'domain_suffix_set'):
        for d in sorted(upstream[key]):
            if d in current[key]:
                continue
            if is_covered(d, suffixes):
                continue
            new[key].append(d)
    added = sum(len(v) for v in new.values())
    for key in ('domain_set', 'domain_suffix_set'):
        print(f'  {key}: +{len(new[key])} new '
              f'({len(upstream[key]) - len(new[key])} skipped: '
              f'already present or suffix-covered)')
    if added == 0:
        print(f'UNCHANGED Meta.yaml: {current_total} rules, no new upstream entries')
        return 0

    # Append, preserving every existing line byte-for-byte.
    lines = original.splitlines()
    # Locate block boundaries: last entry line of each key's block.
    blocks = {}
    current_key = None
    for i, line in enumerate(lines):
        if line.startswith('domain_set:'):
            current_key = 'domain_set'
            blocks[current_key] = {'start': i, 'last': None}
            continue
        if line.startswith('domain_suffix_set:'):
            current_key = 'domain_suffix_set'
            blocks[current_key] = {'start': i, 'last': None}
            continue
        if re.match(r'^[a-z_]+:', line):
            current_key = None
            continue
        if current_key and ENTRY_RE.match(line):
            blocks[current_key]['last'] = i
    # Insert from the bottom block up so earlier indices stay valid.
    for key in ('domain_suffix_set', 'domain_set'):
        if not new[key]:
            continue
        last = blocks[key]['last']
        insert = [f'  - {d}' for d in new[key]]
        lines[last + 1:last + 1] = insert
    with open(meta_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'MERGED Meta.yaml: {current_total} -> {current_total + added} '
          f'(+{added} new)')
    return 0

if __name__ == '__main__':
    sys.exit(main())

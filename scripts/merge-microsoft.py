#!/usr/bin/env python3
"""Merge Microsoft bucket additions into Microsoft.yaml (add-only).

Run daily from .github/workflows/sync-rules.yml, after convert.py and
after merge-meta.py. Sources are the repo's own Repcz files (already
refreshed from blackmatrix7 by convert.py) plus LinkedIn.list from
blackmatrix7. Rules:
  - Only ADD genuinely new entries. Never delete, reorder or rewrite
    existing entries; with nothing new the file is left untouched.
  - Domain-only: keyword / user-agent / IP / ASN entries are ignored.
  - Gaming is excluded (Xbox, Minecraft, Mojang, Bethesda, Activision,
    Blizzard, and the same games under other names found 2026-11-26):
    those stay out of this bucket by the owner's decision.
  - Third-party domains that are not Microsoft's (Tenor, Fabric,
    HelpShift, Localytics, Optimizely, UserVoice, HERE) and the
    over-broad Akamai suffix edgesuite.net are excluded as well.
  - Copilot.yaml contributes nothing new on purpose: its genuinely
    Microsoft entries are already covered by the microsoft.com suffix,
    and every entry it has beyond that is a third-party vendor
    (OpenAI, Stripe, Sentry, Segment, Auth0, ...) that must never
    enter this file.
  - linkedin.sc.omtrdc.net is Adobe's tracking host, not LinkedIn's:
    dropped.
  - A failed LinkedIn fetch only skips LinkedIn for that run; the
    local Repcz sources still merge. Total upstream failure leaves
    the file untouched.
Usage:
  python3 scripts/merge-microsoft.py [--file Microsoft.yaml]
"""
import argparse
import os
import re
import sys
import urllib.request

LINKEDIN_URL = (
    'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script'
    '/master/rule/Surge/LinkedIn/LinkedIn.list'
)
# Gaming suffixes: excluded from this bucket by the owner's decision.
# The first 25 came from the original build; the rest were found by the
# 2026-11-26 review (same games under other names: Bethesda, Doom,
# Forza, Gears, Game Pass, PlayFab, ...).
GAMING = {
    'beth.games', 'bethesda.net', 'bethesdagamestudios.com',
    'bethsoft.com', 'doom.com', 'elderscrolls.com',
    'forzamotorsport.net', 'forzaracingchampionship.com', 'forzarc.com',
    'gamepass.com', 'gamesstack.com', 'gameuxmasterguide.com',
    'gears5.com', 'gearspop.com', 'gearstactics.com',
    'microsoftgamestack.com', 'minecraft.net', 'minecraftshop.com',
    'mojang.com', 'ms-studiosmedia.com', 'msgamesresearch.com',
    'msgamestudios.com', 'orithegame.com', 'playfabapi.cn',
    'playfabcn.com', 'renovacionxboxlive.com', 'tellmewhygame.com',
    'xbox.co', 'xbox.com', 'xbox.eu', 'xbox.org', 'xbox360.co',
    'xbox360.com', 'xbox360.eu', 'xbox360.org', 'xboxab.com',
    'xboxgamepass.com', 'xboxgamestudios.com', 'xboxlive.cn',
    'xboxlive.com', 'xboxone.co', 'xboxone.com', 'xboxone.eu',
    'xboxplayanywhere.com', 'xboxservices.com', 'xboxstudios.com',
    'xbx.lv',
}
# Third-party domains that are not Microsoft's, found in the upstream
# base file by the 2026-11-26 review (Tenor is Google's, Fabric is
# Google Firebase's, HERE belongs to car makers, the rest are
# independent vendors); edgesuite.net is also dropped because it is
# Akamai's generic suffix and would match non-Microsoft customers.
THIRD_PARTY = {
    'edgesuite.net', 'fabric.io', 'helpshift.com', 'here.com',
    'here.net', 'heremaps.cn', 'localytics.com', 'optimizely.com',
    'tenor.com', 'uservoice.com',
}
LINKEDIN_DROP = {'linkedin.sc.omtrdc.net'}
ENTRY_RE = re.compile(r'^(\s*)- (\S+)\s*$')

def parse_egern_yaml(text):
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

def parse_list(text):
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
    return any(domain == s or domain.endswith('.' + s) for s in suffixes)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default=None,
                        help='Microsoft.yaml path (default: repo root)')
    parser.add_argument('--linkedin-url', default=LINKEDIN_URL)
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    ms_path = args.file or os.path.join(repo_root, 'Microsoft.yaml')
    if not os.path.exists(ms_path):
        print(f'SKIP: {ms_path} not found', file=sys.stderr)
        return 0
    with open(ms_path, 'r', encoding='utf-8') as f:
        original = f.read()
    current = parse_egern_yaml(original)
    current_total = sum(len(v) for v in current.values())
    if current_total == 0:
        print('SKIP: no entries parsed from Microsoft.yaml', file=sys.stderr)
        return 0

    upstream = {'domain_set': set(), 'domain_suffix_set': set()}
    for name in ('Microsoft', 'OneDrive', 'Teams', 'GitHub'):
        path = os.path.join(repo_root, 'Repcz', name + '.yaml')
        if not os.path.exists(path):
            print(f'  WARN: {path} missing, skipped', file=sys.stderr)
            continue
        with open(path, 'r', encoding='utf-8') as f:
            parsed = parse_egern_yaml(f.read())
        for key in upstream:
            upstream[key] |= parsed[key]
        print(f'  read Repcz/{name}.yaml')
    try:
        req = urllib.request.Request(args.linkedin_url,
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            li = parse_list(resp.read().decode('utf-8', errors='replace'))
        for key in upstream:
            upstream[key] |= li[key]
        print('  fetched LinkedIn.list')
    except Exception as e:
        print(f'  WARN: LinkedIn fetch failed ({e}), continuing without it',
              file=sys.stderr)

    upstream['domain_suffix_set'] -= GAMING
    upstream['domain_suffix_set'] -= THIRD_PARTY
    upstream['domain_set'] -= LINKEDIN_DROP
    upstream_total = sum(len(v) for v in upstream.values())
    if upstream_total < 10:
        print(f'SKIP: upstream implausibly small ({upstream_total} rules)',
              file=sys.stderr)
        return 0

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
              f'({len(upstream[key]) - len(new[key])} skipped: already '
              f'present, suffix-covered or excluded)')
    if added == 0:
        print(f'UNCHANGED Microsoft.yaml: {current_total} rules, '
              f'no new upstream entries')
        return 0

    lines = original.splitlines()
    blocks = {}
    current_key = None
    for i, line in enumerate(lines):
        if line.startswith('domain_set:'):
            current_key = 'domain_set'
            blocks[current_key] = {'last': None}
            continue
        if line.startswith('domain_suffix_set:'):
            current_key = 'domain_suffix_set'
            blocks[current_key] = {'last': None}
            continue
        if re.match(r'^[a-z_]+:', line):
            current_key = None
            continue
        if current_key and ENTRY_RE.match(line):
            blocks[current_key]['last'] = i
    for key in ('domain_suffix_set', 'domain_set'):
        if not new[key]:
            continue
        last = blocks[key]['last']
        insert = [f'  - {d}' for d in new[key]]
        lines[last + 1:last + 1] = insert
    with open(ms_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'MERGED Microsoft.yaml: {current_total} -> '
          f'{current_total + added} (+{added} new)')
    return 0

if __name__ == '__main__':
    sys.exit(main())

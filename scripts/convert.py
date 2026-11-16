#!/usr/bin/env python3
"""
Convert Surge .list rules from multiple upstreams into Egern YAML format.
Merges rules from all listed upstreams for each rule set, deduplicates,
and outputs Egern-native YAML.

Usage:
    python3 convert.py [--output-dir DIR]

Upstreams:
    - blackmatrix7/ios_rule_script (Surge .list) — primary source
    - mihoyo-typ/KeleeOne (Loon .lsr, Surge-compatible) — Telegram only
    - hin0ka (Egern YAML, mirrored as-is, not converted)
"""

import argparse
import os
import re
import sys
import urllib.request

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Surge type -> Egern YAML key
TYPE_MAP = {
    'DOMAIN': 'domain_set',
    'DOMAIN-SUFFIX': 'domain_suffix_set',
    'DOMAIN-KEYWORD': 'domain_keyword_set',
    'DOMAIN-WILDCARD': 'domain_wildcard_set',
    'IP-CIDR': 'ip_cidr_set',
    'IP-CIDR6': 'ip_cidr6_set',
    'GEOIP': 'geoip_set',
    'IP-ASN': 'asn_set',
    'URL-REGEX': 'url_regex_set',
    'USER-AGENT': 'user_agent_set',
    'DEST-PORT': 'dest_port_set',
}

# Types that need YAML quotes (contain special chars)
QUOTE_TYPES = {'IP-ASN', 'URL-REGEX', 'USER-AGENT', 'DEST-PORT'}

# Types Egern rule_set does not support — drop them
DROP_TYPES = {'PROCESS-NAME', 'AND', 'OR', 'NOT', 'SRC-IP', 'SRC-PORT'}

# Rule definitions: output file -> list of upstream URLs
# For China, IP rules are filtered out (drop_ip=True)
RULES = {
    'Repcz/Google.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Google/Google.list',
    ],
    'Repcz/Twitter.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Twitter/Twitter.list',
    ],
    'Repcz/YouTube.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/YouTube/YouTube.list',
    ],
    'Repcz/Telegram.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Telegram/Telegram.list',
        'https://raw.githubusercontent.com/mihoyo-typ/KeleeOne/Loon/Rule/Lsr/Telegram.lsr',
    ],
    'Repcz/TikTok.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/TikTok/TikTok.list',
    ],
    'Repcz/Instagram.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Instagram/Instagram.list',
    ],
    'Repcz/FaceBook.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Facebook/Facebook.list',
    ],
    'Repcz/Threads.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Threads/Threads.list',
    ],
    'Repcz/GitHub.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/GitHub/GitHub.list',
    ],
    'Repcz/China.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaMax/ChinaMax_Domain.list',
    ],
    # --- Streaming ---
    'Repcz/Netflix.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Netflix/Netflix.list',
    ],
    'Repcz/Disney.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Disney/Disney.list',
    ],
    'Repcz/HBO.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/HBO/HBO.list',
    ],
    'Repcz/Spotify.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Spotify/Spotify.list',
    ],
    'Repcz/PrimeVideo.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/PrimeVideo/PrimeVideo.list',
    ],
    'Repcz/Hulu.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Hulu/Hulu.list',
    ],
    'Repcz/ParamountPlus.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ParamountPlus/ParamountPlus.list',
    ],
    'Repcz/Twitch.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Twitch/Twitch.list',
    ],
    'Repcz/YouTubeMusic.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/YouTubeMusic/YouTubeMusic.list',
    ],
    'Repcz/AppleTV.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/AppleTV/AppleTV.list',
    ],
    # --- Social ---
    'Repcz/Whatsapp.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Whatsapp/Whatsapp.list',
    ],
    'Repcz/Discord.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Discord/Discord.list',
    ],
    'Repcz/Reddit.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Reddit/Reddit.list',
    ],
    'Repcz/Pinterest.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Pinterest/Pinterest.list',
    ],
    'Repcz/Line.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Line/Line.list',
    ],
    # --- Games ---
    'Repcz/Steam.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Steam/Steam.list',
    ],
    'Repcz/PlayStation.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/PlayStation/PlayStation.list',
    ],
    'Repcz/Xbox.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Xbox/Xbox.list',
    ],
    'Repcz/Nintendo.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Nintendo/Nintendo.list',
    ],
    'Repcz/Blizzard.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Blizzard/Blizzard.list',
    ],
    'Repcz/Epic.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Epic/Epic.list',
    ],
    'Repcz/Riot.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Riot/Riot.list',
    ],
    # --- Microsoft / Productivity ---
    'Repcz/Microsoft.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Microsoft/Microsoft.list',
    ],
    'Repcz/OneDrive.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/OneDrive/OneDrive.list',
    ],
    'Repcz/Teams.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Teams/Teams.list',
    ],
    'Repcz/Dropbox.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Dropbox/Dropbox.list',
    ],
    'Repcz/Notion.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Notion/Notion.list',
    ],
    'Repcz/Slack.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Slack/Slack.list',
    ],
    # --- AI (individual services; hin0ka AI.yaml is the combined one) ---
    'Repcz/OpenAI.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/OpenAI/OpenAI.list',
    ],
    'Repcz/Claude.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Claude/Claude.list',
    ],
    'Repcz/Gemini.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Gemini/Gemini.list',
    ],
    'Repcz/Copilot.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Copilot/Copilot.list',
    ],
    # --- Other ---
    'Repcz/Amazon.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Amazon/Amazon.list',
    ],
    'Repcz/eBay.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/eBay/eBay.list',
    ],
    'Repcz/TestFlight.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/TestFlight/TestFlight.list',
    ],
    'Repcz/PayPal.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/PayPal/PayPal.list',
    ],
    'Repcz/Cloudflare.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Cloudflare/Cloudflare.list',
    ],
    'Repcz/Docker.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Docker/Docker.list',
    ],
    'Repcz/GitLab.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/GitLab/GitLab.list',
    ],
    'Repcz/Speedtest.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Speedtest/Speedtest.list',
    ],
    # --- Domestic Services (China) - Chinese names ---
    'Repcz/腾讯.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/WeChat/WeChat.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Tencent/Tencent.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/TencentVideo/TencentVideo.list',
    ],
    'Repcz/京东.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/JingDong/JingDong.list',
    ],
    'Repcz/拼多多.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Pinduoduo/Pinduoduo.list',
    ],
    'Repcz/百度.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Baidu/Baidu.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/BaiDuTieBa/BaiDuTieBa.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/iQIYI/iQIYI.list',
    ],
    'Repcz/哔哩哔哩.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/BiliBili/BiliBili.list',
    ],
    'Repcz/字节跳动.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ByteDance/ByteDance.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/DouYin/DouYin.list',
    ],
    'Repcz/国产手机.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/XiaoMi/XiaoMi.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Huawei/Huawei.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Vivo/Vivo.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/OPPO/OPPO.list',
    ],
    'Repcz/阿里巴巴.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Alibaba/Alibaba.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/AliPay/AliPay.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/DingTalk/DingTalk.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/GaoDe/GaoDe.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Youku/Youku.list',
    ],
    'Repcz/网易.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/NetEase/NetEase.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/NetEaseMusic/NetEaseMusic.list',
    ],
    'Repcz/美团.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/MeiTuan/MeiTuan.list',
    ],
    'Repcz/滴滴.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/DiDi/DiDi.list',
    ],
    'Repcz/快手.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/KuaiShou/KuaiShou.list',
    ],
    'Repcz/小红书.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/XiaoHongShu/XiaoHongShu.list',
    ],
    'Repcz/知乎.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Zhihu/Zhihu.list',
    ],
    'Repcz/豆瓣.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/DouBan/DouBan.list',
    ],
    'Repcz/新浪.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Sina/Sina.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Weibo/Weibo.list',
    ],
    'Repcz/搜狐.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Sohu/Sohu.list',
    ],
    'Repcz/三大运营商.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaMobile/ChinaMobile.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaTelecom/ChinaTelecom.list',
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaUnicom/ChinaUnicom.list',
    ],
    'Repcz/中国国航.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/AirChina/AirChina.list',
    ],
    'Repcz/中国新闻.yaml': [
        'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/ChinaNews/ChinaNews.list',
    ],
}

# Rules that drop IP-type entries (IP-CIDR, IP-CIDR6, GEOIP)
DROP_IP_RULES = {'Repcz/China.yaml'}

# --- User-managed files: merge upstream additions WITHOUT overwriting ---
# For these files, the sync READS the current file, fetches upstream,
# filters out junk ("polluted" entries), and ADDS only genuinely new
# entries. User's own entries are never removed.
# NOTE: Apple.yaml is NOT here — its only upstream (MagicRule) is too
# polluted to filter reliably (5993 entries, mostly squatter/promo
# domains), and Loyalsoldier's Apple list adds 0 new entries (fully
# covered already). Apple.yaml stays fully user-managed.
# Format: output path -> {'upstreams': [...], 'filter': 'emby'|None}
MERGE_RULES = {
    'Emby.yaml': {
        'upstreams': [
            'https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Surge/Emby/Emby.list',
        ],
        'filter': 'emby',
    },
}


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode('utf-8', errors='replace')


def parse_surge_list(text):
    """Parse Surge .list / Loon .lsr / DOMAIN-SET text into {egern_key: set(values)}."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # DOMAIN-SET format: bare domain, leading '.' means suffix match
        if ',' not in line:
            if line.startswith('.'):
                result.setdefault('domain_suffix_set', set()).add(line[1:].lower())
            else:
                result.setdefault('domain_set', set()).add(line.lower())
            continue
        parts = [p.strip() for p in line.split(',')]
        rtype = parts[0].upper()
        if rtype in DROP_TYPES or len(parts) < 2:
            continue
        key = TYPE_MAP.get(rtype)
        if not key:
            continue
        value = parts[1]
        # Normalize: lowercase domains, strip trailing dot
        if key in ('domain_set', 'domain_suffix_set', 'domain_keyword_set', 'domain_wildcard_set'):
            value = value.lower().rstrip('.')
        # IP-ASN: ensure AS prefix
        if rtype == 'IP-ASN' and not value.upper().startswith('AS'):
            value = 'AS' + value
        result.setdefault(key, set()).add(value)
    return result


def merge_parsed(parsed_list):
    merged = {}
    for parsed in parsed_list:
        for key, values in parsed.items():
            merged.setdefault(key, set()).update(values)
    return merged


def to_egern_yaml(name, merged, drop_ip=False):
    """Render merged rules as Egern YAML text."""
    lines = []
    # Fixed key order (match Repcz output order)
    key_order = ['domain_set', 'domain_suffix_set', 'domain_keyword_set',
                 'domain_wildcard_set', 'ip_cidr_set', 'ip_cidr6_set',
                 'geoip_set', 'asn_set', 'url_regex_set', 'user_agent_set',
                 'dest_port_set']
    for key in key_order:
        if drop_ip and key in ('ip_cidr_set', 'ip_cidr6_set', 'geoip_set'):
            continue
        values = sorted(merged.get(key, set()))
        if not values:
            continue
        lines.append(f'{key}:')
        # Quote types that contain YAML special chars
        quote_all = key in ('asn_set', 'url_regex_set', 'user_agent_set', 'dest_port_set')
        for v in values:
            # Quote if the whole key needs it, or the value starts with a
            # YAML special char (*, &, !, |, >, ', ", %, @, `) or contains ': '
            needs_quote = quote_all or v.startswith(('*', '&', '!', '|', '>', "'", '"', '%', '@', '`')) or ': ' in v or v.endswith(':')
            if needs_quote:
                escaped = v.replace('\\', '\\\\').replace('"', '\\"')
                lines.append(f'  - "{escaped}"')
            else:
                lines.append(f'  - {v}')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def parse_egern_yaml(text):
    """Parse an Egern YAML rule file into {egern_key: set(values)}."""
    if not HAS_YAML:
        return {}
    d = yaml.safe_load(text)
    if not isinstance(d, dict):
        return {}
    result = {}
    for key, values in d.items():
        if isinstance(values, list):
            result[key] = set(str(v) for v in values)
    return result


def parse_clash_payload(text):
    """Parse a Clash payload YAML (Loyalsoldier format) into sets."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- '") and not line.startswith('- "'):
            continue
        # Strip "- '" prefix and "'" suffix
        entry = line[3:].strip().strip("'\"")
        if entry.startswith('+.'):
            result.setdefault('domain_suffix_set', set()).add(entry[2:].lower())
        elif entry.startswith('*.'):
            result.setdefault('domain_wildcard_set', set()).add(entry.lower())
        else:
            result.setdefault('domain_set', set()).add(entry.lower())
    return result


def is_emby_related(domain):
    """Check if a domain is Emby-related.

    blackmatrix7's Emby list is already curated (all entries are Emby
    servers or related services), so accept everything from it.
    """
    return True


def filter_parsed(parsed, filter_name):
    """Remove junk entries from parsed upstream data."""
    if filter_name == 'emby':
        check = is_emby_related
    else:
        return parsed
    filtered = {}
    for key, values in parsed.items():
        # Only filter domain-type keys; keep IP/ASN/etc. as-is
        if key in ('domain_set', 'domain_suffix_set', 'domain_keyword_set',
                   'domain_wildcard_set'):
            kept = set(v for v in values if check(v))
            if kept:
                filtered[key] = kept
        else:
            filtered[key] = set(values)
    return filtered


def merge_user_file(output_path, spec, output_dir):
    """Merge upstream additions into a user-managed file.

    Reads the current file, fetches + filters upstream, unions the sets,
    writes back. User entries are never removed. Returns (added, total).
    """
    full_path = os.path.join(output_dir, output_path)
    current = {}
    if os.path.exists(full_path):
        with open(full_path, 'r', encoding='utf-8') as f:
            current = parse_egern_yaml(f.read())
    current_total = sum(len(v) for v in current.values())

    upstream_parsed = []
    for url in spec['upstreams']:
        try:
            text = fetch(url)
            if url.endswith('.yaml') or url.endswith('.yml'):
                parsed = parse_egern_yaml(text)
            elif 'clash-rules' in url or 'payload' in text[:200]:
                parsed = parse_clash_payload(text)
            else:
                parsed = parse_surge_list(text)
            n = sum(len(v) for v in parsed.values())
            print(f'  fetched {url.split("/")[-1]}: {n} rules (raw)')
            filtered = filter_parsed(parsed, spec.get('filter'))
            fn = sum(len(v) for v in filtered.values())
            print(f'  filtered to {fn} rules (dropped {n - fn} junk)')
            upstream_parsed.append(filtered)
        except Exception as e:
            print(f'  FAILED {url}: {e}', file=sys.stderr)

    if not upstream_parsed:
        print(f'  SKIP {output_path}: no upstream fetched', file=sys.stderr)
        return (0, current_total)

    merged = {}
    for key in set(current) | set().union(*[set(p) for p in upstream_parsed]):
        vals = set(current.get(key, set()))
        for p in upstream_parsed:
            vals |= set(p.get(key, set()))
        if vals:
            merged[key] = vals

    new_total = sum(len(v) for v in merged.values())
    added = new_total - current_total
    name = os.path.splitext(os.path.basename(output_path))[0]
    yaml_text = to_egern_yaml(name, merged)
    os.makedirs(os.path.dirname(full_path) or '.', exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(yaml_text)
    print(f'  MERGED {output_path}: {current_total} -> {new_total} (+{added} new)')
    return (added, new_total)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='.')
    args = parser.parse_args()

    for output_path, urls in RULES.items():
        name = os.path.splitext(os.path.basename(output_path))[0]
        parsed_list = []
        for url in urls:
            try:
                text = fetch(url)
                parsed = parse_surge_list(text)
                n = sum(len(v) for v in parsed.values())
                print(f'  fetched {url.split("/")[-1]}: {n} rules')
                parsed_list.append(parsed)
            except Exception as e:
                print(f'  FAILED {url}: {e}', file=sys.stderr)
        if not parsed_list:
            print(f'  SKIP {output_path}: no sources fetched', file=sys.stderr)
            continue
        merged = merge_parsed(parsed_list)
        drop_ip = output_path in DROP_IP_RULES
        yaml_text = to_egern_yaml(name, merged, drop_ip=drop_ip)
        full_path = os.path.join(args.output_dir, output_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(yaml_text)
        total = sum(len(v) for v in merged.values())
        print(f'  WROTE {output_path}: {total} rules (from {len(urls)} upstream(s))')

    # User-managed files: merge upstream additions (never overwrite)
    print('--- Merging user-managed files ---')
    for output_path, spec in MERGE_RULES.items():
        print(f'  {output_path}:')
        merge_user_file(output_path, spec, args.output_dir)


if __name__ == '__main__':
    main()

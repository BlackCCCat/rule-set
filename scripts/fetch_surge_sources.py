#!/usr/bin/env python3
"""Build the workflow's Surge-style inputs from their published sources."""

import ipaddress
import json
import re
import subprocess
import sys
from functools import cache
from pathlib import Path


DLC_URL = "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/"
OUTPUTS = {"surge": "download/surge", "mail": "download/special/mail-sources"}
RULE_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD", "DOMAIN-REGEX",
    "IP-CIDR", "IP-CIDR6", "IP-ASN", "PROCESS-NAME", "USER-AGENT", "URL-REGEX",
}
ALIASES = {
    "HOST": "DOMAIN", "HOST-SUFFIX": "DOMAIN-SUFFIX",
    "HOST-KEYWORD": "DOMAIN-KEYWORD", "HOST-WILDCARD": "DOMAIN-WILDCARD",
    "IP6-CIDR": "IP-CIDR6",
}
DLC_TYPES = {
    "domain": "DOMAIN-SUFFIX", "full": "DOMAIN",
    "keyword": "DOMAIN-KEYWORD", "regexp": "DOMAIN-REGEX",
}
SKK_MARKER = "7h15.ru1353t.1s.m4d3.by.5ukk4w.skk.moe"


def cidr_rule(value):
    network = ipaddress.ip_network(value, strict=False)
    kind = "IP-CIDR6" if network.version == 6 else "IP-CIDR"
    return f"{kind},{network},no-resolve"


@cache
def fetch_list(url):
    content = subprocess.check_output(
        ["curl", "-fsSL", "--retry", "2", "--max-time", "60", url]
    ).decode("utf-8-sig")
    yaml_payload = content.lstrip().startswith("payload:")
    rules = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        line = re.split(r"\s+(?:#|;|//)", line, maxsplit=1)[0].rstrip()
        if yaml_payload:
            if line == "payload:":
                continue
            if not line.startswith("- "):
                raise ValueError(f"unexpected YAML payload entry: {line!r}")
            line = line[2:].strip().strip("'\042")

        kind, sep, rest = line.partition(",")
        if not sep:
            if "/" in line:
                rules.append(cidr_rule(line))
                continue
            value = line.removeprefix("+.").removeprefix(".")
            if not re.fullmatch(r"[\w.*-]+", value):
                raise ValueError(f"invalid domain entry: {line!r}")
            kind = "DOMAIN-WILDCARD" if "*" in value else (
                "DOMAIN-SUFFIX" if value != line else "DOMAIN"
            )
        else:
            kind = kind.strip().upper()
            kind = ALIASES.get(kind, kind)
            if kind not in RULE_TYPES:
                raise ValueError(f"unsupported rule type: {kind!r}")
            # Keep regex commas. Other trailing fields may be QX policy names.
            value = (rest if kind in {"DOMAIN-REGEX", "URL-REGEX"} else rest.split(",")[0]).strip()
            if kind in {"IP-CIDR", "IP-CIDR6"}:
                rules.append(cidr_rule(value))
                continue
            if not value:
                raise ValueError(f"empty {kind} entry")
        if value != SKK_MARKER or not url.startswith("https://ruleset.skk.moe/"):
            rules.append(f"{kind},{value}")
    if not rules:
        raise ValueError("no rules found")
    return rules


@cache
def read_dlc(directory, name, ancestors=()):
    if name in ancestors:
        raise ValueError(f"recursive v2fly include: {' -> '.join((*ancestors, name))}")
    if not re.fullmatch(r"[\w.!-]+", name):
        raise ValueError(f"invalid v2fly list name: {name!r}")
    sources = {DLC_URL + name}
    rules = []
    for line in (directory / name).read_text(encoding="utf-8").splitlines():
        fields = line.partition("#")[0].split()
        if not fields:
            continue
        entry, *attributes = fields
        kind, sep, value = entry.partition(":")
        if not sep:
            kind, value = "domain", entry
        if kind == "include":
            included, links = read_dlc(directory, value, (*ancestors, name))
            sources.update(links)
            rules.extend(
                (rule, tags) for rule, tags in included
                if all(
                    attr[2:] not in tags if attr.startswith("@-") else attr[1:] in tags
                    for attr in attributes
                )
            )
        else:
            rules.append((f"{DLC_TYPES[kind]},{value}", {attr[1:] for attr in attributes}))
    return rules, sources


def main():
    sources = json.loads(Path(__file__).with_name("surge_sources.json").read_text(encoding="utf-8"))
    dlc_directory = Path(sys.argv[1])
    for group, rule_sets in sources.items():
        output = Path(OUTPUTS[group])
        output.mkdir(parents=True, exist_ok=True)
        for name, upstreams in rule_sets.items():
            rules, links = {}, set()
            for upstream in upstreams:
                try:
                    if upstream.startswith("v2fly:"):
                        entries, files = read_dlc(dlc_directory, upstream.removeprefix("v2fly:"))
                        rules.update(dict.fromkeys(rule for rule, _ in entries))
                        links.update(files)
                    else:
                        rules.update(dict.fromkeys(fetch_list(upstream)))
                        links.add(upstream)
                except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                    raise SystemExit(f"{name}: {upstream}: {error}") from error
            if not rules:
                raise SystemExit(f"{name}: no rules found")
            (output / f"{name}.list").write_text("\n".join(rules) + "\n", encoding="utf-8")
            (output / f"{name}.list.sources").write_text(
                "\n".join(sorted(links)) + "\n", encoding="utf-8"
            )
            print(f"{name}: {len(rules)} rules from {len(links)} source files", flush=True)


if __name__ == "__main__":
    main()

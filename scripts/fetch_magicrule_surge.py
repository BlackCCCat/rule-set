#!/usr/bin/env python3
"""Download a named Surge rule from MagicRule's generated artifact index."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path


INDEX_URL = "https://magicrule.pages.dev/data/index/Surge.json"
MAGICRULE_REPOSITORY = "https://github.com/magical404/MagicRule"
INDEX_CACHE = Path(os.environ.get("MAGICRULE_INDEX_CACHE", "/tmp/magicrule-surge-index.json"))

# MagicRule keeps the source names where they are meaningful, but a few names
# used by this workflow have a different spelling or a newer equivalent.
ALIASES = {
    "Abema": "AbemaTV",
    "Coolapk": "CoolAPK",
    "Crypto": "Cryptocurrency",
    "GameDownloadCN": "ChinaGame",
    "Proxy": "Global",
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "rule-set-builder"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "rule-set-builder"})
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sources-output", required=True, type=Path)
    args = parser.parse_args()

    requested_name = args.name
    actual_name = ALIASES.get(requested_name, requested_name)
    if INDEX_CACHE.is_file():
        index = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
    else:
        index = fetch_json(INDEX_URL)
        INDEX_CACHE.write_text(json.dumps(index), encoding="utf-8")
    rule = next((item for item in index.get("rules", []) if item.get("name") == actual_name), None)
    if rule is None:
        raise SystemExit(f"MagicRule Surge rule not found: {requested_name} (resolved as {actual_name})")

    manifest = fetch_json(rule["manifest"])
    artifacts = manifest.get("artifacts", [])
    artifact = next(
        (
            item
            for item in artifacts
            if item.get("role") == "full" and item.get("ext") == "list" and not item.get("binary")
        ),
        None,
    )
    if artifact is None:
        raise SystemExit(f"MagicRule Surge rule has no text artifact: {requested_name}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.sources_output.parent.mkdir(parents=True, exist_ok=True)
    download(artifact["url"], args.output)

    providers = rule.get("providers", [])
    sources = [MAGICRULE_REPOSITORY, INDEX_URL, rule["manifest"], artifact["url"], *providers]
    args.sources_output.write_text("\n".join(dict.fromkeys(sources)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Mint the Zenodo record for cad-silent-failure-bench v1.0 through the REST API. Stdlib only.

Reads ZENODO_TOKEN from the environment or from ~/Research/.env. Creates a new deposition,
uploads the zip, sets the metadata below, and publishes (unless --dry-run, which stops after
the metadata step and leaves an unpublished draft you can inspect at zenodo.org/me/uploads).
Prints the version DOI, the concept DOI, and the record URL.

Usage:
  python3 scripts/zenodo_publish.py /path/to/cad-silent-failure-bench-v1.0.zip [--dry-run]
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request

API = "https://zenodo.org/api"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

DESCRIPTION = """<p>Benchmark, harness, and full attempt corpus for the paper <em>Done Is Not Correct: Measuring Silent Failures and Self-Verification Calibration When LLM Agents Take CAD Actions</em> (Rodrigues, Rodrigues, Reddy G, 2026). Suite v1.0 is the frozen version every number in the paper is computed from.</p>
<p><strong>Contents.</strong> 13 natural-language mechanical specification tasks in three tiers with 122 machine-checkable requirements and published tolerance bands; 13 reference build123d solutions; the grader, kernel executor, property extractor, and single-shot / tool-use / multi-agent harnesses; every graded attempt (519 full-population attempts, the 468-attempt primary population, 78 legacy-contract ablation attempts, 60 pilot attempts) as JSON records with final code, measured properties, verdicts under the original and hardened oracle, completion claim, stated confidence, tokens, and context-divergence scores; multi-turn transcripts for the 234 fixed-protocol tool-use and ablation attempts; the blind expert scoring sheet; the analysis scripts that reproduce every statistic, table, and figure (including the tolerance-band sensitivity sweep); the pre-registered study plan; a static 3D viewer of every attempt against its reference; and the manuscript with its datasheet supplement.</p>
<p><strong>Headline.</strong> A silent failure is a valid, renderable solid, delivered with an explicit completion claim, that fails at least one semantic check. Across four vendors (n = 156 per condition), single-shot agents were silently wrong on 14.1% of attempts; a tool-use loop that enforces measure-then-claim cut that to 3.2%; hardening the oracle flipped 18 of 519 verdicts from pass to fail and none in reverse, so these rates are lower bounds; scaling every tolerance band from x0.25 to x4 leaves the contrast intact.</p>
<p><strong>Licences.</strong> Code MIT; tasks, reference solutions, records, transcripts, and viewer assets CC BY 4.0. Corrections are logged in ERRATA.md; later suite versions are separate tagged releases. Contact: carson@celabe.com.</p>"""

METADATA = {
    "metadata": {
        "upload_type": "software",
        "publication_date": "2026-09-03",
        "title": "cad-silent-failure-bench v1.0: benchmark, harness, and attempt corpus for \"Done Is Not Correct: Measuring Silent Failures and Self-Verification Calibration When LLM Agents Take CAD Actions\"",
        "creators": [
            {"name": "Rodrigues, Carson", "affiliation": "Celabe", "orcid": "0009-0001-7195-6742"},
            {"name": "Rodrigues, Clive", "affiliation": "Hochschule Coburg, University of Applied Sciences"},
            {"name": "Reddy G, Aravind", "affiliation": "Independent"},
        ],
        "description": DESCRIPTION,
        "access_right": "open",
        "license": "cc-by-4.0",
        "version": "1.0",
        "language": "eng",
        "keywords": ["agentic benchmarks", "silent failure", "LLM agents", "computer-aided design",
                     "calibration", "evaluation methodology", "grader audit", "text-to-CAD", "build123d"],
        "related_identifiers": [
            {"identifier": "https://github.com/rodriguescarson/cad-silent-failure-bench", "relation": "isSupplementTo", "resource_type": "software"},
            {"identifier": "https://github.com/rodriguescarson/cad-silent-failure-bench/tree/v1.0", "relation": "isIdenticalTo", "resource_type": "software"},
        ],
    }
}


def token() -> str:
    t = os.environ.get("ZENODO_TOKEN")
    if not t:
        env = pathlib.Path.home() / "Research" / ".env"
        for line in env.read_text().splitlines():
            if line.startswith("ZENODO_TOKEN="):
                t = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not t:
        sys.exit("ZENODO_TOKEN not found")
    return t


def call(method: str, url: str, tok: str, data: bytes | None = None, ctype: str = "application/json"):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok, "User-Agent": UA,
                                          "Content-Type": ctype, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        sys.exit(f"{method} {url} -> HTTP {e.code}: {body[:400]}")


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    zip_path = pathlib.Path(sys.argv[1])
    dry = "--dry-run" in sys.argv
    tok = token()
    _, dep = call("POST", f"{API}/deposit/depositions", tok, b"{}")
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    print("deposition", dep_id, "created")
    data = zip_path.read_bytes()
    st, _ = call("PUT", f"{bucket}/{zip_path.name}", tok, data, ctype="application/octet-stream")
    print("uploaded", zip_path.name, len(data), "bytes -> HTTP", st)
    call("PUT", f"{API}/deposit/depositions/{dep_id}", tok, json.dumps(METADATA).encode())
    print("metadata set")
    if dry:
        print(f"dry run: draft left unpublished at https://zenodo.org/uploads/{dep_id}")
        return 0
    _, pub = call("POST", f"{API}/deposit/depositions/{dep_id}/actions/publish", tok, b"")
    print("PUBLISHED")
    print("version DOI :", pub.get("doi"))
    print("concept DOI :", pub.get("conceptdoi"))
    print("record URL  :", pub.get("links", {}).get("record_html") or pub.get("links", {}).get("html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

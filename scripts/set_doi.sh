#!/usr/bin/env bash
# Fill the Zenodo DOI into the master and the supplement, rebuild every PDF, re-stage the release.
# Usage: scripts/set_doi.sh 10.5281/zenodo.NNNNNNNN
set -e
DOI="$1"; [ -n "$DOI" ] || { echo "usage: $0 10.5281/zenodo.NNNNNNNN"; exit 1; }
cd "$(dirname "$0")/.."
python3 - "$DOI" <<'PY'
import re,sys,pathlib
doi=sys.argv[1]
for p in ["draft-tmlr/paper.tex","draft-dmlr/supplement.tex"]:
    f=pathlib.Path(p); t=f.read_text()
    t2=re.sub(r"\\newcommand\{\\artifactdoi\}\{[^}]*\}", "\\\\newcommand{\\\\artifactdoi}{"+doi+"}", t)
    assert t2!=t or doi in t, p
    f.write_text(t2); print("set", p)
PY
cp references/verified.bib draft-tmlr/verified.bib
(cd draft-tmlr && tectonic paper.tex >/dev/null 2>&1 && grep -E "Output written" paper.log | tail -1)
(cd draft-dmlr && ./build.sh 2>&1 | tail -1 && tectonic supplement.tex >/dev/null 2>&1 && echo "supplement rebuilt")
grep -c "UNSET" draft-dmlr/paper.tex draft-dmlr/supplement.tex || true
./scripts/stage_release.sh
echo "now: cd ~/projects/cad-silent-failure-bench && git add -A && git commit -m 'v1.0: paper PDFs with Zenodo DOI $DOI' && git push"

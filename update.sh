#!/bin/bash
# Refresh rain + agriculture data, rerun the analysis, regenerate figures.
# Guarded fetches: a failed or truncated download never clobbers good data.
# FAOSTAT bulk (~50 MB) is only re-downloaded when the local copy is >90 days
# old; CCKP + WDI are small and refresh every run.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../venv/bin/python"
[ -x "$PY" ] || PY=python3
export MPLBACKEND=Agg

echo "==> israel-rain-agriculture refresh $(date '+%Y-%m-%d %H:%M')"
"$PY" "$HERE/fetch_data.py" || exit 1
"$PY" "$HERE/analyze.py" > "$HERE/results.txt" 2>&1 || exit 1
"$PY" "$HERE/make_plots.py" || exit 1
tail -6 "$HERE/results.txt"
echo "==> done"

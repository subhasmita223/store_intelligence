#!/usr/bin/env bash
# T-14: Process all CCTV clips for one store and post events to the API.
#
# Usage (host):
#   bash pipeline/run.sh <clips_dir> <api_base_url> [--date YYYY-MM-DD]
#
# Usage (Docker):
#   docker compose run --rm pipeline ./data/store1 http://api:8000
#
# Re-runnable: the ingest endpoint is idempotent (duplicate events are skipped).
# Failure on one camera does not abort processing of the others.

set -euo pipefail

CLIPS_DIR="${1:?Usage: run.sh <clips_dir> <api_base_url> [--date YYYY-MM-DD]}"
API_URL="${2:?Usage: run.sh <clips_dir> <api_base_url> [--date YYYY-MM-DD]}"
CLIP_DATE="${3:-$(date +%Y-%m-%d)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Add repo root to PYTHONPATH so 'from app.models import ...' works outside Docker
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "=============================================="
echo " Store Intelligence Pipeline"
echo " Store dir : $CLIPS_DIR"
echo " API URL   : $API_URL"
echo " Clip date : $CLIP_DATE"
echo "=============================================="

python "$SCRIPT_DIR/process_store.py" \
    "$CLIPS_DIR" \
    "$API_URL" \
    --date "$CLIP_DATE"

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "[run.sh] Pipeline finished with errors (exit $EXIT_CODE)" >&2
fi
exit $EXIT_CODE

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi
case "${1:-verify}" in
 verify) "$PYTHON" "$ROOT/source/VGA显示部分/verify_package.py"; "$PYTHON" "$ROOT/serve/verify_upload.py" ;;
 ui) exec "$PYTHON" "$ROOT/source/PC/ui/launch_scope.py" ;;
 *) echo 'Usage: bash run.sh [verify|ui]' >&2; exit 2 ;;
esac

#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_path="${1:-${project_dir}/BookPilot-Production-Complete.zip}"

cd "$project_dir"
python - "$output_path" <<'PY'
from pathlib import Path
import sys

output = Path(sys.argv[1]).resolve()
if output.exists():
    output.unlink()
PY

zip -q -r "$output_path" \
  .env.example .github .gitignore ALL_BUSINESS_EDITION_NOTES.md \
  BOUTIQUE_UPGRADE_NOTES.md MASTER_SETUP_GUIDE.md MASTER_VERSION_MANIFEST.md \
  MOBILE_SHOP_EDITION_NOTES.md README.md apps build.sh config conftest.py \
  docker-compose.yml docs manage.py pytest.ini render.yaml requirements \
  scripts static templates tests \
  -x '*/__pycache__/*' '*.pyc' '.pytest_cache/*' 'media/*' 'staticfiles/*' \
     '.venv/*' 'venv/*' '*.zip'

python - "$output_path" <<'PY'
import sys
import zipfile

path = sys.argv[1]
blocked = (".venv/", "venv/", "__pycache__/", ".pytest_cache/", "media/", "staticfiles/")
with zipfile.ZipFile(path) as archive:
    bad = [name for name in archive.namelist() if any(part in name for part in blocked)]
    if bad:
        raise SystemExit(f"Release contains blocked files: {bad[:5]}")
print(path)
PY

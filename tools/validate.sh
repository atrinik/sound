#!/usr/bin/env bash

set -euo pipefail

python3 tools/sound_release.py validate
python3 -m unittest discover -s tests -v
python3 -m compileall -q tools tests
bash -n tools/build-release-assets.sh tools/package-release.sh tools/validate.sh
git diff --check

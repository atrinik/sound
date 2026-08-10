#!/usr/bin/env bash

set -euo pipefail

python3 tools/sound_release.py validate
quality_review_count=$(python3 -c 'import json; print(len(json.load(open("manifests/vorbis-quality-reviews.json", encoding="utf-8"))["reviews"]))')
if (( quality_review_count > 0 )); then
  if [[ ${ATRINIK_PINNED_TOOLCHAIN:-} == 1 ]]; then
    python3 tools/sound_release.py validate-quality-outputs
  else
    docker run --rm --platform linux/amd64 \
      --user "$(id -u):$(id -g)" \
      --volume "$PWD:/workspaces/sound:ro" \
      --env ATRINIK_RELEASE_INPUT_ATTESTED=1 \
      atrinik-sound-audio \
      python3 tools/sound_release.py validate-quality-outputs
  fi
fi
python3 -m unittest discover -s tests -v
python3 -m compileall -q tools tests
bash -n tools/build-release-assets.sh tools/package-release.sh tools/validate.sh
git diff --check

#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 MAJOR.MINOR.PATCH" >&2
  exit 2
fi

tag="v$1"
output_directory=build/release
mkdir -p "${output_directory}"

tools/package-release.sh "${tag}" "${output_directory}"
python3 tools/sound_release.py validate

blockers_file="${output_directory}/atrinik-sound-runtime-$1-BLOCKED.json"
python3 tools/sound_release.py blockers >"${blockers_file}"
blocker_count=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["count"])' "${blockers_file}")
if [[ ${blocker_count} -eq 0 ]]; then
  rm "${blockers_file}"
  export SOURCE_DATE_EPOCH
  SOURCE_DATE_EPOCH=$(git show -s --format=%ct "${tag}^{commit}")
  source_commit=$(git rev-parse "${tag}^{commit}")
  source_tree=$(git rev-parse "${tag}^{tree}")
  absolute_output=$(realpath "${output_directory}")
  docker build --platform linux/amd64 \
    --file tools/audio/Dockerfile --tag atrinik-sound-audio .
  docker run --rm --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:/workspaces/sound:ro" \
    --volume "${absolute_output}:/output" \
    --env SOURCE_DATE_EPOCH \
    --env ATRINIK_SOURCE_COMMIT="${source_commit}" \
    --env ATRINIK_SOURCE_TREE="${source_tree}" \
    atrinik-sound-audio \
    python3 tools/sound_release.py build-runtime "${tag}" /output
else
  echo "runtime archive blocked by ${blocker_count} recorded license/provenance findings" >&2
fi

python3 tools/sound_release.py checksums "${output_directory}"

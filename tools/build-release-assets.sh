#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 MAJOR.MINOR.PATCH" >&2
  exit 2
fi

tag="v$1"
output_directory=build/release
unset ATRINIK_RELEASE_INPUT_ATTESTED
source_commit=$(git rev-parse "${tag}^{commit}")
source_tree=$(git rev-parse "${tag}^{tree}")
if [[ $(git rev-parse HEAD) != "${source_commit}" ]]; then
  echo "release tag ${tag} does not identify HEAD" >&2
  exit 1
fi
if ! release_status=$(git status --porcelain --untracked-files=all); then
  echo "cannot verify release input worktree status" >&2
  exit 1
fi
if [[ -n ${release_status} ]]; then
  echo "release input worktree is not clean" >&2
  exit 1
fi
mkdir -p "${output_directory}"
shopt -s nullglob dotglob
existing_outputs=("${output_directory}"/*)
shopt -u nullglob dotglob
if (( ${#existing_outputs[@]} != 0 )); then
  echo "release output directory must be empty: ${output_directory}" >&2
  exit 1
fi

tools/package-release.sh "${tag}" "${output_directory}"
python3 tools/sound_release.py validate
export ATRINIK_RELEASE_INPUT_ATTESTED=1
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(git show -s --format=%ct "${tag}^{commit}")
absolute_output=$(realpath "${output_directory}")

blockers_file="${output_directory}/atrinik-sound-runtime-$1-BLOCKED.json"
python3 tools/sound_release.py blockers >"${blockers_file}"
blocker_count=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["count"])' "${blockers_file}")
if [[ ${blocker_count} -eq 0 ]]; then
  rm "${blockers_file}"
  docker build --platform linux/amd64 \
    --file tools/audio/Dockerfile --tag atrinik-sound-audio .
  docker run --rm --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:/workspaces/sound:ro" \
    --env ATRINIK_RELEASE_INPUT_ATTESTED=1 \
    atrinik-sound-audio \
    python3 tools/sound_release.py validate-quality-outputs
  comparison_directory=$(mktemp -d)
  trap 'rm -rf "${comparison_directory}"' EXIT
  run_runtime_build() {
    local target=$1
    docker run --rm --platform linux/amd64 \
      --user "$(id -u):$(id -g)" \
      --volume "$PWD:/workspaces/sound:ro" \
      --volume "${target}:/output" \
      --env SOURCE_DATE_EPOCH \
      --env ATRINIK_SOURCE_COMMIT="${source_commit}" \
      --env ATRINIK_SOURCE_TREE="${source_tree}" \
      --env ATRINIK_RELEASE_INPUT_ATTESTED \
      --env GH_TOKEN \
      atrinik-sound-audio \
      python3 tools/sound_release.py build-runtime "${tag}" /output
  }
  run_runtime_build "${absolute_output}"
  run_runtime_build "${comparison_directory}"
  cmp \
    "${absolute_output}/atrinik-sound-runtime-$1.tar.gz" \
    "${comparison_directory}/atrinik-sound-runtime-$1.tar.gz"
else
  echo "runtime archive blocked by ${blocker_count} recorded release findings" >&2
fi

docker build --platform linux/amd64 \
  --file tools/audio/classic-runtime.Dockerfile \
  --tag atrinik-sound-classic-audio .
classic_comparison_directory=$(mktemp -d)
cleanup_comparison_directories() {
  if [[ -n ${comparison_directory:-} ]]; then
    rm -rf -- "${comparison_directory}"
  fi
  rm -rf -- "${classic_comparison_directory}"
}
trap cleanup_comparison_directories EXIT
run_classic_runtime_build() {
  local target=$1
  docker run --rm --platform linux/amd64 \
    --network none \
    --user "$(id -u):$(id -g)" \
    --volume "$PWD:/workspaces/sound:ro" \
    --volume "${target}:/output" \
    --env SOURCE_DATE_EPOCH \
    --env ATRINIK_SOURCE_COMMIT="${source_commit}" \
    --env ATRINIK_SOURCE_TREE="${source_tree}" \
    --env ATRINIK_RELEASE_INPUT_ATTESTED \
    atrinik-sound-classic-audio \
    python3 tools/sound_release.py build-classic-runtime "${tag}" /output
}
run_classic_runtime_build "${absolute_output}"
run_classic_runtime_build "${classic_comparison_directory}"
classic_archive="atrinik-sound-classic-runtime-$1.tar.gz"
classic_remediation="atrinik-sound-classic-runtime-$1-REMEDIATION.json"
cmp \
  "${absolute_output}/${classic_archive}" \
  "${classic_comparison_directory}/${classic_archive}"
cmp \
  "${absolute_output}/${classic_remediation}" \
  "${classic_comparison_directory}/${classic_remediation}"
docker run --rm --platform linux/amd64 \
  --network none \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspaces/sound:ro" \
  --volume "${absolute_output}:/output:ro" \
  --env SOURCE_DATE_EPOCH \
  --env ATRINIK_SOURCE_COMMIT="${source_commit}" \
  --env ATRINIK_SOURCE_TREE="${source_tree}" \
  --env ATRINIK_RELEASE_INPUT_ATTESTED \
  atrinik-sound-classic-audio \
  python3 tools/sound_release.py verify-classic-runtime \
    "${tag}" "/output/${classic_archive}"

python3 tools/sound_release.py checksums "${output_directory}"

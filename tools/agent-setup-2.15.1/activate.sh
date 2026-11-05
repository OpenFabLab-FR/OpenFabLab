#!/bin/bash
# One-time activation on an already running, verified 2.15.1 installation.
set +x
set -euo pipefail
umask 077
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
fail(){ printf 'AGENT_SETUP_REFUSED=%s\n' "$1"; exit 1; }
[[ $# -ge 8 ]] || fail ARGUMENTS_INVALID
archive=$1 project=$2 backups=$3 agent=$4 docker_cli=$5 compose_cli=$6 image=$7 mode=$8
shift 8
rights=readonly
extra=()
confirmation=()
case "$mode" in
    --check) operation=setup-check ;;
    --prepare) operation=setup-prepare ;;
    --install)
        [[ $# = 2 && "$1" = --confirm && "$2" = AUTHORIZE-LOCAL-AGENT-2.15.1 ]] ||
            fail EXPLICIT_AGENT_AUTHORIZATION_REQUIRED
        operation=setup-install
        rights=write
        extra=(--cap-add CHOWN)
        confirmation=(--confirm "$2")
        shift 2 ;;
    *) fail ARGUMENTS_INVALID ;;
esac
[[ $# = 0 ]] || fail ARGUMENTS_INVALID
[[ "$(id -u)" = 0 && "$(uname -s)" = Linux ]] || fail LOCAL_LINUX_ADMINISTRATOR_REQUIRED
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]] || fail APPROVED_RUNNING_IMAGE_REQUIRED

canonical(){
    [[ "$1" =~ ^/[A-Za-z0-9_./@-]+$ && "$1" != / && "$(readlink -f -- "$1")" = "$1" ]]
}
independent(){
    [[ "$1/" != "$2/"* && "$2/" != "$1/"* ]]
}
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
for path in "$kit" "$archive" "$project" "$backups" "$agent" "$docker_cli" "$compose_cli"; do
    canonical "$path" || fail PATH_MUST_BE_CANONICAL_AND_ABSOLUTE
done
for path in "$project" "$project/data" "$backups" "$agent" "$agent/state" "$agent/shared"; do
    canonical "$path" && [[ -d "$path" ]] || fail LOCAL_DIRECTORY_UNSAFE_OR_MISSING
done
for path in "$project" "$backups"; do
    independent "$agent" "$path" || fail AGENT_DIRECTORIES_MUST_BE_INDEPENDENT
done
for path in "$agent" "$agent/state" "$agent/shared"; do
    permissions=$(stat -c '%a' -- "$path") || fail AGENT_DIRECTORY_OWNERSHIP_UNSAFE
    [[ "$(stat -c '%u' -- "$path")" = 0 && "$permissions" =~ ^[0-7]{3,4}$ ]] &&
        (( (8#$permissions & 022) == 0 )) || fail AGENT_DIRECTORY_OWNERSHIP_UNSAFE
done
for path in "$archive" "$kit/activate.py" "$project/compose.yaml" "$project/data/openfablab.db" "$docker_cli" "$compose_cli"; do
    canonical "$path" && [[ -f "$path" ]] || fail REQUIRED_FILE_UNSAFE_OR_MISSING
done
[[ -x "$docker_cli" && -x "$compose_cli" && -S /var/run/docker.sock ]] ||
    fail LOCAL_DOCKER_OR_COMPOSE_UNAVAILABLE
[[ "$(sha256sum <"$archive" | cut -d' ' -f1)" = 84e3363ec78b20dd7c3fc3b65e600ba27caab2fe2ec6a7adefa49cea4d886957 ]] ||
    fail APPROVED_APPLICATION_ARCHIVE_MISMATCH

docker_local(){
    env -i PATH="$PATH" "$docker_cli" --host unix:///var/run/docker.sock "$@" 2>/dev/null
}
container=$(env -i PATH="$PATH" DOCKER_HOST=unix:///var/run/docker.sock "$compose_cli" \
    --project-directory "$project" -f "$project/compose.yaml" ps -q application 2>/dev/null) ||
    fail COMPOSE_SERVICE_IDENTITY_UNAVAILABLE
[[ "$container" =~ ^[0-9a-f]{12,64}$ ]] || fail COMPOSE_SERVICE_IDENTITY_AMBIGUOUS
[[ "$(docker_local inspect --type container --format '{{.Image}}' "$container")" = "$image" ]] ||
    fail APPROVED_RUNNING_IMAGE_MISMATCH
gid=$(docker_local exec "$container" python -c 'import os;print(os.getgid())') ||
    fail SOURCE_PROCESS_GROUP_UNAVAILABLE
[[ "$gid" =~ ^[0-9]+$ ]] || fail SOURCE_PROCESS_GROUP_INVALID
docker_root=$(docker_local info --format '{{.DockerRootDir}}') || fail DOCKER_STORAGE_UNAVAILABLE
canonical "$docker_root" && [[ -d "$docker_root" ]] || fail DOCKER_STORAGE_PATH_UNSUPPORTED
for path in "$project" "$backups" "$agent"; do
    independent "$docker_root" "$path" || fail DOCKER_STORAGE_OVERLAP
done
suffix=
if [[ "$rights" = readonly ]]; then suffix=,readonly; fi
log=$(mktemp "$agent/state/SETUP_RESULT-$(date -u +%Y%m%d-%H%M%S).XXXXXXXX.log") ||
    fail REPORT_DESTINATION_REQUIRED
status=0
docker_local run --rm --user 0:0 --read-only --cap-drop ALL --cap-add DAC_OVERRIDE "${extra[@]}" \
    --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev \
    -e PYTHONDONTWRITEBYTECODE=1 -e OPENFABLAB_UPDATER_EXPECT_NNP=1 --entrypoint python \
    --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
    --mount "type=bind,source=$kit/activate.py,target=/activate.py,readonly" \
    --mount "type=bind,source=$archive,target=/approved.zip,readonly" \
    --mount "type=bind,source=$agent,target=$agent" \
    --mount "type=bind,source=$project,target=$project$suffix" \
    --mount "type=bind,source=$backups,target=$backups$suffix" \
    --mount "type=bind,source=$docker_root,target=$docker_root,readonly" \
    --mount "type=bind,source=$docker_cli,target=/usr/local/bin/docker,readonly" \
    --mount "type=bind,source=$compose_cli,target=/usr/local/lib/docker/cli-plugins/docker-compose,readonly" \
    "$image" /activate.py "$operation" --archive /approved.zip --project "$project" --backups "$backups" \
    --agent "$agent" --docker-root "$docker_root" --source-image "$image" --web-gid "$gid" \
    "${confirmation[@]}" >"$log" || status=$?
if [[ $status != 0 && ! -s "$log" ]]; then
    printf 'AGENT_SETUP_REFUSED=LOCAL_DOCKER_CONTROLLER_FAILED\n' >"$log"
fi
printf 'AGENT_SETUP_EXIT_CODE=%s\nRapport : %s\n' "$status" "$log"
exit "$status"

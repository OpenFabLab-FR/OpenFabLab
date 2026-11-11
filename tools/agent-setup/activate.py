"""Activate the local agent for the exact, already installed and approved runtime."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_ARCHIVE = 64 * 1024**2
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SetupError(Exception):
    pass


def stage(archive, runtime, expected_sha, version):
    from openfablab import __version__
    from updater_agent.installation import setup_target
    from updater_agent.releases import unpack

    if __version__ != version:
        raise SetupError("APPROVED_RUNNING_VERSION_MISMATCH")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise SetupError("APPROVED_APPLICATION_SHA256_REQUIRED")
    with archive.open("rb") as stream:
        data = stream.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != expected_sha:
        raise SetupError("APPROVED_APPLICATION_ARCHIVE_MISMATCH")
    extracted = runtime / "checked"
    info = unpack(io.BytesIO(data), extracted, version)
    setup_target(info)
    declared = info.get("runtime_files")
    if not isinstance(declared, dict) or not {"app.py","family_model.py","openfablab/__init__.py"} <= declared.keys():
        raise SetupError("APPROVED_APPLICATION_RUNTIME_MISSING")
    if any(info["files"].get(path) != digest for path, digest in declared.items()):
        raise SetupError("APPROVED_APPLICATION_RUNTIME_MISMATCH")
    # Run the installed image's code, never the code extracted from the ZIP.
    manifest = runtime / "approved-manifest.json"
    manifest.write_text(json.dumps(info))
    manifest.chmod(0o600)
    return manifest


def run(args, manifest):
    from updater_agent.__main__ import main
    from updater_agent.docker_executor import DockerExecutor
    from updater_agent.installation import validate_layout
    from updater_agent.privileges import validate_if_expected
    from updater_agent.security import checked_path, load_policy, private_json

    if os.geteuid() != 0 or sys.platform != "linux" or os.environ.get("OPENFABLAB_UPDATER_EXPECT_NNP") != "1":
        raise SetupError("RESTRICTED_LINUX_CONTROLLER_REQUIRED")
    validate_if_expected()
    state = checked_path(args.agent / "state")
    shared = checked_path(args.agent / "shared")
    for directory in (args.agent, state, shared):
        status = directory.stat()
        if status.st_uid != 0 or status.st_mode & 0o022:
            raise SetupError("AGENT_DIRECTORY_OWNERSHIP_UNSAFE")
    policy = dict(protocol=1, project=str(args.project), compose_file=str(args.project / "compose.yaml"),
                  service="application", data=str(args.project / "data"),
                  database=str(args.project / "data" / "openfablab.db"), backups=str(args.backups),
                  state=str(state), socket=str(shared / "agent.sock"), token_file=str(shared / "token"),
                  repository_id=1399693198, docker="/usr/local/bin/docker",
                  docker_root=str(args.docker_root), enabled=True, web_gid=args.web_gid)
    validate_layout(policy)
    policy_file = state / "policy.json"
    if policy_file.exists() or policy_file.is_symlink():
        if load_policy(policy_file) != policy:
            raise SetupError("EXISTING_AGENT_POLICY_REQUIRES_REVIEW")
    else:
        private_json(policy_file, policy)
    policy = load_policy(policy_file)
    helper_image = args.source_image
    if args.operation == "setup-install":
        prepared = checked_path(state / "prepared-agent.json", False)
        info = prepared.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_size > 4096:
            raise SetupError("AGENT_PREPARATION_RECEIPT_UNSAFE")
        helper_image = json.loads(prepared.read_bytes()).get("image", "")
        if not isinstance(helper_image, str) or not IMAGE.fullmatch(helper_image):
            raise SetupError("PREPARED_AGENT_IMAGE_INVALID")
    executor = DockerExecutor(policy, helper_image)
    if executor.container()["Image"] != args.source_image:
        raise SetupError("APPROVED_RUNNING_IMAGE_MISMATCH")
    executor.capability_preflight()
    command = ["--policy", str(policy_file), "--helper-image", helper_image, args.operation,
               "--manifest", str(manifest)]
    if args.operation == "setup-prepare":
        command += ["--docker-cli", "/usr/local/bin/docker", "--compose-cli",
                    "/usr/local/lib/docker/cli-plugins/docker-compose"]
    if args.operation == "setup-install":
        command += ["--confirm", args.confirm]
    sys.argv[1:] = command
    return main()


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["verify", "setup-check", "setup-prepare", "setup-install"])
    for field in ("archive", "project", "backups", "agent", "docker-root"):
        parser.add_argument("--" + field, type=Path, required=field == "archive")
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-image")
    parser.add_argument("--web-gid", type=int)
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.confirm != ("AUTHORIZE-LOCAL-AGENT-" + args.version if args.operation == "setup-install" else None):
        raise SetupError("EXPLICIT_AGENT_AUTHORIZATION_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="openfablab-agent-") as folder:
        runtime = Path(folder)
        manifest = stage(args.archive, runtime, args.sha256, args.version)
        if args.operation == "verify":
            print("APPROVED_APPLICATION_ARCHIVE_OK")
            return 0
        if (not all((args.project, args.backups, args.agent, args.docker_root)) or args.web_gid is None
                or not IMAGE.fullmatch(args.source_image or "")):
            raise SetupError("LOCAL_SETUP_ARGUMENTS_REQUIRED")
        return run(args, manifest)


if __name__ == "__main__":
    try:
        sys.exit(cli())
    except Exception as error:
        code = str(error) if isinstance(error, SetupError) else getattr(error, "code", "")
        if not isinstance(code, str) or not re.fullmatch("[A-Z0-9_]{1,100}", code):
            code = "AGENT_SETUP_OPERATION_FAILED"
        print("AGENT_SETUP_REFUSED=" + code)
        sys.exit(1)

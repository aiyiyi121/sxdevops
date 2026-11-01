"""Locate private deployment context without displaying connection values."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


PRIVATE_FILES = (
    "connection_file",
    "known_hosts_file",
    "remote_helper",
    "runbook_file",
)
PROFILE_FIELDS = {"version", "mode", "transport", "runtime", *PRIVATE_FILES}


class ContextError(Exception):
    """An actionable error whose message contains no private configuration values."""


def git(directory, *args):
    result = subprocess.run(
        ["git", "-C", str(directory), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def discover_profile():
    override = os.environ.get("SXDEVOPS_DEPLOY_PROFILE")
    if override:
        return Path(override).expanduser().resolve(), "environment override"
    code, checkout = git(Path.cwd(), "rev-parse", "--show-toplevel")
    if code:
        raise ContextError("Run from an SXDevOps checkout or set SXDEVOPS_DEPLOY_PROFILE.")
    local = Path(checkout) / ".codex" / "deploy.local.json"
    if local.is_file():
        return local.resolve(), "current checkout"
    code, common = git(Path(checkout), "rev-parse", "--git-common-dir")
    if not code:
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = Path(checkout) / common_path
        shared = common_path.resolve().parent / ".codex" / "deploy.local.json"
        if shared.is_file():
            return shared.resolve(), "primary checkout"
    raise ContextError("No private deployment profile found. Supply it privately; do not infer a target from Git.")


def privacy_errors(path):
    code, root = git(path.parent, "rev-parse", "--show-toplevel")
    if code:
        return []
    try:
        relative = path.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return ["private file resolves outside its reported Git root"]
    errors = []
    code, _ = git(root, "ls-files", "--error-unmatch", "--", relative)
    if code == 0:
        errors.append("private file is tracked by Git")
    code, _ = git(root, "check-ignore", "--no-index", "-q", "--", relative)
    if code != 0:
        errors.append("private file is not ignored by Git")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate private files without connecting to a server.")
    args = parser.parse_args()
    try:
        profile_path, origin = discover_profile()
        if not profile_path.is_file():
            raise ContextError("The explicitly selected private deployment profile is missing.")
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            raise ContextError("Cannot read valid JSON from the private deployment profile.") from None
        if not isinstance(profile, dict) or profile.get("version") != 1:
            raise ContextError("Expected a version-1 private profile; see references/environment-reuse.md.")
        if set(profile) - PROFILE_FIELDS:
            raise ContextError("Unsupported profile fields. Keep credentials in the referenced connection file.")
        if profile.get("mode") != "customized" or profile.get("transport") not in ("paramiko", "openssh"):
            raise ContextError("Unsupported deployment mode or transport in the private profile.")
        runtime = profile.get("runtime")
        if not isinstance(runtime, dict) or not runtime.get("workdir") or not runtime.get("compose_files"):
            raise ContextError("The private runtime mapping is incomplete.")
        paths = {"profile": profile_path}
        for field in PRIVATE_FILES:
            value = profile.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ContextError(f"Missing private file reference: {field}.")
            path = Path(value).expanduser()
            paths[field] = (path if path.is_absolute() else profile_path.parent / path).resolve()
        report = {"origin": origin, "private_files": {key: str(path) for key, path in paths.items()}}
        errors = []
        if args.check:
            for label, path in paths.items():
                if not path.is_file():
                    errors.append(f"{label}: required private file is missing")
                else:
                    errors.extend(f"{label}: {issue}" for issue in privacy_errors(path))
            if paths["known_hosts_file"].is_file() and not paths["known_hosts_file"].stat().st_size:
                errors.append("known_hosts_file: host-key pins are empty")
            services = runtime.get("app_services")
            containers = runtime.get("app_containers")
            if (not isinstance(services, list) or not services or
                    not isinstance(containers, list) or len(services) != len(containers)):
                errors.append("runtime: enabled app services and containers must have a matching explicit mapping")
            disabled = runtime.get("disabled_services", [])
            if not isinstance(disabled, list) or any(service in disabled for service in services or []):
                errors.append("runtime: an enabled service is also marked disabled, or disabled_services is invalid")
            report["check"] = "failed" if errors else "passed"
            report["issues"] = errors
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 1 if errors else 0
    except ContextError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (ValueError, TypeError, OSError):
        # Exception details may contain values from private files or connection errors.
        print("Deployment context could not be validated. Check the local profile, private file availability, and references/environment-reuse.md.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

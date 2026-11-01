# Reusing a private deployment environment

Read this when continuing an existing installation from a new session or checkout. The public skill supplies procedures; the ignored local profile supplies the actual target and operational state.

## Discovery

Run from the checkout that contains the approved source changes:

```powershell
python .codex/skills/sxdevops-deploy/scripts/deploy_context.py --check
```

Discovery order is an explicitly set `SXDEVOPS_DEPLOY_PROFILE`, the current checkout's `.codex/deploy.local.json`, then the primary checkout's profile obtained from Git's common directory. An explicit missing override fails instead of silently selecting another server. Paths inside the profile are relative to the profile's directory unless absolute.

The command uses Python's standard library, does not contact the server, and does not print SSH addresses, usernames, passwords, domains, or arbitrary profile values. It validates that the profile and its referenced private files exist and are untracked and ignored wherever they are inside a Git working tree. Never work around a failed privacy check with `git add -f`.

A new session in the same repository can reuse these files immediately. A linked worktree can reuse the primary checkout's profile; package source from the active worktree, not from the directory containing the connection helper. For an unrelated checkout on the same computer, set an absolute override:

```powershell
$env:SXDEVOPS_DEPLOY_PROFILE = '<absolute path to the ignored deploy.local.json>'
python .codex/skills/sxdevops-deploy/scripts/deploy_context.py --check
```

For another computer, privately transfer/recreate the profile and required connection material, verify the host-key fingerprint, and configure the override. These files are deliberately absent from Git.

## Profile contract

The existing environment uses a version-1 profile with this structure; angle-bracket values below are placeholders, not deployment defaults:

```json
{
  "version": 1,
  "mode": "customized",
  "transport": "paramiko",
  "connection_file": "<private directory>/connection.json",
  "known_hosts_file": "<private directory>/known_hosts",
  "remote_helper": "<private directory>/remote.py",
  "runbook_file": "<private directory>/environment.local.md",
  "runtime": {
    "workdir": "<remote application directory>",
    "compose_command": ["<absolute podman-compose executable>"],
    "compose_project": "<project>",
    "compose_files": ["<active private compose file>"],
    "app_services": ["<web service>", "<async worker service>"],
    "app_containers": ["<web container>", "<async worker container>"],
    "disabled_services": ["<intentionally disabled scheduler>"],
    "static_publish_command": "<remote publication helper>",
    "backup_command": "<remote backup helper>"
  }
}
```

The existing private connection JSON has `host`, `port`, `user`, and `password`; helpers must consume it locally without printing values or passing passwords on the command line. A future key-based transport can use its own private contract. Do not copy the actual profile into this example or add credentials inline to the profile.

The private runbook contains the actual URLs, exact runtime topology, TLS/static publication locations, memory settings, intentionally disabled services, backup procedure, and dated handoff records. Treat its observations as a baseline to verify, not as timeless live state. Never copy the private runbook or logs into tracked skill references.

## Customized runtime

1. Read the resolved private runbook and runtime mapping. Inspect active systemd/Compose selection, selected container image IDs, memory headroom, and the source baseline in a single remote check. Print selected fields only: full `podman inspect`, Compose `config`, and environment dumps can disclose secrets.
2. Use the existing private transport helper with pinned host keys. Read its implementation/CLI before invocation; install `paramiko` from the normal package registry only if unavailable. The configured helper accepts a local UTF-8 shell script and can combine a JSON SFTP upload list with a following remote script. Keep these generated scripts and upload lists in an ignored directory. The connection file and `known_hosts` must remain beside the current helper.
3. Create a fresh explicit source package from the active checkout and compare against the current remote baseline. Do not rerun historical scripts with stale expected images or hashes. Save source manifests, database/config backups, and the previous image before replacing anything.
4. Keep the active Compose project/file flags on every command. Recreate only enabled app services using the updated image. Retain the async worker; an intentionally removed scheduler remains removed. A frontend-only layer built from the verified running image may reduce memory use when no backend or dependency change is required; record the base image and validate the resulting assets.
5. If Nginx serves a separate static release, publish from the running app image with the configured hash-verifying publication helper and retain its previous symlink target. Verify HTTPS for the actual configured hostnames and real affected APIs/UI. A successful build or healthy loopback login alone does not verify the public release.
6. Update the private runbook/handoff with the current image, backup path, selected services, static publication and validation results. Do not change resource limits, optional services, credentials, or database contents merely to make a deployment helper's defaults work.

The public `deploy.ps1` is a legacy three-service helper. For this profile it refuses remote execution and only supports `-PrepareOnly`; use the customized sequence above. A profile is connection context, not a grant of permission for deployments, destructive maintenance, Git pushes, or tag changes.

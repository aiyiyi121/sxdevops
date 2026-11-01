---
name: sxdevops-deploy
description: Deploy approved SXDevOps changes or maintain an existing environment using its private local profile, with backups, targeted Podman Compose recreation, static publication, and health verification.
metadata:
  short-description: 部署 SXDevOps
---

# SXDevOps Deployment

Use for authorized synchronization or deployment of SXDevOps to its configured server.

## Resume An Existing Environment

New sessions must discover the existing private handoff before choosing a target or deployment command:

```powershell
python .codex/skills/sxdevops-deploy/scripts/deploy_context.py --check
```

The resolver checks `SXDEVOPS_DEPLOY_PROFILE`, then the current checkout's `.codex/deploy.local.json`, then the primary checkout's profile for a linked worktree. It prints paths and validation results, never connection values. Read the resolved private runbook and runtime profile; pass the resolved absolute path to local helpers when working in another checkout. Do not print or copy credential JSON into the conversation.

See [references/environment-reuse.md](references/environment-reuse.md) for the private profile contract, reuse across sessions/worktrees, and the customized-runtime workflow. Reuse an existing valid configuration without asking the user for the same connection details again. A missing profile on another computer requires privately supplying that profile and its referenced files; a Git clone alone does not contain credentials. Loading a profile is not authorization to deploy, seed data, push Git, or move a release tag.

## Target

- SSH server: for a versioned private profile, use its connection file and configured helper. For the legacy OpenSSH helper only, use `-Server` or the `server` value in the local, ignored `.codex/deploy.local.json`. Keep actual targets and credentials out of version control. Honor the configured SSH port and explicit user overrides.
- Working copy: `/opt/sxdevops`; it is not a Git checkout.
- Standard runtime names: Podman Compose app `sxdevops-app` on port `8000`, optional CMDB scheduler `sxdevops-cmdb-sync-scheduler`, and AIOps worker `sxdevops-aiops-chat-worker`. The private profile determines which services are actually enabled.
- Preserve existing private Compose files, environment files, encryption keys, certificates, and `docker-compose.override.yml` where present. Do not print or include these in a source package.
- Inspect the active service unit and Compose file before choosing a deployment command. Some installations use a private Compose file and omit unused services; adapt the helper's default three-service command to that active configuration rather than re-enabling removed services.

## Flow

1. Select only approved source files. Use completed relevant validation; frontend changes require a production build.
2. Create an explicit file list and SHA-256 manifest locally. Package those files with their relative paths.
3. Transfer the package once. In one remote script, validate staged hashes, back up every destination under `/opt/sxdevops/.deploy-backups/<topic>-<timestamp>/`, install the selected files, and validate every installed hash.
4. Build the selected application image with the active project's exact Compose file list, then force recreation of the enabled app services that use it. Use the profile's service/container mapping; do not re-enable an omitted scheduler or rebuild unrelated databases/observability services. A new image alone does not replace old containers. For schema changes, explicitly plan backups, migrations, and app/worker compatibility; do not rerun seed/bootstrap initialization on an existing database.
5. Verify the selected app/worker containers are running with the current `localhost/sxdevops:latest` image, Django check passes, and the app returns HTTP 200. If Nginx serves a separate frontend release, publish the running app image's built assets with hash verification and an atomic symlink switch before testing the public page. Where installed, `/usr/local/sbin/sxdevops-publish-static` performs this publication; retain the prior release. Then run the affected real API or UI regression.
6. Stop on any failed transfer, hash, build, recreation, or health check. Preserve backups and logs; do not improvise a rollback.

## Connection Discipline

For the standard OpenSSH runtime, prefer [scripts/deploy.ps1](scripts/deploy.ps1), which uses one SCP connection and one SSH connection for the deployment. Backups and per-file hashes are processed inside the remote script; never open SSH or SCP separately for every file.

That helper executes the legacy three-service runtime only. For a customized private profile it supports `-PrepareOnly` and refuses remote deployment; use the profile's private transport helper with an adapted, reviewed remote script. This prevents a default command from restarting disabled services or omitting the production Compose file.

- Batch independent remote checks into the same session.
- Poll an existing command session for build or test progress; polling does not require a new SSH handshake.
- Package regression scripts together and run them in one remote session.
- Use bounded connection timeouts and keepalive options. On reset/refusal, stop reconnecting and report the failed stage; resume after the connection is confirmed restored.
- Require pinned host keys: OpenSSH uses `StrictHostKeyChecking=yes`; Paramiko uses the existing private `known_hosts` and `RejectPolicy`. Missing or changed host keys require verifying the actual fingerprint through a trusted channel; never use automatic trust or disable TLS verification.
- Do not try other ports or change SSH/firewall/security settings to work around an interception. Use the port authorized by the user.
- No particular connection count guarantees exemption from IT policies; batching reduces the observed burst of short sessions.

## Helper

Run from the repository root in PowerShell:

```powershell
$approvedFiles = @(
    'backend/aiops/audit_executions.py',
    'frontend/src/views/AIOpsAudit.vue'
)
& .codex/skills/sxdevops-deploy/scripts/deploy.ps1 -Files $approvedFiles -Topic 'aiops-execution-audit' -Port 22
```

For a legacy profile the helper reads `server` and optional `port`, unless explicitly overridden; the fallback port is 22. It uses the same override/current/primary checkout discovery order as the context resolver. `-PrepareOnly` builds and lists the local package without contacting the server or requiring a target. It excludes generated artifacts and server configuration; supply an explicit list, never the whole working tree. It retains the package, staging files, timestamped backup, and build/recreation logs for diagnosis.

For a deployment outside the helper's three-service scope, adapt the same batched procedure to the approved services. Never rerun a previous one-off deployment script unchanged: its expected image, source baseline, package, and backup assumptions may be stale.

## Git And Private Configuration

- Tracked skill files describe the workflow and placeholders only. Store actual SSH addresses/users/passwords, domains, tokens, private keys, certificate archives, host-key pins, resolved environment/Compose output, and operational history in the ignored profile and private runbook directory.
- Before committing, check both `git check-ignore` and `git ls-files` for private paths; ignore rules do not remove files that are already tracked. Review the explicit staged diff and scan it for actual connection values, secrets, and accidental inclusion of private files. Report matching file paths or field names without printing matching secrets.
- Use an explicit file list for staging and packaging. Preserve other sessions' changes. Never force-add private configuration, deploy the entire working tree, or embed credentials in shell arguments/URLs.
- Update the ignored runbook after a deployment with the observed image, backup path, selected services, static release, and real checks. Do not bake a current image/tag into this public skill. Push or retarget a release tag only within the user's authorized scope; use a remote-value lease when an authorized tag update requires replacement.

## First Deployment On A New Server

- Inspect OS, CPU, RAM, disk, existing services, domain resolution, and registry access before choosing the runtime configuration. A new server has no application backup yet; retain the source manifest and a record of newly created configuration instead.
- Package an explicit tracked-source file list for initial installation. Exclude local databases, credentials, runtime state, dependencies, and generated assets; build the frontend in the release image. Validate staged and installed SHA-256 hashes as for an upgrade.
- Generate independent application, database, and encryption secrets into private server files with restrictive permissions. Keep an ignored local handoff if needed. Never reuse another server's override file or upload local development credentials.
- Keep databases, caches, and observability ingestion endpoints private. Verify actual listening sockets after Compose starts; host networking requires explicit loopback listeners for every service. Bind the app to loopback behind a domain-restricted reverse proxy that supports WebSockets.
- Resolve package/registry access failures using verified reachable mirrors and bounded timeouts. Record server-specific build adaptations privately; do not change SSH ports or weaken TLS verification.
- For seeded showcase environments, run destructive seed commands only against the confirmed new database, then disable them for subsequent starts. Seed schedules and external notification routes must stay inactive until their actual targets are configured.
- Check whether startup migrations invoke initializers that overwrite customized records. After installing the initial schema, manage migrations explicitly during upgrades when needed and disable repeated bootstrap initialization on ordinary restarts.
- Start additional components only within measured resource limits. Verify real metric queries, log queries, trace search/detail, and embedded dashboards rather than reporting container startup as successful integration.
- On small servers, run image builds and full test suites sequentially, with memory and filesystem-cache headroom. Prefer an isolated test container over running full suites inside the memory-limited serving container. Inspect memory pressure and disk wait as well as CPU usage; temporary validation limits must be restored before handoff.
- For memory incidents, inspect each container's anonymous memory, file cache, `memory.events`, and memory pressure as well as host available memory. A low cgroup limit can cause sustained reclaim and disk stalls without a host OOM. Reduce verified-unused services or Grafana data-source plugins before lowering working limits; preserve configured dashboards, actual data sources, and async workers required by active features. Confirm that stopped services also stay disabled in the active startup configuration.
- Enable reboot persistence and bounded log/data retention. Back up the database and private configuration before later updates. When a certificate is pending, use HTTP explicitly and leave HTTPS redirects/HSTS disabled until a trusted certificate is installed; browser reputation warnings cannot be guaranteed away by configuration.

## Handoff

State the backup path, recreated services, current image and health checks, and actual regression results. State a commit only if committing/pushing was requested. Do not report success before post-recreation verification.

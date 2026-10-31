---
name: sxdevops-deploy
description: Deploy approved SXDevOps changes to the configured server, including safe backup, Podman Compose rebuild, and health verification.
metadata:
  short-description: 部署 SXDevOps
---

# SXDevOps Deployment

Use for authorized synchronization or deployment of SXDevOps to its configured server.

## Target

- SSH server: use `-Server` or the `server` value in the local, ignored `.codex/deploy.local.json`. Keep server addresses and credentials out of version control. The default port is `22`; a port explicitly supplied by the user takes precedence.
- Working copy: `/opt/sxdevops`; it is not a Git checkout.
- Runtime: Podman Compose; app `sxdevops-app` on port `8000`, CMDB scheduler `sxdevops-cmdb-sync-scheduler`, AIOps worker `sxdevops-aiops-chat-worker`.
- Preserve `docker-compose.override.yml`: it contains server secrets. Do not upload, print, or package it.
- Inspect the active service unit and Compose file before choosing a deployment command. Some installations use a private Compose file and omit unused services; adapt the helper's default three-service command to that active configuration rather than re-enabling removed services.

## Flow

1. Select only approved source files. Use completed relevant validation; frontend changes require a production build.
2. Create an explicit file list and SHA-256 manifest locally. Package those files with their relative paths.
3. Transfer the package once. In one remote script, validate staged hashes, back up every destination under `/opt/sxdevops/.deploy-backups/<topic>-<timestamp>/`, install the selected files, and validate every installed hash.
4. Build with `podman-compose up -d --build`, then force recreation of `sxdevops cmdb-sync-scheduler aiops-chat-worker`. A new image alone does not replace old containers.
5. Verify the selected app/worker containers are running with the current `localhost/sxdevops:latest` image, Django check passes, and the app returns HTTP 200. If Nginx serves a separate frontend release, publish the running app image's built assets with hash verification and an atomic symlink switch before testing the public page. Where installed, `/usr/local/sbin/sxdevops-publish-static` performs this publication; retain the prior release. Then run the affected real API or UI regression.
6. Stop on any failed transfer, hash, build, recreation, or health check. Preserve backups and logs; do not improvise a rollback.

## Connection Discipline

Prefer [scripts/deploy.ps1](scripts/deploy.ps1), which uses one SCP connection and one SSH connection for the deployment. Backups and per-file hashes are processed inside the remote script; never open SSH or SCP separately for every file.

- Batch independent remote checks into the same session.
- Poll an existing command session for build or test progress; polling does not require a new SSH handshake.
- Package regression scripts together and run them in one remote session.
- Use bounded connection timeouts and keepalive options. On reset/refusal, stop reconnecting and report the failed stage; resume after the connection is confirmed restored.
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

The helper reads its target from `.codex/deploy.local.json` unless `-Server` is supplied, and defaults to port 22. `-PrepareOnly` builds and lists the local package without contacting the server or requiring a target. It excludes generated artifacts and server configuration; supply an explicit list, never the whole working tree. It retains the package, staging files, timestamped backup, and build/recreation logs for diagnosis.

For a deployment outside the helper's three-service scope, adapt the same batched procedure to the approved services.

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

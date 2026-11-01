param(
    [Parameter(Mandatory = $true)]
    [string[]]$Files,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{0,63}$')]
    [string]$Topic,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.@:-]*$')]
    [string]$Server,
    [ValidateRange(1, 65535)]
    [int]$Port = 22,
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Get-Location).Path
$taskServer = $Server
$taskConfigPath = Join-Path $taskRoot '.codex/deploy.local.json'
$taskProfileOverride = [Environment]::GetEnvironmentVariable('SXDEVOPS_DEPLOY_PROFILE')
if ($taskProfileOverride) {
    $taskConfigPath = [System.IO.Path]::GetFullPath($taskProfileOverride)
} elseif (-not (Test-Path -LiteralPath $taskConfigPath -PathType Leaf)) {
    $taskCommonGitDir = & git rev-parse --git-common-dir 2>$null
    if ($LASTEXITCODE -eq 0 -and $taskCommonGitDir) {
        if (-not [System.IO.Path]::IsPathRooted($taskCommonGitDir)) {
            $taskCommonGitDir = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $taskCommonGitDir))
        }
        $taskSharedConfig = Join-Path (Split-Path -Parent $taskCommonGitDir) '.codex/deploy.local.json'
        if (Test-Path -LiteralPath $taskSharedConfig -PathType Leaf) {
            $taskConfigPath = $taskSharedConfig
        }
    }
}
if ($taskProfileOverride -and -not (Test-Path -LiteralPath $taskConfigPath -PathType Leaf)) {
    throw 'SXDEVOPS_DEPLOY_PROFILE points to a missing private profile.'
}
if (Test-Path -LiteralPath $taskConfigPath -PathType Leaf) {
    $taskConfig = Get-Content -LiteralPath $taskConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $PrepareOnly -and ($taskConfig.version -or $taskConfig.mode -eq 'customized' -or
        ($taskConfig.transport -and $taskConfig.transport -ne 'openssh'))) {
        throw 'This private runtime requires its configured transport and service list. Run deploy_context.py --check and read references/environment-reuse.md. Use -PrepareOnly for packaging only.'
    }
    if (-not $taskServer) {
        $taskServer = [string]$taskConfig.server
    }
    if (-not $PSBoundParameters.ContainsKey('Port') -and $taskConfig.port) {
        if ($taskConfig.port -lt 1 -or $taskConfig.port -gt 65535) {
            throw 'Invalid SSH port in the private profile.'
        }
        $Port = [int]$taskConfig.port
    }
}
if (-not $PrepareOnly -and $taskServer -notmatch '^[A-Za-z0-9][A-Za-z0-9_.@:-]*$') {
    throw 'Supply -Server or configure server in the ignored .codex/deploy.local.json file.'
}
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskIdentifier = "$Topic-$taskStamp-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$taskStage = Join-Path ([System.IO.Path]::GetTempPath()) "sxdevops-$taskIdentifier"
$taskPayload = Join-Path $taskStage 'payload'
$taskArchive = "$taskStage.tar.gz"
$taskRemoteArchive = "/tmp/sxdevops-$taskIdentifier.tar.gz"
$taskRemoteStage = "/tmp/sxdevops-$taskIdentifier"
$taskEncoding = [System.Text.UTF8Encoding]::new($false)
$taskFiles = @($Files | Select-Object -Unique)
$taskManifest = @()

if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'docker-compose.yml'))) {
    throw 'Run from the SXDevOps repository root.'
}
if (-not $taskFiles.Count) {
    throw 'An explicit source file list is required.'
}
foreach ($taskFile in $taskFiles) {
    if ($taskFile -match '(^/|\\|[:*?"\r\n\x00-\x1f]|(^|/)\.\.?(/|$))' -or
        $taskFile -match '(^|/)(node_modules|dist|__pycache__|\.git|\.codex|runtime)(/|$)' -or
        $taskFile -match '(^|/)(\.env(?:\..*)?|docker-compose\.override\.yml|config\.json|db\.sqlite3)$') {
        throw "Unsupported deployment path: $taskFile"
    }
    $taskSource = Join-Path $taskRoot $taskFile
    if (-not (Test-Path -LiteralPath $taskSource -PathType Leaf) -or
        (Get-Item -LiteralPath $taskSource).LinkType) {
        throw "A regular source file is required: $taskFile"
    }
}
New-Item -ItemType Directory -Path $taskPayload -Force | Out-Null
foreach ($taskFile in $taskFiles) {
    $taskSource = Join-Path $taskRoot $taskFile
    $taskDestination = Join-Path $taskPayload $taskFile
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskDestination) -Force | Out-Null
    Copy-Item -LiteralPath $taskSource -Destination $taskDestination
    $taskHash = (Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskManifest += "$taskHash  $taskFile"
}
[System.IO.File]::WriteAllText((Join-Path $taskStage 'files.txt'), ($taskFiles -join "`n") + "`n", $taskEncoding)
[System.IO.File]::WriteAllText((Join-Path $taskStage 'sha256.txt'), ($taskManifest -join "`n") + "`n", $taskEncoding)
$taskRemoteScript = @'
#!/usr/bin/env bash
set -euo pipefail
stage="$(cd "$(dirname "$0")" && pwd)"
root=/opt/sxdevops
backup="$root/.deploy-backups/$1"
phase=staging
trap 'printf "DEPLOY_FAILED phase=%s backup=%s\n" "$phase" "$backup" >&2' ERR
cd "$stage/payload"
sha256sum -c "$stage/sha256.txt"
phase=backup
test ! -e "$backup"
mkdir -p "$backup"
while IFS= read -r file; do
    mkdir -p "$backup/$(dirname "$file")"
    if test -e "$root/$file"; then
        test -f "$root/$file"
        test ! -L "$root/$file"
        cp -a -- "$root/$file" "$backup/$file"
    else
        printf '%s\n' "$file" >> "$backup/missing-files.txt"
    fi
done < "$stage/files.txt"
cp "$stage/files.txt" "$stage/sha256.txt" "$backup/"
printf 'BACKUP=%s\n' "$backup"
phase=install
while IFS= read -r file; do
    mkdir -p "$root/$(dirname "$file")"
    cp -- "$stage/payload/$file" "$root/$file"
done < "$stage/files.txt"
cd "$root"
sha256sum -c "$stage/sha256.txt"
phase=build
printf 'BUILD_START\n'
podman-compose up -d --build > "$backup/build.log" 2>&1
phase=recreate
printf 'RECREATE_START\n'
podman-compose up -d --force-recreate sxdevops cmdb-sync-scheduler aiops-chat-worker > "$backup/recreate.log" 2>&1
phase=health
curl --retry 12 --retry-connrefused --retry-delay 2 -fsS -o /tmp/sxdevops-health.html -w 'HTTP=%{http_code} SIZE=%{size_download}\n' http://127.0.0.1:8000/
podman exec sxdevops-app python manage.py check
image="$(podman image inspect localhost/sxdevops:latest --format '{{.Id}}')"
for container in sxdevops-app sxdevops-cmdb-sync-scheduler sxdevops-aiops-chat-worker; do
    container_image="$(podman inspect "$container" --format '{{.Image}}')"
    status="$(podman inspect "$container" --format '{{.State.Status}}')"
    test "$container_image" = "$image"
    test "$status" = running
    printf '%s %s %s\n' "$container" "$container_image" "$status"
done
podman-compose ps
printf 'DEPLOY_OK backup=%s image=%s\n' "$backup" "$image"
'@
[System.IO.File]::WriteAllText((Join-Path $taskStage 'deploy.sh'), $taskRemoteScript.Replace("`r`n", "`n") + "`n", $taskEncoding)
& tar -czf $taskArchive -C $taskStage payload files.txt sha256.txt deploy.sh
if ($LASTEXITCODE -ne 0) {
    throw 'Local package creation failed.'
}
Write-Output "PACKAGE=$taskArchive FILES=$($taskFiles.Count) PORT=$Port"
if ($PrepareOnly) {
    & tar -tzf $taskArchive
    if ($LASTEXITCODE -ne 0) {
        throw 'Local package inspection failed.'
    }
    return
}
& scp -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -P $Port $taskArchive "${taskServer}:$taskRemoteArchive"
if ($LASTEXITCODE -ne 0) {
    throw 'Batch transfer failed. Stop reconnecting until connectivity is restored.'
}
$taskRemoteCommand = "set -e; mkdir -p '$taskRemoteStage'; tar -xzf '$taskRemoteArchive' -C '$taskRemoteStage'; bash '$taskRemoteStage/deploy.sh' '$taskIdentifier'"
& ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p $Port $taskServer $taskRemoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Deployment stopped. Inspect /opt/sxdevops/.deploy-backups/$taskIdentifier and retained staging files before resuming."
}

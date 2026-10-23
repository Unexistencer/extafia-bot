#!/usr/bin/env bash
# Read-only triage. Does not start Python/pip, update packages, or print secrets.
# Run as an account with Docker access: bash vm-security-check.sh [container]
set -eu
container="${1:-extafia}"
printf '\n== Host ==\n'
date -u '+%Y-%m-%dT%H:%M:%SZ'
uname -srmo
if [ -r /etc/os-release ]; then cat /etc/os-release; fi
printf '\n== Container identity ==\n'
docker container inspect --format 'Name={{.Name}} ImageID={{.Image}} ImageRef={{.Config.Image}} Created={{.Created}} Started={{.State.StartedAt}} Status={{.State.Status}} User={{.Config.User}} Privileged={{.HostConfig.Privileged}} ReadOnlyRootfs={{.HostConfig.ReadonlyRootfs}}' "$container"
image_id="$(docker container inspect --format '{{.Image}}' "$container")"
docker image inspect --format 'ID={{.Id}} Created={{.Created}} RepoDigests={{json .RepoDigests}}' "$image_id"
printf '\n== Existing local image inventory ==\n'
docker image ls --digests --no-trunc --format '{{.Repository}}:{{.Tag}} {{.Digest}} {{.ID}} {{.CreatedAt}}'
printf '\n== Container filesystem triage (shell only) ==\n'
if [ "$(docker container inspect --format '{{.State.Running}}' "$container")" != true ]; then
  printf 'Container is stopped; skipping filesystem scan. Do not start it just for triage.\n'
  exit 0
fi
docker exec -i "$container" sh -s <<'REMOTE'
set -eu
printf '\n-- OS package versions --\n'
if command -v dpkg-query >/dev/null 2>&1; then
  dpkg-query -W -f='${Package} ${Version}\n' ca-certificates openssl 2>/dev/null || true
fi
printf '\n-- Installed distribution metadata (not imported) --\n'
for base in /usr/local/lib /usr/lib /app /opt; do
  [ -d "$base" ] || continue
  find "$base" -type f -path '*/site-packages/*.dist-info/METADATA' \
    -exec awk '/^Name: / {name=$0} /^Version: / {print name " | " $0; exit}' {} \; 2>/dev/null || true
done
printf '\n-- Startup hook / LiteLLM evidence paths --\n'
for base in /usr/local/lib /usr/lib /app /opt; do
  [ -d "$base" ] || continue
  find "$base" \( -name 'cook.pth' -o -name 'cook.py' -o -name 'sitecustomize.py' \
    -o -name 'cook.cpython-*.pyc' -o -name 'sitecustomize*.pyc' \
    -o -name 'litellm*.dist-info' -o -name '*.pth' \) -print 2>/dev/null || true
done
printf '\n-- Known loader lock presence --\n'
if [ -e /tmp/remote_code_loader.lock ]; then
  printf 'PRESENT: /tmp/remote_code_loader.lock\n'
else
  printf 'Not found (does not rule out past execution).\n'
fi
printf '\n-- Relevant CA labels in common bundle locations --\n'
for base in /etc/ssl/certs /usr/share/ca-certificates /usr/local/lib /usr/lib /opt; do
  [ -d "$base" ] || continue
  find "$base" -type f \( -name '*.crt' -o -name 'cacert.pem' \) \
    -exec grep -HnE 'emSign|eMudhra|AAA Certificate Services' {} \; 2>/dev/null || true
done
REMOTE
printf '\nTriage complete. Missing markers or CA labels do not prove safety.\n'

# GCP VM remote security check

Prepared for the 2026-10-23 LiteLLM / eMudhra assessment.

## Connection details to provide

- GCP project ID
- VM instance name and zone (for example `asia-northeast1-a`)
- Connection route: existing SSH, `gcloud compute ssh`, or IAP
- SSH / OS Login username, if already assigned
- Project directory on VM and container name (default: `extafia`)
- Whether this is production and whether the account already has Docker access

Do not paste private SSH keys, service-account JSON, access tokens, or `.env` contents into chat. Authenticate locally with your existing account. Project identifiers and connection details are sufficient to prepare the command.

## Scope of first connection

Read-only triage of host OS, container identity, image digests, installed package metadata, Python startup-hook paths and CA bundle labels. No package installation, restart, rebuild, credential rotation, or IAM change. Shell-based checks avoid triggering Python startup hooks.

The companion `vm-security-check.sh` uses `docker exec` to start a shell in an already running container. It does not start stopped containers. It does not print container environment values or application logs. Docker access is powerful; use an already authorized account. Do not grant new permissions just to run the script without reviewing the need.

## Connection templates

Use confirmed values in place of the placeholders. For an IAP connection:

```powershell
gcloud compute ssh VM_NAME --project PROJECT_ID --zone ZONE --tunnel-through-iap
```

For an existing direct connection, omit `--tunnel-through-iap`. A first `gcloud compute ssh` can create SSH keys or update SSH metadata; review that separately before proceeding. Verify the host fingerprint through a trusted source; do not disable host-key checking.

After connection is established, the script can be streamed through the existing SSH route without uploading a file. On Windows PowerShell, for example:

```powershell
Get-Content -Raw .\docs\vm-security-check.sh | gcloud.cmd compute ssh VM_NAME --project PROJECT_ID --zone ZONE --tunnel-through-iap --command "tr -d '\r' | bash -s -- extafia"
```

Run this from the repository directory. If Docker returns permission denied, stop and identify the intended administrative account; the script does not automatically use sudo.

## Interpretation and next evidence

- `litellm-1.107.0.dist-info` is an exposure indicator. Startup-hook names alone require content/hash review; legitimate `sitecustomize.py` and `.pth` files exist.
- Do not run Python or pip in a suspected environment. Preserve evidence and decide containment before making changes.
- Current metadata and missing markers do not exclude earlier installation or removed containers.
- CA label matches are hints, not cryptographic verification. Bundles without comments and embedded gRPC roots need further inspection.
- Follow up with CI build/deploy history, historical image digests, pip's vendored CA bundle, gRPC roots, host/venv environments, and narrowly scoped GCP audit records.
- Review logs separately with redaction: application logs may contain user content or credentials. Never dump `.env`, full `docker inspect`, or full Compose configuration into a shared report.

Local prerequisite check: `gcloud` and OpenSSH are available. Authentication, connectivity and VM authorization remain unverified.

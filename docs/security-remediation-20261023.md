# 2026-10-23 CA remediation

Target: project `discord-bot-20250213`, VM `extafia-discord-bot`, zone `us-central1-c`, container `extafia`.

## Confirmed before remediation

The running image was built on September 25. Shell-only inspection found pip 26.2.1 and certifi 2026.7.22. Both Python CA bundles included emSign ECC Root CA - G3. No LiteLLM distribution metadata or known startup-hook indicators were found in the inspected container paths or either discovered host venv. This is not proof of no historical compromise.

## Changes

- Bootstrap pip 26.2.2 using the SHA256-pinned wheel published in the Python security announcement.
- Require certifi >= 2026.10.19; refresh system CA packages and explicitly disable the G3 root in Debian's CA configuration.
- Point gRPC at the maintained system CA bundle.
- Validate effective CA bundles during the image build, and run pip dependency checks.
- Exclude environment files, venvs, common credentials, keys and logs from Docker context. Track `.dockerignore` in Git.
- Build CI images with `--pull --no-cache`.
- Update both discovered host venvs to pip 26.2.2 and certifi 2026.10.19. Their existing gRPC `roots.pem` files were backed up with `.before-20261023` suffixes and replaced with the verified system bundle. A future gRPC reinstall must recheck these roots.

## Verified deployment result

Running image: `extafia:security-20261023`, image ID `sha256:9f9ab531dc171502ac1a8c9b1f3e3adb545b021d3fbdaeeca096d4fc27fb0954`.

- Build and deployed runtime: all four effective CA bundles exclude the G3 root; pip dependency checks pass.
- Import checks and syntax parsing pass for 33 application Python files in the VM source tree.
- Discord and PyPI HTTPS requests pass.
- Bot logs confirm successful Discord login; container is running with zero restarts at verification.
- Firestore authenticated read through gRPC passes without printing document data.
- OpenAI authenticated models request passes; no generation request was made.
- Both host venvs pass the same CA verification script; the host system bundle was also parsed with OpenSSL to confirm G3 absence.

The initial VM remediation was performed before repository push or GHCR publication. It uses the VM's existing application source, with the security changes applied; it does not deploy unrelated local application changes.

References: [Python announcement](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576), [LiteLLM incident](https://docs.litellm.ai/blog/security-incident-oct-21-2026).

## Recovery and deployment

VM configuration backups and build logs: `/home/gba54230/security-backup-20261023` (restricted directory). Pre-remediation image retained as `extafia:rollback-20261023`. This old image remains vulnerable; use only for emergency recovery.

Initial deployment uses a local `extafia:security-20261023` image with pull disabled in the VM Compose file, so an older registry `latest` cannot silently undo the fix. Publish the fixed image through the reviewed CI workflow before returning the VM to registry-based deployment. Until that migration, a successful CI run does not mean the VM switched away from the locally pinned image.

## Remaining work

This patch addresses the identified CA exposure. It does not constitute a full compromise investigation. Historical CI/audit logs, a complete dependency lock with hashes, Action commit pinning, and migration to a non-root runtime remain separate work. The build still resolves unpinned application dependencies, so validate normal bot commands after deployment.

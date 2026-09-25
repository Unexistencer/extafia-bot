# Extafia Discord Bot

**Extafia** is a multilingual Discord bot featuring multiplayer arena battles, in-game currency and enchantments, image-based choice selection, and VHS effects for images and GIFs.

It runs on **Python 3.12 + discord.py**, uses **Firestore** for persistence, and includes a GitHub Actions workflow for deployment to a **GCP VM** with Docker Compose.

## Technical Highlights

- Designed and implemented the bot from application logic to cloud deployment and operation.
- Separated Discord command handling (`cogs/`) from core application logic (`service/`) for maintainability.
- Uses Firestore for persistent user/game data with an in-memory cache to reduce repeated database access.
- Implements image-based option extraction using the OpenAI API, including image preprocessing, result caching, and fallback handling.
- Supports English, Japanese, and written Cantonese through a centralized message resolver and translation dictionaries.
- Containerized with Docker and deployed to a GCP Compute Engine VM through GitHub Actions and GHCR.

## System Overview

- **Language:** Python 3.12 (Dockerized)
- **Framework:** `discord.py`
- **Database:** Firestore (GCP)
- **Authentication:** Google Application Default Credentials (ADC)
- **Deployment:** GitHub Actions → GHCR → GCP VM (Docker Compose)

Firestore stores user and game data, while in-memory caches reduce repeated reads within each bot process. Currency updates currently use separate read and write operations without Firestore transactions, so concurrent updates can conflict. Running multiple instances would require transactional updates and coordination between caches.

## Features

| Command | Description |
|----------|--------------|
| `/h` | Display command help |
| `/lang` | Set the interface language: English, Japanese, or written Cantonese (Traditional Chinese) |
| `/choose`, `.choose` | Select an option from text input or an image |
| `/arena` | Start a dice-based multiplayer battle with currency wagers and enchantment modifiers |
| `/enchant` | Generate enchantments that affect arena outcomes or rewards |
| `/vaal` | Apply a corruption effect to existing enchantments, with a chance of improvement or failure |
| `/stat` | Display user language, currency, enchantments, and developer privileges |
| `.vhs` | Apply a customizable VHS-style filter to an attached image or GIF, media in a replied-to message, or recent media |

See the [Command Guide](docs/commands.md) for usage examples, image effects, arena rules, and currency details.


## Project Structure

```text
extafia/
├── service/                # Core logic (arena, enchantment, etc.)
├── cogs/                   # Discord command modules
├── data/message.json       # Translation dictionaries
├── constants.py            # Dataclasses, enums, bitfield constants
├── user_data.py            # Firestore I/O + in-memory cache
├── msg_utils.py            # Multilingual message resolver
├── docker_tools.sh         # Docker build/run helper script
├── Dockerfile
├── compose.yaml            # VM deployment using GHCR images
└── requirements.txt
```
## Environment Setup

### 1. Configure Environment Variables

Create `.env` in the repository root. The following example uses the OCR implementation's default model:
```bash
DISCORD_TOKEN=your_discord_bot_token
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
OPEN_AI_API_KEY=your_openai_api_key
OPEN_AI_MODEL=gpt-4o-mini
TURTLE_AI_API_KEY=your_turtle_ai_api_key
TURTLE_AI_MODEL=gpt-4o
TZ=Asia/Tokyo
```

`OPEN_AI_API_KEY` is required for image-based choice selection. `OPEN_AI_MODEL` overrides the default OCR model (`gpt-4o-mini`); `.env.example` currently sets this override to `gpt-4o`. Optional `OPEN_AI_FALLBACK_MODEL` selects the additional text-extraction model and otherwise inherits the OCR model. `CHOOSE_OCR_CACHE_TTL_SECONDS` controls the image-result cache lifetime (default: 1200 seconds; minimum: 60 seconds).

### 2. Configure Application Default Credentials

```bash
gcloud auth application-default login
gcloud config set project your_gcp_project_id
```

For the Compute Engine deployment, attach a runtime service account with Firestore access.

### 3. Local Setup with Docker

From the repository root, use Bash to open the helper menu and select option `2` to build and run the container. This option also prunes unused Docker resources and replaces the existing `extafia` container.
```bash
# Local development: explicitly mount the ADC file created by gcloud
ADC_PATH="$HOME/.config/gcloud/application_default_credentials.json" bash ./docker_tools.sh
```
> The helper does not choose an ADC path automatically. Without a valid `ADC_PATH`, it relies on runtime default credentials (such as a Compute Engine service account):
> ```bash
> bash ./docker_tools.sh
> ```
> If your local ADC file is elsewhere, set `ADC_PATH` to its actual path.


## GCP Deployment Guide

On pushes to `main`, GitHub Actions builds Docker images, pushes them to GitHub Container Registry (GHCR), and deploys to a GCP VM over SSH by running `docker compose pull` and `docker compose up -d`. The deployment job requires the repository secrets `VM_HOST`, `VM_USER`, `VM_SSH_KEY`, and `VM_WORKDIR`; the VM working directory must already contain `compose.yaml` and `.env`.

Published image tags:

```bash
ghcr.io/unexistencer/extafia-bot:latest
ghcr.io/unexistencer/extafia-bot:<commit-sha>
```

### VM Deployment with Docker Compose

1. Prepare `.env` on the VM.
2. Log in to GHCR if the package is private:
```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```
3. Pull and start the bot:
```bash
docker compose pull
docker compose up -d
```
4. Update the running bot:
```bash
docker compose pull
docker compose up -d
```

The compose file uses `ghcr.io/unexistencer/extafia-bot:${IMAGE_TAG:-latest}`. Set `IMAGE_TAG` in `.env` if you want to pin a specific commit SHA instead of `latest`.

For Compute Engine, attach a service account with Firestore access. If using a local service-account JSON instead, mount it into the container and set `GOOGLE_APPLICATION_CREDENTIALS`.

## Localization

Supported languages:

- English (en)
- Japanese (jp)
- Written Cantonese (zh)

Localized messages are resolved via `msg_utils.py` using translation dictionaries in `data/message.json`.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

This project is licensed under the [MIT License](LICENSE).

## Contact / Support

Developer: 黒矢  
Discord: @ltkaz

For bug reports or feature requests, open an issue in this repository.

## Acknowledgments

Special thanks to @mfasa and @cloo for designing the Shing Coin artwork.

<img src="image/ShingCoin1.png" width="7%"><img src="image/ShingCoin2.png" width="7%"><img src="image/ShingCoin3.png" width="7%">

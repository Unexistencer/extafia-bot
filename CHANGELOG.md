# Changelog

- 2026.04.02 Release.
- 2026.04.28 Optimize `/choose` OCR flow with parser-first extraction, in-memory image-result cache, AI fallback gate, shorter prompts, cheaper default model, and local `random.choice` selection.
- 2026.06.16 Unblocked command by other bots, edited .gitignore
- 2026.07.06 Migrate deployment to GHCR and Docker Compose
- 2026.09.25 Updated README.md for portfolio, and optimized vhs effect
- 2026.11.12 Optimize /choose OCR: AI Parser will be default as ON for further accuracy.

## Unreleased

- Added opt-in experimental image tiling to `/choose` and `.choose`. The default 2 × 2 grid crops at full resolution and sends four sequential Vision requests, then merges the transcriptions for one AI parser pass when enabled and text is available.
- Made downscaling independently configurable, with the default 1800 px limit applied to the full image or to individual crops in tiled mode.
- Isolated OCR cache entries by preprocessing settings and routed incomplete tiled OCR through the existing error handler without caching partial results. Added tile, timing, and token-usage diagnostics.
- Added mocked OCR tests and documented the manual evaluation procedure. Tiling defaults to off pending owner review and live evaluation.

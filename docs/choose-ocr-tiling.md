# Experimental OCR tiling

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `CHOOSE_OCR_TILING_ENABLED` | `false` | Enable one Vision OCR request per tile. |
| `CHOOSE_OCR_TILE_ROWS` | `2` | Positive integer row count. |
| `CHOOSE_OCR_TILE_COLS` | `2` | Positive integer column count. |
| `CHOOSE_OCR_TILE_OVERLAP` | `0.15` | Per-side extension as a fraction of the nominal tile dimension, from zero up to but excluding one. |
| `CHOOSE_OCR_DOWNSCALE_ENABLED` | `true` | Resize the full image in single-image mode or each crop in tiled mode. |
| `CHOOSE_OCR_MAX_IMAGE_SIZE` | `1800` | Positive integer maximum longest-side length in pixels when downscaling is enabled. |

Boolean values accept `true` and `false` with case and surrounding whitespace ignored. Invalid booleans log a warning and use their defaults. Invalid numbers and grids over nine tiles trigger the existing OCR error. An enabled grid needs at least one image pixel per row and column.

The service applies EXIF orientation and converts to RGB at full resolution. Tiled mode crops in row-major order, then shrinks crops whose longest side exceeds the limit. Smaller crops retain their dimensions. Nominal boundaries divide each axis using integer pixel coordinates. Each tile extends across internal edges by the overlap ratio times the nominal tile dimension, rounded to the nearest pixel and clipped to the image. For a 2160 × 2880 image with a 2 × 2 grid and overlap 0.15, each 1080 × 1440 nominal tile extends 162 px horizontally and 216 px vertically. The resulting tiles are 1242 × 1656 and share 324 px horizontally or 432 px vertically.

Vision processes tiles sequentially. Completed transcriptions are joined verbatim with two newlines between tiles and passed once to the existing AI parser if enabled and the transcription contains text. Empty completed tiles are counted separately. An API error or incomplete Vision response stops at the affected tile, reports an OCR error, and leaves the cache untouched. The combined OCR and parser cache retains its existing TTL and is isolated by preprocessing, OCR model and detail, parser settings, and engine versions.

## Manual evaluation

Use the same original 2160 × 2880 directory image and a reference list of the 18 restaurant names. Set `OPEN_AI_MODEL=gpt-4o`, keep the AI parser enabled with the same parser model throughout, and fix overlap at 0.15 and the size limit at 1800. Keep the prompts, image detail and output token limits fixed.

| Trial | Tiling | Downscale | Grid | Logical requests with parser |
|---|---|---|---|---:|
| A | Off | On | — | 2 |
| B | Off | Off | — | 2 |
| C | On | Off | 2 × 2 | 5 |
| D | On | On | 2 × 2 | 5 |
| E | On | Off | 2 × 3 | 7 |

A and B were performed previously. Prioritize C and E. D uses the same tile sizes as C because the 1656 px longest side of each tile is below the limit. Request counts assume successful OCR with nonempty merged text and exclude SDK retries.

1. Set the trial configuration in a local or staging environment. Start a fresh process for each repeat to clear the in-memory cache. Use the same image in `/choose` or `.choose` and confirm the log records a cache miss. For direct service evaluation, run the following from the repository root and supply the original image path.

   ```powershell
   python -c "from dotenv import load_dotenv; load_dotenv(); import sys; from service.ocr_service import extract_options_from_path; print(extract_options_from_path(sys.argv[1]))" "C:/path/to/directory.jpg"
   ```

2. Repeat each configuration three times where practical. For each run, compare the merged OCR and final options with the reference list. Record correct names, incorrect spellings of identifiable entries, missing reference names, hallucinated options with no corresponding entry, and duplicate occurrences. Inspect duplicates in the merged OCR as well as the final options so exact deduplication does not hide OCR repeats.
3. Record Vision and parser request counts, sum input and output tokens separately from the INFO usage lines, and record OCR, parser and total elapsed time. DEBUG logs show crop bounds, image sizes, tile request durations and status, and the tile, merged and parser text. Use those transcriptions to identify whether an error first appeared in Vision or in the parser.

## Implementation report

| File | Change |
|---|---|
| `service/ocr_service.py` | Configuration validation, Pillow crop iteration, sequential OCR, merge and failure handling, diagnostics, and OCR cache version bump. |
| `tests/test_ocr_service.py` | Mocked API tests and image geometry checks. |
| `.env.example`, `README.md` | Configuration defaults and documentation link. |
| `CHANGELOG.md` | Unreleased maintenance summary. |
| `docs/choose-ocr-tiling.md` | Configuration, evaluation procedure and implementation report. |

All 23 tests passed with `python -m unittest discover -s tests -v`, including the 12 existing tests. The suite uses mocked OpenAI responses. Both commands use the shared OCR service and existing error handling. Live Discord and restaurant accuracy evaluation are pending owner review.

Overlap can repeat names or leave partial names near tile edges. Exact deduplication and the existing 30-option cap still apply. Vision can still misread or hallucinate text, and the parser has its existing output limit. Overlapping pixels and repeated OCR prompts can increase image and text input tokens, and a longer transcription can increase parser input tokens. Sequential calls add their durations, including SDK retries. Compare measured tokens and elapsed time before enabling tiling in production.

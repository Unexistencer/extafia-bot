import base64
import hashlib
from io import BytesIO
import os
import re
import time
from dataclasses import dataclass
from typing import Iterator, List

from openai import OpenAI
from PIL import Image, ImageOps

from logger import logger

MAX_OPTIONS = 30
DEFAULT_OCR_MODEL = "gpt-4o"
DEFAULT_AI_FALLBACK_MODEL = "gpt-4o"
DEFAULT_CACHE_TTL_SECONDS = 20 * 60
OCR_ENGINE_VERSION = "openai-vision-v3"
PARSER_VERSION = "choose-parser-v3"
OCR_IMAGE_DETAIL = "high"
MAX_OCR_TILES = 9

_CJK = (
    r"\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\u3040-\u309f"  # Hiragana
    r"\u30a0-\u30ff"  # Katakana
    r"\uac00-\ud7af"  # Hangul
)

ONLY_SYMBOLS_RE = re.compile(r"^[^\w]+$", re.UNICODE)
LIST_PREFIX_RE = re.compile(r"^\s*(?:\d{1,3}|[A-Za-z])[\.\)]\s+")
BULLET_PREFIX_RE = re.compile(r"^\s*(?:[\-\u2022\u30fb\u00b7\u25cf\u25cb\u25aa\u25ab\u25b6\u25ba\u3001])\s*")
_CJK_SPACE_RE = re.compile(fr"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")
_MULTISPACE_RE = re.compile(r"[ \t]+")
_SPLIT_RE = re.compile(r"[,、，/|]")
_STANDALONE_ORDINAL_RE = re.compile(r"^(?:\d{1,3}|[A-Za-z])$")
_OPENAI_CLIENT: OpenAI | None = None
_OCR_CACHE: dict[str, "OcrCacheEntry"] = {}


@dataclass(frozen=True)
class OcrPreprocessing:
    tiling_enabled: bool = False
    rows: int = 2
    cols: int = 2
    overlap: float = 0.15
    downscale_enabled: bool = True
    max_image_size: int = 1800

    def __post_init__(self) -> None:
        if min(self.rows, self.cols) < 1 or self.rows * self.cols > MAX_OCR_TILES:
            raise ValueError(f"OCR grid must contain 1 to {MAX_OCR_TILES} tiles")
        if not 0 <= self.overlap < 1:
            raise ValueError("OCR tile overlap must be in [0, 1)")
        if self.max_image_size < 1:
            raise ValueError("OCR maximum image size must be positive")


class IncompleteTiledOcrError(RuntimeError):
    """At least one tile could not be transcribed."""


@dataclass(frozen=True)
class OcrResult:
    ocr_text: str
    options: List[str]
    source: str
    cache_hit: bool = False


@dataclass
class OcrCacheEntry:
    ocr_text: str
    options: List[str]
    source: str
    created_at: float

    def to_result(self) -> OcrResult:
        return OcrResult(
            ocr_text=self.ocr_text,
            options=list(self.options),
            source=self.source,
            cache_hit=True,
        )


def _downscale(image: Image.Image, max_side: int = 1800) -> Image.Image:
    w, h = image.size
    m = max(w, h)
    if m <= max_side:
        return image
    return image.resize((max(1, w * max_side // m), max(1, h * max_side // m)))


def _fix_cjk_spacing(text: str) -> str:
    """Clean unnecessary spaces in options."""
    return _CJK_SPACE_RE.sub("", text)


def _normalize_spaces(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = _MULTISPACE_RE.sub(" ", text)
    return _fix_cjk_spacing(text).strip()


def _orient_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    return image if image.mode == "RGB" else image.convert("RGB")


def _resize_for_ocr(image: Image.Image, config: OcrPreprocessing) -> Image.Image:
    return _downscale(image, config.max_image_size) if config.downscale_enabled else image


def preprocess_image(image: Image.Image) -> Image.Image:
    """Prepare a single full image for OCR."""
    return _resize_for_ocr(_orient_rgb(image), _get_preprocessing())


def iter_image_tiles(
    image: Image.Image, rows: int = 2, cols: int = 2, overlap: float = 0.15
) -> Iterator[tuple[tuple[int, int, int, int], Image.Image]]:
    """Yield (crop box, tile) in row order, extending both sides of internal seams."""
    OcrPreprocessing(rows=rows, cols=cols, overlap=overlap)
    width, height = image.size
    if cols > width or rows > height:
        raise ValueError("OCR grid has more rows or columns than the image has pixels")
    extend_x = round(overlap * width / cols)
    extend_y = round(overlap * height / rows)
    for row in range(rows):
        top = max(0, row * height // rows - extend_y) if row else 0
        bottom = min(height, (row + 1) * height // rows + extend_y)
        for col in range(cols):
            left = max(0, col * width // cols - extend_x) if col else 0
            right = min(width, (col + 1) * width // cols + extend_x)
            box = (left, top, right, bottom)
            yield box, image.crop(box)


def _get_bool(name: str, default: bool, *, invalid: bool | None = None) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"true", "false"}:
        return value == "true"
    fallback = default if invalid is None else invalid
    logger.warning("[choose-config] Invalid %s; using %s", name, str(fallback).lower())
    return fallback


def _get_preprocessing() -> OcrPreprocessing:
    return OcrPreprocessing(
        tiling_enabled=_get_bool("CHOOSE_OCR_TILING_ENABLED", False),
        rows=int(os.getenv("CHOOSE_OCR_TILE_ROWS", "2")),
        cols=int(os.getenv("CHOOSE_OCR_TILE_COLS", "2")),
        overlap=float(os.getenv("CHOOSE_OCR_TILE_OVERLAP", "0.15")),
        downscale_enabled=_get_bool("CHOOSE_OCR_DOWNSCALE_ENABLED", True),
        max_image_size=int(os.getenv("CHOOSE_OCR_MAX_IMAGE_SIZE", "1800")),
    )


def _get_api_key() -> str:
    api_key = os.getenv("OPEN_AI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPEN_AI_API_KEY or OPENAI_API_KEY for OCR.")
    return api_key


def _get_model() -> str:
    return os.getenv("OPEN_AI_MODEL") or DEFAULT_OCR_MODEL


def _get_ai_fallback_model() -> str:
    return (
        os.getenv("OPEN_AI_FALLBACK_MODEL")
        or _get_model()
        or DEFAULT_AI_FALLBACK_MODEL
    )


def _get_cache_ttl_seconds() -> int:
    raw = os.getenv("CHOOSE_OCR_CACHE_TTL_SECONDS")
    if raw and raw.isdigit():
        return max(60, int(raw))
    return DEFAULT_CACHE_TTL_SECONDS


def _get_client() -> OpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI(api_key=_get_api_key())
    return _OPENAI_CLIENT


def _image_to_data_url(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    payload = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def _log_usage(stage: str, response, request: str = "") -> None:
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info("[%s] %s input_tokens=%s output_tokens=%s total_tokens=%s",
                    stage, request, usage.input_tokens, usage.output_tokens, usage.total_tokens)


def _request_ocr(image: Image.Image, request: str, *, tiled: bool) -> str:
    response = _get_client().responses.create(
        model=_get_model(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
                        OCR this image.
                        Return visible text only, preserving line breaks.
                        No explanations.
                        """,
                    },
                    {
                        "type": "input_image",
                        "image_url": _image_to_data_url(image),
                        "detail": OCR_IMAGE_DETAIL,
                    },
                ],
            },
        ],
        max_output_tokens=2048,
    )
    status = getattr(response, "status", None)
    details = getattr(response, "incomplete_details", None)
    text = response.output_text or ""
    logger.debug("[choose-ocr] %s status=%s incomplete_reason=%s empty=%s raw_output:\n%s",
                 request, status, getattr(details, "reason", None), not text.strip(), text)
    _log_usage("choose-ocr", response, request)
    if tiled and status not in (None, "completed"):
        raise IncompleteTiledOcrError("Vision response did not complete")
    return text


def extract_text_from_pil(image: Image.Image, config: OcrPreprocessing | None = None) -> str:
    config = config if config is not None else _get_preprocessing()
    started = time.perf_counter()
    image = _orient_rgb(image)
    total = config.rows * config.cols if config.tiling_enabled else 1
    logger.info("[choose-ocr] original_size=%s config=%s tiles=%d", image.size, config, total)
    tiles = (
        iter_image_tiles(image, config.rows, config.cols, config.overlap)
        if config.tiling_enabled else [((0, 0, *image.size), image)]
    )
    outputs = []
    failed = 0
    empty = 0
    try:
        for index, (box, tile) in enumerate(tiles, start=1):
            request = f"tile={index}/{total}"
            processed = _resize_for_ocr(tile, config)
            logger.debug("[choose-ocr] %s crop_box=%s original_size=%s processed_size=%s downscaled=%s",
                         request, box, tile.size, processed.size, processed is not tile)
            request_started = time.perf_counter()
            try:
                text = _request_ocr(processed, request, tiled=config.tiling_enabled)
            except Exception as exc:
                failed += 1
                logger.warning("[choose-ocr] %s failed error_type=%s http_status=%s",
                               request, type(exc).__name__, getattr(exc, "status_code", None))
                if config.tiling_enabled:
                    raise IncompleteTiledOcrError(f"Tiled OCR incomplete at {request}") from exc
                raise
            finally:
                logger.debug("[choose-ocr] %s duration_ms=%.0f",
                             request, (time.perf_counter() - request_started) * 1000)
            outputs.append(text)
            empty += not text.strip()
    finally:
        logger.info("[choose-ocr] tiles=%d succeeded=%d empty=%d failed=%d unattempted=%d duration_ms=%.0f",
                    total, len(outputs), empty, failed, total - len(outputs) - failed,
                    (time.perf_counter() - started) * 1000)
    if not config.tiling_enabled:
        return outputs[0].strip()
    merged = "\n\n".join(outputs)
    logger.debug("[choose-ocr] merged_text_len=%d merged_output:\n%s", len(merged), merged)
    return merged


def _is_standalone_ordinal(line: str) -> bool:
    return bool(_STANDALONE_ORDINAL_RE.match(line))


def _strip_list_prefix(line: str) -> str:
    line = LIST_PREFIX_RE.sub("", line, count=1)
    line = BULLET_PREFIX_RE.sub("", line, count=1)
    return line.strip()


def _is_noise_option(line: str) -> bool:
    if not line:
        return True
    if ONLY_SYMBOLS_RE.match(line):
        return True
    return False


def _should_split_line(line: str) -> bool:
    if not _SPLIT_RE.search(line):
        return False

    parts = [p.strip() for p in _SPLIT_RE.split(line) if p.strip()]
    if len(parts) < 2 or len(parts) > MAX_OPTIONS:
        return False

    average_len = sum(len(p) for p in parts) / len(parts)
    long_parts = sum(1 for p in parts if len(p) > 12)
    return average_len <= 8 and long_parts == 0


def _prepare_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw_line in text.splitlines():
        line = _normalize_spaces(raw_line)
        if line:
            lines.append(line)
    return lines


def parse_options_from_text(text: str) -> List[str]:
    lines = _prepare_lines(text)
    non_ordinals = sum(1 for line in lines if not _is_standalone_ordinal(line))

    options: List[str] = []
    seen = set()
    for index, raw_line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if (
            _is_standalone_ordinal(raw_line)
            and non_ordinals > 0
            and next_line
            and not _is_standalone_ordinal(next_line)
        ):
            continue

        line = _normalize_spaces(_strip_list_prefix(raw_line))
        candidates = [_normalize_spaces(p) for p in _SPLIT_RE.split(line)] if _should_split_line(line) else [line]

        for candidate in candidates:
            candidate = _normalize_spaces(_strip_list_prefix(candidate))
            if _is_noise_option(candidate):
                continue
            if candidate in seen:
                continue
            options.append(candidate)
            seen.add(candidate)
            if len(options) >= MAX_OPTIONS:
                return options

    return options


def _get_ai_parser_enabled() -> bool:
    """Accept true/false (case-insensitive); invalid values disable AI."""
    return _get_bool("CHOOSE_AI_PARSER_ENABLED", True, invalid=False)


def should_use_ai_fallback(text: str, options: List[str], force_ai: bool) -> bool:
    """Compatibility helper: force_ai=False opts out; option count is ignored."""
    return _get_ai_parser_enabled() and force_ai and bool(text.strip())


def extract_options_with_ai_fallback(text: str) -> List[str]:
    prompt = """
    Extract only entries that a user would reasonably select or choose.
    Identify the primary selectable entities rather than their categories, attributes, or descriptions.
    When a specific entity name and its category are both present, prefer the specific entity name.

    For example:
    - Restaurant name over cuisine type.
    - Dish name over ingredients.
    - Product name over product category.
    - Character name over character class.

    If the category itself is the selectable option, retain it.

    Ignore prices, opening hours, descriptions, notes, metadata, and other supplementary information.

    Preserve the original text exactly.
    Do not infer, correct, translate, or invent names.

    Return one entry per line.
    Do not add numbering, bullet points, headings, or explanations.

    Output only the extracted entries.
    """
    response = _get_client().responses.create(
        model=_get_ai_fallback_model(),
        input=[
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        max_output_tokens=1024,
    )

    cleaned = (response.output_text or "").strip()
    _log_usage("choose-parser", response)

    logger.info(
        f"[choose-ocr] AI parser text_len={len(cleaned)}"
    )

    logger.debug("[choose-parser] raw_output:\n%s", cleaned)

    return parse_options_from_text(cleaned)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_key(
    image_hash: str, ai_enabled: bool | None = None, preprocessing: OcrPreprocessing | None = None
) -> str:
    if ai_enabled is None:
        ai_enabled = _get_ai_parser_enabled()
    preprocessing = preprocessing if preprocessing is not None else _get_preprocessing()
    config = repr((preprocessing, _get_model(), OCR_IMAGE_DETAIL, ai_enabled,
                   _get_ai_fallback_model() if ai_enabled else None, MAX_OPTIONS))
    config_hash = hashlib.sha256(config.encode("utf-8")).hexdigest()
    return f"{image_hash}:{OCR_ENGINE_VERSION}:{PARSER_VERSION}:{config_hash}"


def _get_cached_result(key: str) -> OcrResult | None:
    entry = _OCR_CACHE.get(key)
    if entry is None:
        return None
    age = time.time() - entry.created_at
    if age > _get_cache_ttl_seconds():
        _OCR_CACHE.pop(key, None)
        return None
    return entry.to_result()


def _put_cached_result(key: str, result: OcrResult) -> None:
    _OCR_CACHE[key] = OcrCacheEntry(
        ocr_text=result.ocr_text,
        options=list(result.options),
        source=result.source,
        created_at=time.time(),
    )

    now = time.time()
    expired = [
        cache_key
        for cache_key, entry in _OCR_CACHE.items()
        if now - entry.created_at > _get_cache_ttl_seconds()
    ]
    for cache_key in expired:
        _OCR_CACHE.pop(cache_key, None)


def extract_options_result_from_bytes(
    data: bytes,
    suffix: str = ".png",
    force_ai_fallback: bool = True,
) -> OcrResult:
    """OCR then AI parsing by default; legacy force_ai_fallback=False opts out.

    CHOOSE_AI_PARSER_ENABLED=false always disables the AI parser.
    """
    started = time.perf_counter()
    ai_enabled = _get_ai_parser_enabled() and force_ai_fallback
    preprocessing = _get_preprocessing()
    image_hash = _sha256(data)
    key = _cache_key(image_hash, ai_enabled, preprocessing)
    cached = _get_cached_result(key)
    if cached is not None:
        logger.info(
            f"[choose-ocr] cache hit hash={image_hash[:12]} "
            f"ai_enabled={ai_enabled} ai_attempted=False "
            f"source={cached.source} rule_fallback={cached.source == 'rule_parser_fallback'} "
            f"options={len(cached.options)} config={preprocessing}"
        )
        return cached

    logger.info(f"[choose-ocr] cache miss hash={image_hash[:12]} suffix={suffix}")
    with Image.open(BytesIO(data)) as image:
        text = extract_text_from_pil(image, preprocessing)

    parser_started = time.perf_counter()
    options = []
    source = "rule_parser"
    ai_attempted = ai_enabled and bool(text.strip())
    if ai_attempted:
        try:
            options = extract_options_with_ai_fallback(text)
        except Exception:
            # Avoid logging exception messages, which may contain request details.
            logger.warning("[choose-parser] AI parser failed; using rule parser")
        source = "ai_parser" if options else "rule_parser_fallback"
    if not options:
        options = parse_options_from_text(text)

    logger.info(
        f"[choose-parser] ai_enabled={ai_enabled} ai_attempted={ai_attempted} "
        f"source={source} rule_fallback={source == 'rule_parser_fallback'} "
        f"text_len={len(text)} options={len(options)} "
        f"duration_ms={(time.perf_counter() - parser_started) * 1000:.0f}"
    )

    result = OcrResult(ocr_text=text, options=options, source=source, cache_hit=False)
    _put_cached_result(key, result)
    logger.info(
        "[choose-ocr] cached hash=%s source=%s options=%d total_duration_ms=%.0f",
        image_hash[:12], source, len(options), (time.perf_counter() - started) * 1000,
    )
    return result


def extract_options_from_path(image_path: str) -> List[str]:
    with open(image_path, "rb") as f:
        data = f.read()
    result = extract_options_result_from_bytes(data)
    logger.info(
        f"[choose-ocr] Parsed {len(result.options)} options from path "
        f"source={result.source} cache_hit={result.cache_hit}"
    )
    return result.options


def extract_options_from_bytes(data: bytes, suffix: str = ".png") -> List[str]:
    result = extract_options_result_from_bytes(data, suffix=suffix)
    logger.info(
        f"[choose-ocr] Parsed {len(result.options)} options from bytes "
        f"(suffix={suffix}, size={len(data)}, source={result.source}, cache_hit={result.cache_hit})"
    )
    return result.options


def is_usable_options(options: List[str]) -> bool:
    return len(options) >= 2

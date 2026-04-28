import base64
import hashlib
from io import BytesIO
import os
import re
import time
from dataclasses import dataclass
from typing import List

from openai import OpenAI
from PIL import Image, ImageOps

from logger import logger

MAX_OPTIONS = 30
DEFAULT_OCR_MODEL = "gpt-4o-mini"
DEFAULT_AI_FALLBACK_MODEL = "gpt-4o-mini"
DEFAULT_CACHE_TTL_SECONDS = 20 * 60
MIN_AI_FALLBACK_TEXT_LENGTH = 8
OCR_ENGINE_VERSION = "openai-vision-v2"
PARSER_VERSION = "choose-parser-v2"

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


def _preview_text(text: str, limit: int = 500) -> str:
    text = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _preview_options(options: List[str], limit: int = 8) -> str:
    shown = options[:limit]
    suffix = "" if len(options) <= limit else f", ...(+{len(options) - limit})"
    return f"{shown}{suffix}"


def _downscale(image: Image.Image, max_side: int = 1800) -> Image.Image:
    w, h = image.size
    m = max(w, h)
    if m <= max_side:
        return image
    scale = max_side / m
    return image.resize((int(w * scale), int(h * scale)))


def _fix_cjk_spacing(text: str) -> str:
    """Clean unnecessary spaces in options."""
    return _CJK_SPACE_RE.sub("", text)


def _normalize_spaces(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = _MULTISPACE_RE.sub(" ", text)
    return _fix_cjk_spacing(text).strip()


def preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = _downscale(image)
    return image.convert("RGB")


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


def _get_image_detail() -> str:
    return os.getenv("OPEN_AI_OCR_DETAIL") or "low"


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


def extract_text_from_pil(image: Image.Image) -> str:
    image = preprocess_image(image)
    response = _get_client().responses.create(
        model=_get_model(),
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "OCR this image. Return visible text only, preserving line breaks. No explanations.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Read the text."},
                    {
                        "type": "input_image",
                        "image_url": _image_to_data_url(image),
                        "detail": _get_image_detail(),
                    },
                ],
            },
        ],
        max_output_tokens=400,
    )
    text = (response.output_text or "").strip()
    logger.info(f"[choose-ocr] OpenAI OCR text_len={len(text)}")
    return text


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


def _looks_messy(text: str, options: List[str]) -> bool:
    if len(options) >= 2:
        return False
    cleaned_len = len(_normalize_spaces(text))
    if cleaned_len < MIN_AI_FALLBACK_TEXT_LENGTH:
        return False
    symbol_count = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
    return symbol_count >= 3 or len(_prepare_lines(text)) >= 2


def should_use_ai_fallback(text: str, options: List[str], force_ai: bool = False) -> bool:
    if force_ai:
        return bool(text.strip())
    if len(options) >= 2:
        return False
    return _looks_messy(text, options)


def extract_options_with_ai_fallback(text: str) -> List[str]:
    response = _get_client().responses.create(
        model=_get_ai_fallback_model(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "從以下 OCR 文字抽出候選選項，每行一個，只輸出選項，不要解釋。\n\n"
                            f"{_preview_text(text, limit=3000)}"
                        ),
                    }
                ],
            }
        ],
        max_output_tokens=250,
    )
    cleaned = (response.output_text or "").strip()
    logger.info(f"[choose-ocr] AI fallback text_len={len(cleaned)}")
    return parse_options_from_text(cleaned)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_key(image_hash: str) -> str:
    return f"{image_hash}:{OCR_ENGINE_VERSION}:{PARSER_VERSION}"


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
    force_ai_fallback: bool = False,
) -> OcrResult:
    image_hash = _sha256(data)
    key = _cache_key(image_hash)
    cached = _get_cached_result(key)
    if cached is not None:
        logger.info(
            f"[choose-ocr] cache hit hash={image_hash[:12]} "
            f"source={cached.source} options={len(cached.options)}"
        )
        return cached

    logger.info(f"[choose-ocr] cache miss hash={image_hash[:12]} suffix={suffix}")
    with Image.open(BytesIO(data)) as image:
        text = extract_text_from_pil(image)

    options = parse_options_from_text(text)
    source = "parser"
    use_ai = should_use_ai_fallback(text, options, force_ai=force_ai_fallback)
    logger.info(
        f"[choose-ocr] parser text_len={len(text)} options={len(options)} "
        f"use_ai_fallback={use_ai}"
    )

    if use_ai:
        ai_options = extract_options_with_ai_fallback(text)
        if ai_options:
            options = ai_options
            source = "ai_fallback"

    result = OcrResult(ocr_text=text, options=options, source=source, cache_hit=False)
    _put_cached_result(key, result)
    logger.info(
        f"[choose-ocr] cached hash={image_hash[:12]} source={source} "
        f"options={len(options)} preview={_preview_options(options)}"
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

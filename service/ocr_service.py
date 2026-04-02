import base64
from io import BytesIO
import os
import re
from typing import List

from openai import OpenAI
from PIL import Image, ImageOps
from logger import logger

MAX_OPTIONS = 30
MIN_LINE_LENGTH = 2
DEFAULT_OCR_MODEL = "gpt-4o"

_CJK = (
    r"\u4e00-\u9fff"   # CJK Unified Ideographs
    r"\u3040-\u309f"   # Hiragana
    r"\u30a0-\u30ff"   # Katakana
    r"\uac00-\ud7af"   # Hangul
)

ONLY_SYMBOLS_RE = re.compile(r"^[\W_]+$")
LEADING_MARK_RE = re.compile("^[\\s\\-\\*\\d\\.\\)\\]\\u2022\\u00b7\\u25cf\\u25b6\\u25ba\\u3001]{1,6}")
_CJK_SPACE_RE = re.compile(fr"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")
_OPENAI_CLIENT: OpenAI | None = None


def _preview_text(text: str, limit: int = 500) -> str:
    text = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


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


def preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = _downscale(image)
    return image.convert("RGB")


def _get_api_key() -> str:
    api_key = os.getenv("OPEN_AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPEN_AI_API_KEY or OPENAI_API_KEY for OCR.")
    return api_key


def _get_model() -> str:
    return os.getenv("OPEN_AI_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_OCR_MODEL


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
                        "text": (
                            "Perform OCR on the image.\n"
                            "Extract all readable text items that could represent selectable options.\n"
                            "Each distinct option must be returned on its own line.\n"
                            "Do not merge multiple items into one line.\n"
                            "Do not add numbering, explanations, or extra words.\n"
                            "Ignore decorative elements, prices, and repeated labels if they appear.\n"
                            "Return only the extracted text."
                            ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Read this image and output every visible choice item.",
                    },
                    {
                        "type": "input_image",
                        "image_url": _image_to_data_url(image),
                        "detail": "high",
                    },
                ],
            },
        ],
        max_output_tokens=400,
    )
    text = (response.output_text or "").strip()
    logger.info(f"[choose-ocr] OpenAI OCR raw_text='{_preview_text(text)}'")
    return text


def parse_options_from_text(text: str) -> List[str]:
    options: List[str] = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = _fix_cjk_spacing(line)
        if len(line) < MIN_LINE_LENGTH:
            continue
        if ONLY_SYMBOLS_RE.match(line):
            continue
        line = LEADING_MARK_RE.sub("", line).strip()
        if not line or line in seen:
            continue
        options.append(line)
        seen.add(line)
        if len(options) >= MAX_OPTIONS:
            break
    return options


def extract_options_from_path(image_path: str) -> List[str]:
    with Image.open(image_path) as image:
        text = extract_text_from_pil(image)
    options = parse_options_from_text(text)
    logger.info(f"[choose-ocr] Parsed {len(options)} options from path: {options}")
    return options


def extract_options_from_bytes(data: bytes, suffix: str = ".png") -> List[str]:
    source_suffix = suffix
    with Image.open(BytesIO(data)) as image:
        text = extract_text_from_pil(image)
    options = parse_options_from_text(text)
    logger.info(
        f"[choose-ocr] Parsed {len(options)} options from bytes "
        f"(suffix={source_suffix}, size={len(data)}): {options}"
    )
    return options


def is_usable_options(options: List[str]) -> bool:
    return len(options) >= 2

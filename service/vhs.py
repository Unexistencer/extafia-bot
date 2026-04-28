from __future__ import annotations

import random
import math
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageSequence


MAX_SIDE = 1400
JPEG_QUALITY = 92
MIN_JPEG_QUALITY = 60
MAX_OUTPUT_BYTES = 20 * 1024 * 1024
PREPROCESS_TRIGGER_BYTES = 3 * 1024 * 1024
PREPROCESS_STATIC_MAX_SIDE = MAX_SIDE
PREPROCESS_GIF_MAX_SIDE = 960

DEFAULT_STRENGTH = 35
MIN_STRENGTH = 1
MAX_STRENGTH = 100

DEFAULT_NOISE = 50
MIN_NOISE = 0
MAX_NOISE = 100

DEFAULT_SCANLINE = 800
MIN_SCANLINE = 0
MAX_SCANLINE = 1000

DEFAULT_RGB_SHIFT = 120
MIN_RGB_SHIFT = 0
MAX_RGB_SHIFT = 200

DEFAULT_SHIFT_SCALE = 0.6
DEFAULT_NOISE_Y_DENSITY = 1.8
DEFAULT_TRACKING_NOISE = 100

DEFAULT_LOFI = 100
MIN_LOFI = 1
MAX_LOFI = 100
MIN_LOFI_SCALE = 0.46
MAX_LOFI_SCALE = 0.998

GIF_FRAME_LIMIT = 120
ADAPTIVE_PALETTE = Image.ADAPTIVE if hasattr(Image, "ADAPTIVE") else Image.Palette.ADAPTIVE

def _resize_to_fit(image: Image.Image, max_side: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image

    scale = max_side / longest
    resized = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(resized, Image.Resampling.LANCZOS)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _scale(value: float, strength: int) -> float:
    return value * (strength / DEFAULT_STRENGTH)


def _clamp_strength(strength: int | None) -> int:
    if strength is None:
        return DEFAULT_STRENGTH
    return _clamp(strength, MIN_STRENGTH, MAX_STRENGTH)


def _downscale(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    return _resize_to_fit(image, max_side)


def _lofi_scale(lofi: int) -> float:
    factor = _clamp(lofi, MIN_LOFI, MAX_LOFI) / MAX_LOFI
    return MAX_LOFI_SCALE - (MAX_LOFI_SCALE - MIN_LOFI_SCALE) * factor


def _apply_lofi_softening(image: Image.Image, lofi: int) -> Image.Image:
    width, height = image.size
    scale = _lofi_scale(lofi)
    reduced = (
        max(1, int(width * scale)),
        max(1, int(height * scale)),
    )
    if reduced == image.size:
        return image

    lowered = image.resize(reduced, Image.Resampling.BILINEAR)
    return lowered.resize(image.size, Image.Resampling.NEAREST)


def _preprocess_input_image(image: Image.Image, input_bytes_len: int, is_animated: bool) -> Image.Image:
    preprocess_side = PREPROCESS_GIF_MAX_SIDE if is_animated else PREPROCESS_STATIC_MAX_SIDE
    longest = max(image.size)
    if input_bytes_len < PREPROCESS_TRIGGER_BYTES and longest <= preprocess_side:
        return image
    return _resize_to_fit(image, preprocess_side)


def _normalize_frame(frame: Image.Image) -> Image.Image:
    if frame.mode in ("RGBA", "LA") or ("transparency" in frame.info):
        background = Image.new("RGBA", frame.size, (0, 0, 0, 255))
        background.alpha_composite(frame.convert("RGBA"))
        return background.convert("RGB")
    return frame.convert("RGB")


def _make_band_shift_layer(
    base: Image.Image,
    rng: random.Random,
    strength: int,
    rgb_shift: int,
) -> Image.Image:
    width, height = base.size
    shifted = Image.new("RGB", (width, height))
    cursor = 0
    min_band = max(2, int(_scale(6, strength)))
    max_band = max(min_band, int(_scale(26, strength)))
    max_offset = max(1, int(_scale(14, strength) * DEFAULT_SHIFT_SCALE * (rgb_shift / DEFAULT_RGB_SHIFT)))

    while cursor < height:
        band_height = min(height - cursor, rng.randint(min_band, max_band))
        offset = rng.randint(-max_offset, max_offset)
        band = base.crop((0, cursor, width, cursor + band_height))
        shifted.paste(ImageChops.offset(band, offset, 0), (0, cursor))
        cursor += band_height

    return shifted


def _make_scanlines(
    size: tuple[int, int],
    rng: random.Random,
    strength: int,
    scanline: int,
) -> Image.Image:
    width, height = size
    scanline_factor = scanline / DEFAULT_SCANLINE
    even_min = max(4, int(_scale(18, strength) * scanline_factor))
    even_max = max(even_min, int(_scale(34, strength) * scanline_factor))
    odd_min = max(2, int(_scale(8, strength) * scanline_factor))
    odd_max = max(odd_min, int(_scale(18, strength) * scanline_factor))
    column = Image.new("L", (1, height))
    column.putdata(
        [
            min(255, rng.randint(even_min, even_max) if y % 2 == 0 else rng.randint(odd_min, odd_max))
            for y in range(height)
        ]
    )
    return column.resize((width, height), Image.Resampling.BILINEAR)


def _make_noise(
    size: tuple[int, int],
    rng: random.Random,
    strength: int,
    noise_strength: int,
) -> Image.Image:
    width, height = size
    noise_factor = noise_strength / DEFAULT_NOISE
    spread = max(4, int(_scale(28, strength) * noise_factor))
    source_height = max(height, int(height * DEFAULT_NOISE_Y_DENSITY))
    noise = Image.effect_noise((width, source_height), max(1, spread * 1.8))
    noise = noise.resize((width, height), Image.Resampling.LANCZOS)
    offset = rng.randint(-spread // 2, spread // 2)
    noise = noise.point(lambda value: max(0, min(255, int(value + offset - 10))))
    noise = noise.filter(
        ImageFilter.GaussianBlur(radius=max(0.1, _scale(0.35, strength) * max(0.5, noise_factor)))
    )
    return noise.convert("RGB")


def _apply_line_jolt(
    image: Image.Image,
    rng: random.Random,
    strength: int,
    rgb_shift: int,
) -> Image.Image:
    width, height = image.size
    jolted = image.copy()
    burst_count = 1 if rng.random() < 0.72 else 2
    max_offset = max(10, int(_scale(42, strength) * max(0.7, rgb_shift / DEFAULT_RGB_SHIFT)))

    for _ in range(burst_count):
        band_height = rng.randint(max(2, int(_scale(3, strength))), max(6, int(_scale(11, strength))))
        top = rng.randint(0, max(0, height - band_height))
        offset = rng.randint(-max_offset, max_offset)
        band = jolted.crop((0, top, width, top + band_height))
        band = ImageChops.offset(band, offset, 0)

        if rng.random() < 0.6:
            red, green, blue = band.split()
            red = ImageChops.offset(red, rng.randint(-8, 8), 0)
            blue = ImageChops.offset(blue, rng.randint(-10, 10), 0)
            band = Image.merge("RGB", (red, green, blue))

        jolted.paste(band, (0, top))

    return jolted


def _make_tracking_noise_layer(
    size: tuple[int, int],
    rng: random.Random,
    strength: int,
    noise_strength: int,
    phase: float,
    drift_seed: float,
) -> tuple[Image.Image, Image.Image]:
    width, height = size
    noise_factor = noise_strength / DEFAULT_TRACKING_NOISE
    band_height = max(8, int(_scale(12, strength) * noise_factor))
    travel_start_min = int(height * 0.62)
    travel_start_max = int(height * 0.9)
    start_range = max(1, travel_start_max - travel_start_min)
    travel_start = travel_start_min + int(drift_seed * start_range)
    phase_jitter = rng.uniform(-0.14, 0.14)
    adjusted_phase = min(1.15, max(-0.15, phase + phase_jitter))
    travel_span = max(1, height - travel_start + band_height)
    top = travel_start + int(adjusted_phase * travel_span) - band_height

    if top >= height or top + band_height <= 0:
        empty = Image.new("RGB", size, (0, 0, 0))
        return empty, Image.new("L", size, 0)

    active_top = max(0, top)
    active_bottom = min(height, top + band_height)
    active_height = active_bottom - active_top

    seed_noise = Image.effect_noise((width, max(1, active_height * 3)), max(10, _scale(46, strength) * noise_factor))
    seed_noise = seed_noise.resize((width, active_height), Image.Resampling.BILINEAR)

    red = Image.new("L", (width, active_height), 0)
    green = Image.new("L", (width, active_height), 0)
    blue = Image.new("L", (width, active_height), 0)

    red_data: list[int] = []
    green_data: list[int] = []
    blue_data: list[int] = []
    for value in seed_noise.getdata():
        intensity = 255 if value > 140 else 210 if value > 95 else 0
        if intensity == 0 or rng.random() < 0.15:
            red_data.append(0)
            green_data.append(0)
            blue_data.append(0)
            continue

        channel = rng.randrange(3)
        red_data.append(intensity if channel == 0 else 0)
        green_data.append(intensity if channel == 1 else 0)
        blue_data.append(intensity if channel == 2 else 0)

    red.putdata(red_data)
    green.putdata(green_data)
    blue.putdata(blue_data)

    red = ImageChops.offset(red, rng.randint(-18, 18), 0)
    green = ImageChops.offset(green, rng.randint(-10, 10), 0)
    blue = ImageChops.offset(blue, rng.randint(-18, 18), 0)
    shimmer = Image.merge("RGB", (red, green, blue))

    tear_count = max(2, int(width / 220))
    for _ in range(tear_count):
        tear_y = rng.randint(0, max(0, active_height - 1))
        tear_h = rng.randint(1, max(1, int(band_height * 0.18)))
        tear = shimmer.crop((0, tear_y, width, min(active_height, tear_y + tear_h)))
        tear = ImageChops.offset(tear, rng.randint(-24, 24), 0)
        shimmer.paste(tear, (0, tear_y))

    sparkle = Image.new("RGB", (width, active_height), (0, 0, 0))
    sparkle_count = max(90, int(width * active_height / 45))
    sparkle_px = sparkle.load()
    palette = (
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
    )
    for _ in range(sparkle_count):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, active_height - 1)
        sparkle_px[x, y] = palette[rng.randrange(len(palette))]
    sparkle = sparkle.filter(ImageFilter.GaussianBlur(radius=max(0.1, _scale(0.08, strength))))
    shimmer = ImageChops.add(shimmer, sparkle)

    mask_strip = Image.new("L", (width, active_height), 0)
    stripe_count = max(24, int(width / max(8, _scale(10, strength))))
    for _ in range(stripe_count):
        stripe_x = rng.randint(0, max(0, width - 1))
        stripe_w = rng.randint(1, max(3, int(_scale(8, strength) * noise_factor)))
        stripe_alpha = rng.randint(150, 255)
        stripe = Image.new("L", (stripe_w, active_height), stripe_alpha)
        mask_strip.paste(stripe, (stripe_x, 0))

    mask_strip = mask_strip.filter(ImageFilter.GaussianBlur(radius=max(0.2, _scale(0.45, strength))))
    vertical_fade = Image.linear_gradient("L").rotate(90, expand=True).resize(
        (width, active_height), Image.Resampling.BILINEAR
    )
    mask_strip = ImageChops.multiply(mask_strip, vertical_fade)

    line_noise = Image.new("L", (1, active_height))
    line_noise.putdata([rng.randint(90, 220) for _ in range(active_height)])
    line_noise = line_noise.resize((width, active_height), Image.Resampling.BILINEAR)
    mask_strip = ImageChops.screen(mask_strip, line_noise.filter(ImageFilter.GaussianBlur(radius=0.6)))

    layer = Image.new("RGB", size, (0, 0, 0))
    mask = Image.new("L", size, 0)
    layer.paste(shimmer, (0, active_top))
    mask.paste(mask_strip, (0, active_top))
    return layer, mask


def _save_jpeg_under_limit(image: Image.Image, max_bytes: int = MAX_OUTPUT_BYTES) -> bytes:
    candidate = image
    for max_side in (MAX_SIDE, 1280, 1152, 1024, 896, 768):
        candidate = _resize_to_fit(candidate, max_side)
        for quality in (JPEG_QUALITY, 88, 84, 80, 76, 72, 68, 64, MIN_JPEG_QUALITY):
            output = BytesIO()
            candidate.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
            data = output.getvalue()
            if len(data) <= max_bytes:
                return data

    output = BytesIO()
    candidate.save(output, format="JPEG", quality=MIN_JPEG_QUALITY, optimize=True, progressive=True)
    return output.getvalue()


def _resize_frames(frames: list[Image.Image], max_side: int) -> list[Image.Image]:
    return [_resize_to_fit(frame, max_side) for frame in frames]


def _save_gif_under_limit(
    frames: list[Image.Image],
    durations: list[int],
    loop: int,
    max_bytes: int = MAX_OUTPUT_BYTES,
) -> bytes:
    working_frames = frames
    palette_sizes = (96, 64, 48, 32)
    max_sides = (MAX_SIDE, 1152, 960, 768, 640)

    for max_side in max_sides:
        resized_frames = _resize_frames(working_frames, max_side)
        for colors in palette_sizes:
            converted = [frame.convert("P", palette=ADAPTIVE_PALETTE, colors=colors) for frame in resized_frames]
            output = BytesIO()
            first, *rest = converted
            first.save(
                output,
                format="GIF",
                save_all=True,
                append_images=rest,
                loop=loop,
                duration=durations,
                optimize=True,
                disposal=2,
            )
            data = output.getvalue()
            if len(data) <= max_bytes:
                return data
        working_frames = resized_frames

    output = BytesIO()
    fallback = [frame.convert("P", palette=ADAPTIVE_PALETTE, colors=32) for frame in working_frames]
    first, *rest = fallback
    first.save(
        output,
        format="GIF",
        save_all=True,
        append_images=rest,
        loop=loop,
        duration=durations,
        optimize=True,
        disposal=2,
    )
    return output.getvalue()


def _collect_gif_frames(
    opened: Image.Image,
    input_bytes_len: int,
    strength: int,
    noise: int,
    scanline: int,
    rgb_shift: int,
    noise_bar: bool,
    lofi: int | None,
) -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []
    total_frames = getattr(opened, "n_frames", 1)
    frame_step = max(1, math.ceil(total_frames / GIF_FRAME_LIMIT))
    accumulated_duration = 0
    processed_count = 0
    drift_seed = random.SystemRandom().random()

    for frame_index, frame in enumerate(ImageSequence.Iterator(opened)):
        duration = int(frame.info.get("duration", opened.info.get("duration", 100)) or 100)
        accumulated_duration += duration

        if frame_index % frame_step != 0:
            continue
        if processed_count >= GIF_FRAME_LIMIT:
            break

        normalized = _normalize_frame(ImageOps.exif_transpose(frame))
        normalized = _preprocess_input_image(normalized, input_bytes_len, is_animated=True)
        rng = random.Random(random.SystemRandom().randrange(0, 2**32))
        processed = _apply_vhs_to_image(
            normalized,
            strength,
            noise,
            scanline,
            rgb_shift,
            rng,
            noise_bar=noise_bar,
            lofi=lofi,
            animated=True,
            phase=processed_count / max(1, min(total_frames, GIF_FRAME_LIMIT)),
            drift_seed=drift_seed,
        )
        frames.append(processed)
        durations.append(accumulated_duration)
        accumulated_duration = 0
        processed_count += 1

    if durations and accumulated_duration:
        durations[-1] += accumulated_duration

    return frames, durations


def _apply_vhs_to_image(
    image: Image.Image,
    strength: int,
    noise: int,
    scanline: int,
    rgb_shift: int,
    rng: random.Random,
    noise_bar: bool = False,
    lofi: int | None = None,
    animated: bool = False,
    phase: float | None = None,
    drift_seed: float | None = None,
) -> Image.Image:
    image = _downscale(image)
    if lofi is not None:
        image = _apply_lofi_softening(image, lofi)
    image = ImageEnhance.Color(image).enhance(1 + _scale(0.45, strength))
    image = ImageEnhance.Contrast(image).enhance(1 + _scale(0.12, strength))

    band_shifted = _make_band_shift_layer(image, rng, strength, rgb_shift)
    rgb_factor = rgb_shift / DEFAULT_RGB_SHIFT
    red_shift = max(1, int(_scale(8, strength) * DEFAULT_SHIFT_SCALE * rgb_factor))
    blue_shift = max(1, int(_scale(10, strength) * DEFAULT_SHIFT_SCALE * rgb_factor))
    red = ImageChops.offset(band_shifted.getchannel("R"), rng.randint(-red_shift, red_shift), 0)
    green = band_shifted.getchannel("G")
    blue = ImageChops.offset(band_shifted.getchannel("B"), rng.randint(-blue_shift, blue_shift), 0)
    merged = Image.merge("RGB", (red, green, blue))

    glow = merged.filter(ImageFilter.GaussianBlur(radius=max(0.2, _scale(1.4, strength))))
    merged = Image.blend(merged, glow, min(0.6, _scale(0.22, strength)))

    scanline_alpha = _make_scanlines(merged.size, rng, strength, scanline)
    merged = Image.composite(Image.new("RGB", merged.size, (18, 18, 18)), merged, scanline_alpha)

    noise_layer = _make_noise(merged.size, rng, strength, noise)
    noise_blend = min(0.35, _scale(0.08, strength) * (noise / DEFAULT_NOISE))
    merged = Image.blend(merged, noise_layer, noise_blend)

    if animated and rng.random() < 0.22:
        merged = _apply_line_jolt(merged, rng, strength, rgb_shift)

    if noise_bar:
        tracking_layer, tracking_mask = _make_tracking_noise_layer(
            merged.size,
            rng,
            strength,
            noise,
            rng.random() if phase is None else phase,
            rng.random() if drift_seed is None else drift_seed,
        )
        tracked = Image.composite(tracking_layer, Image.new("RGB", merged.size, (0, 0, 0)), tracking_mask)
        tracked = Image.blend(Image.new("RGB", merged.size, (0, 0, 0)), tracked, 0.9)
        merged = ImageChops.add(merged, tracked, scale=1.0, offset=0)
    return merged.filter(ImageFilter.GaussianBlur(radius=max(0.1, _scale(0.3, strength))))


def apply_vhs_effect(
    image_bytes: bytes,
    strength: int | None = None,
    noise: int | None = None,
    scanline: int | None = None,
    rgb_shift: int | None = None,
    noise_bar: bool = False,
    lofi: int | None = None,
) -> tuple[bytes, str]:
    input_bytes_len = len(image_bytes)
    strength = _clamp_strength(strength)
    noise = _clamp(noise if noise is not None else DEFAULT_NOISE, MIN_NOISE, MAX_NOISE)
    scanline = _clamp(scanline if scanline is not None else DEFAULT_SCANLINE, MIN_SCANLINE, MAX_SCANLINE)
    rgb_shift = _clamp(rgb_shift if rgb_shift is not None else DEFAULT_RGB_SHIFT, MIN_RGB_SHIFT, MAX_RGB_SHIFT)
    if lofi is not None:
        lofi = _clamp(lofi, MIN_LOFI, MAX_LOFI)

    with Image.open(BytesIO(image_bytes)) as opened:
        is_animated = bool(getattr(opened, "is_animated", False)) and getattr(opened, "n_frames", 1) > 1

        if is_animated:
            frames, durations = _collect_gif_frames(
                opened,
                input_bytes_len,
                strength,
                noise,
                scanline,
                rgb_shift,
                noise_bar,
                lofi,
            )

            if not frames:
                raise ValueError("Failed to read GIF frames. Please try a different GIF.")

            return _save_gif_under_limit(
                frames,
                durations,
                loop=int(opened.info.get("loop", 0)),
            ), "gif"

        image = _normalize_frame(ImageOps.exif_transpose(opened))
        image = _preprocess_input_image(image, input_bytes_len, is_animated=False)

    rng = random.SystemRandom()
    merged = _apply_vhs_to_image(
        image,
        strength,
        noise,
        scanline,
        rgb_shift,
        rng,
        noise_bar=noise_bar,
        lofi=lofi,
        animated=False,
        drift_seed=random.SystemRandom().random(),
    )

    return _save_jpeg_under_limit(merged), "jpg"


def build_output_filename(source_name: str | None, extension: str = "jpg") -> str:
    stem = Path(source_name or "image").stem or "image"
    return f"{stem}_vhs.{extension}"

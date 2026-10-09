#!/usr/bin/env python3
"""
Nothing X Advanced EQ QR Code Generator & Encoder
-------------------------------------------------
Takes an 8-band EQ CSV file, validates each band against Nothing X hardware limits,
encodes the parameters into Nothing's binary payload, and renders a Nothing-style QR code.

Cross-platform: Windows & Linux compatible.
"""

import argparse
import base64
import csv
import gzip
import math
import os
import re
import struct
import sys
from pathlib import Path

# Image rendering dependencies
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    import qrcode
except ImportError:
    qrcode = None


# Official Nothing X hardware limits per band
BAND_SPECS = [
    {"band": 1, "f_min": 20, "f_max": 99, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 2, "f_min": 100, "f_max": 199, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 3, "f_min": 200, "f_max": 399, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 4, "f_min": 400, "f_max": 999, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 5, "f_min": 1000, "f_max": 2999, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 6, "f_min": 3000, "f_max": 5999, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 7, "f_min": 6000, "f_max": 11999, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
    {"band": 8, "f_min": 12000, "f_max": 20000, "g_min": -6.0, "g_max": 6.0, "q_min": 0.1, "q_max": 10.0},
]


def parse_csv(csv_path: str) -> list:
    """Parses 8 bands from either a 3-column or 4-column CSV file."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with path.open(mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = [r for r in reader if r and not r[0].strip().startswith("#")]

    if not rows:
        raise ValueError("CSV file is empty.")

    # Skip header row if present
    start_idx = 0
    try:
        float(rows[0][0].strip())
    except ValueError:
        start_idx = 1

    bands = []
    for r in rows[start_idx:]:
        clean = [x.strip() for x in r if x.strip()]
        if not clean:
            continue
        if len(clean) >= 4:
            # Format: Band, Frequency, Gain, Q
            bands.append({
                "frequency_hz": float(clean[1]),
                "gain_db": float(clean[2]),
                "q_factor": float(clean[3])
            })
        elif len(clean) >= 3:
            # Format: Frequency, Gain, Q
            bands.append({
                "frequency_hz": float(clean[0]),
                "gain_db": float(clean[1]),
                "q_factor": float(clean[2])
            })
        else:
            raise ValueError(f"Invalid row format: {r}. Expected at least 3 values.")

    return bands


def validate_bands(bands: list):
    """Validates bands against Nothing X hardware limit table."""
    if len(bands) != 8:
        raise ValueError(f"Expected exactly 8 bands, but found {len(bands)} in CSV.")

    for i, (b, spec) in enumerate(zip(bands, BAND_SPECS)):
        band_num = spec["band"]
        freq = b["frequency_hz"]
        gain = b["gain_db"]
        q = b["q_factor"]

        # Validate Frequency
        if not (spec["f_min"] <= freq <= spec["f_max"]):
            raise ValueError(
                f"[Band {band_num}] Frequency {freq:g} Hz is out of allowed range [{spec['f_min']}–{spec['f_max']}] Hz."
            )

        # Validate Gain
        if not (spec["g_min"] <= gain <= spec["g_max"]):
            raise ValueError(
                f"[Band {band_num}] Gain {gain:+.2f} dB is out of allowed range [{spec['g_min']} to {spec['g_max']}] dB."
            )

        # Validate Q Factor
        if not (spec["q_min"] <= q <= spec["q_max"]):
            raise ValueError(
                f"[Band {band_num}] Q Factor {q:.2f} is out of allowed range [{spec['q_min']} to {spec['q_max']}]."
            )


def encode_nothing_payload(profile_name: str, bands: list) -> str:
    """Builds the binary structure, compresses with Gzip, and returns Base64 string."""
    # 1. Format Header: 2 bytes
    header = b"\x00\x60"

    # 2. 8 Bands: each band is 3 little-endian 32-bit floats (Gain, Frequency, Q Factor)
    payload_parts = []
    for b in bands:
        chunk = struct.pack(
            "<3f",
            float(b["gain_db"]),
            float(b["frequency_hz"]),
            float(b["q_factor"])
        )
        payload_parts.append(chunk)
    payload = b"".join(payload_parts)

    # 3. Trailer: Flag (0x01) + length byte + UTF-8 name bytes
    name_bytes = profile_name.strip().encode("utf-8")
    if len(name_bytes) > 255:
        raise ValueError("Profile name is too long (max 255 characters).")
    trailer = bytes([0x01, len(name_bytes)]) + name_bytes

    # Gzip compress with fixed mtime for consistent hashing
    full_binary = header + payload + trailer
    compressed = gzip.compress(full_binary, mtime=0)

    # Base64 encode
    return base64.b64encode(compressed).decode("ascii")


def generate_qr_matrix(b64_str: str) -> np.ndarray:
    """Generates the QR boolean matrix using Error Correction Level H (30%)."""
    if qrcode is not None:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=1,
            border=0,
        )
        qr.add_data(b64_str)
        qr.make(fit=True)
        return np.array(qr.get_matrix(), dtype=bool)

    if cv2 is not None:
        params = cv2.QRCodeEncoder_Params()
        params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_H
        params.mode = cv2.QRCodeEncoder_MODE_BYTE
        encoder = cv2.QRCodeEncoder.create(params)
        qr_mat = encoder.encode(b64_str)
        # cv2 returns 2px quiet border by default
        return (qr_mat[2:-2, 2:-2] == 0)

    raise RuntimeError("Neither 'qrcode' nor 'opencv-python' is available to generate QR matrices.")


def render_nothing_style_qr(
    matrix: np.ndarray,
    module_size: int = 12,
    quiet_zone: int = 4
) -> Image.Image:
    """
    Renders an authentic Nothing-style QR card:
      - Dot-matrix circular modules
      - Rounded outer & inner corner eyes with 1-module separation
      - Central white emblem featuring the Nothing Ear stem with the iconic red marker
      - Framed inside a rounded white card
    """
    if Image is None:
        raise RuntimeError("Pillow is required for rendering QR codes. Install via 'pip install Pillow'.")

    N = matrix.shape[0]
    total_modules = N + 2 * quiet_zone
    img_size = total_modules * module_size

    img = Image.new("RGBA", (img_size, img_size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 1. Reserved zones around finder patterns (8x8 modules)
    def in_finder_zone(r, c):
        if r < 8 and c < 8: return True
        if r < 8 and c >= N - 8: return True
        if r >= N - 8 and c < 8: return True
        return False

    # 2. Central emblem cutout area
    center_r, center_c = N / 2.0, N / 2.0
    center_cutout_radius = 5.6

    def in_center_cutout(r, c):
        return math.hypot(r - center_r + 0.5, c - center_c + 0.5) < center_cutout_radius

    # 3. Draw Data Modules as Circles
    dot_radius = module_size * 0.44
    for r in range(N):
        for c in range(N):
            if in_finder_zone(r, c) or in_center_cutout(r, c):
                continue
            if matrix[r, c]:
                cx = (c + quiet_zone + 0.5) * module_size
                cy = (r + quiet_zone + 0.5) * module_size
                draw.ellipse(
                    [cx - dot_radius, cy - dot_radius, cx + dot_radius, cy + dot_radius],
                    fill=(0, 0, 0, 255)
                )

    # 4. Draw Rounded Finder Patterns
    finder_coords = [(0, 0), (0, N - 7), (N - 7, 0)]
    for fr, fc in finder_coords:
        x = (fc + quiet_zone) * module_size
        y = (fr + quiet_zone) * module_size
        size = 7 * module_size

        # Outer black box (7x7 modules)
        r_outer = int(1.5 * module_size)
        draw.rounded_rectangle([x, y, x + size, y + size], radius=r_outer, fill=(0, 0, 0, 255))

        # Inner white gap (5x5 modules)
        inset1 = 1 * module_size
        r_inner1 = int(1.0 * module_size)
        draw.rounded_rectangle(
            [x + inset1, y + inset1, x + size - inset1, y + size - inset1],
            radius=r_inner1, fill=(255, 255, 255, 255)
        )

        # Center black eye (3x3 modules)
        inset2 = 2 * module_size
        r_inner2 = int(0.7 * module_size)
        draw.rounded_rectangle(
            [x + inset2, y + inset2, x + size - inset2, y + size - inset2],
            radius=r_inner2, fill=(0, 0, 0, 255)
        )

    # 5. Draw Central Nothing Earbud Emblem
    center_px = (center_c + quiet_zone) * module_size
    center_py = (center_r + quiet_zone) * module_size
    badge_r = center_cutout_radius * module_size

    # Light gray circular base
    draw.ellipse(
        [center_px - badge_r, center_py - badge_r, center_px + badge_r, center_py + badge_r],
        fill=(242, 242, 242, 255)
    )

    # Translucent circles representing transparent casing
    t_r = badge_r * 0.38
    t_off = badge_r * 0.28
    draw.ellipse(
        [center_px - t_off - t_r, center_py + t_off - t_r, center_px - t_off + t_r, center_py + t_off + t_r],
        fill=(220, 220, 220, 255)
    )
    draw.ellipse(
        [center_px + t_off - t_r, center_py - t_off - t_r, center_px + t_off + t_r, center_py - t_off + t_r],
        fill=(220, 220, 220, 255)
    )

    # Angled earbud stem
    stem_len = badge_r * 1.05
    stem_w = badge_r * 0.44
    stem_surf = Image.new("RGBA", (int(stem_len * 2), int(stem_len * 2)), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(stem_surf)
    sc = stem_len
    s_draw.rounded_rectangle(
        [sc - stem_len / 2, sc - stem_w / 2, sc + stem_len / 2, sc + stem_w / 2],
        radius=stem_w / 2, fill=(24, 24, 24, 255)
    )

    # Iconic red marker dot on right earbud
    red_r = stem_w * 0.36
    red_cx = sc + stem_len / 2 - stem_w / 2
    s_draw.ellipse(
        [red_cx - red_r, sc - red_r, red_cx + red_r, sc + red_r],
        fill=(215, 30, 30, 255)
    )

    rotated = stem_surf.rotate(-45, resample=Image.Resampling.BICUBIC)
    img.paste(rotated, (int(center_px - sc), int(center_py - sc)), rotated)

    return img


def render_full_share_card(
    profile_name: str,
    author: str,
    bands: list,
    qr_img: Image.Image,
    output_path: str
):
    """Generates the complete 9:16 Nothing share poster matching the official app layout."""
    card_w, card_h = 900, 1600
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(card)

    # 1. Header: NOTHING (R)
    draw.text((48, 64), "NOTHING (R)", fill=(240, 240, 240, 255))

    # 2. White QR Card container
    container_w, container_h = 470, 480
    cx = (card_w - container_w) // 2
    cy = 430
    draw.rounded_rectangle([cx, cy, cx + container_w, cy + container_h], radius=28, fill=(255, 255, 255, 255))

    # Scale and paste QR code inside card
    qr_resized = qr_img.resize((430, 430), resample=Image.Resampling.LANCZOS)
    card.paste(qr_resized, (cx + 20, cy + 25), qr_resized)

    # 3. Dark EQ Curve Preview Box
    box_w, box_h = container_w, 120
    by = cy + container_h + 18
    draw.rounded_rectangle([cx, by, cx + box_w, by + box_h], radius=20, fill=(20, 20, 20, 255))

    # Calculate and draw parametric EQ frequency response curve
    num_pts = box_w - 40
    log_freqs = np.logspace(np.log10(20), np.log10(20000), num_pts)
    curve_gains = np.zeros(num_pts)
    for b in bands:
        f0, g, q = b["frequency_hz"], b["gain_db"], b["q_factor"]
        sigma = 1.0 / (q * 1.5)
        curve_gains += g * np.exp(-0.5 * (np.log2(log_freqs / f0) / sigma) ** 2)

    c_x0 = cx + 20
    c_y_mid = by + box_h // 2
    y_scale = (box_h - 35) / 14.0

    curve_pts = []
    for i, g in enumerate(curve_gains):
        curve_pts.append((c_x0 + i, c_y_mid - g * y_scale))

    for i in range(len(curve_pts) - 1):
        draw.line([curve_pts[i], curve_pts[i + 1]], fill=(70, 70, 70, 255), width=2)

    # Draw 8 band white dots on curve
    for b in bands:
        norm_f = (np.log10(b["frequency_hz"]) - np.log10(20)) / (np.log10(20000) - np.log10(20))
        dot_x = c_x0 + norm_f * (box_w - 40)
        dot_y = c_y_mid - b["gain_db"] * y_scale
        r = 4.0
        draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=(255, 255, 255, 255))

    # 4. Profile Name & Subtitle
    draw.text((48, by + box_h + 70), profile_name, fill=(255, 255, 255, 255))
    draw.text((48, by + box_h + 120), f"By {author}", fill=(200, 200, 200, 255))

    # 5. Footer Text
    draw.text((48, 1490), "Scan using\nNothing X app", fill=(180, 180, 180, 255))
    draw.text((400, 1490), "Tuned on Nothing Ear\nAdvanced equaliser profile", fill=(180, 180, 180, 255))

    card.save(output_path)
    print(f"[✓] Generated full Nothing Share Card poster: {output_path}")


def print_validation_table(profile_name: str, bands: list):
    """Prints a verified parameter table in the terminal."""
    border = "=" * 66
    divider = "-" * 66
    print("\n" + border)
    print(f"{'VERIFIED NOTHING X EQ PROFILE':^66}")
    print(border)
    print(f" Profile Name : {profile_name}")
    print(f" Status       : [✓] ALL 8 BANDS VALIDATED WITHIN HARDWARE LIMITS")
    print(divider)
    print(f" {'Band #':<8} | {'Frequency (Hz)':<16} | {'Gain (dB)':<14} | {'Q Factor':<12} ")
    print(divider)
    for i, b in enumerate(bands):
        freq_str = f"{b['frequency_hz']:g} Hz"
        gain_str = f"{b['gain_db']:+.2f} dB" if b['gain_db'] != 0 else " 0.00 dB"
        q_str = f"{b['q_factor']:.2f}"
        print(f"   {i + 1:<6} | {freq_str:>14}   | {gain_str:>12}   | {q_str:>10}  ")
    print(border)


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return sanitized.replace(" ", "_") or "profile"


def main():
    parser = argparse.ArgumentParser(
        description="Validate an EQ CSV file and generate an authentic Nothing-style QR code."
    )
    parser.add_argument("csv_path", help="Path to the input CSV file.")
    parser.add_argument("--name", "-n", help="Profile name (defaults to CSV filename).")
    parser.add_argument("--author", "-a", default="User", help="Author name for the share card (defaults to 'User').")
    parser.add_argument("--output", "-o", help="Custom path for the QR image.")
    parser.add_argument("--card", action="store_true", help="Also generate the complete 9:16 Nothing share poster.")

    args = parser.parse_args()

    # 1. Parse CSV
    try:
        bands = parse_csv(args.csv_path)
    except Exception as e:
        print(f"[X] CSV Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Validate Bands against hardware limits
    try:
        validate_bands(bands)
    except ValueError as e:
        print(f"\n[X] Validation Failed: {e}", file=sys.stderr)
        print("Please adjust your CSV values to comply with the Nothing X hardware table.", file=sys.stderr)
        sys.exit(1)

    # Profile Name
    profile_name = args.name.strip() if args.name else Path(args.csv_path).stem
    safe_name = sanitize_filename(profile_name)

    # 3. Encode to Nothing binary payload
    b64_payload = encode_nothing_payload(profile_name, bands)

    # 4. Print Table and Payload
    print_validation_table(profile_name, bands)
    print(f"\nEncoded Base64 Payload:\n{b64_payload}\n")

    # 5. Generate Nothing-style QR Code
    try:
        qr_matrix = generate_qr_matrix(b64_payload)
        qr_img = render_nothing_style_qr(qr_matrix)

        qr_output_path = args.output if args.output else f"{safe_name}_qr.png"
        qr_img.save(qr_output_path)
        print(f"[✓] Generated Nothing-style QR code: {qr_output_path}")

        # Optional Share Card
        if args.card:
            card_path = f"{safe_name}_card.png"
            render_full_share_card(profile_name, args.author, bands, qr_img, card_path)

    except Exception as e:
        print(f"[X] Image Generation Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
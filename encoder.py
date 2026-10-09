#!/usr/bin/env python3
"""
Nothing X Advanced EQ QR Code Generator & Authentic Card Renderer
------------------------------------------------------------------
Validates an 8-band EQ CSV against Nothing X hardware limits, encodes the
parameters into Nothing's binary payload, and renders pixel-accurate Nothing-style
QR cards and full share posters with exact DSP biquad curve visualization.

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
            bands.append({
                "frequency_hz": float(clean[1]),
                "gain_db": float(clean[2]),
                "q_factor": float(clean[3])
            })
        elif len(clean) >= 3:
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

    for b, spec in zip(bands, BAND_SPECS):
        band_num = spec["band"]
        freq = b["frequency_hz"]
        gain = b["gain_db"]
        q = b["q_factor"]

        if not (spec["f_min"] <= freq <= spec["f_max"]):
            raise ValueError(
                f"[Band {band_num}] Frequency {freq:g} Hz is out of allowed range [{spec['f_min']}–{spec['f_max']}] Hz."
            )
        if not (spec["g_min"] <= gain <= spec["g_max"]):
            raise ValueError(
                f"[Band {band_num}] Gain {gain:+.2f} dB is out of allowed range [{spec['g_min']} to {spec['g_max']}] dB."
            )
        if not (spec["q_min"] <= q <= spec["q_max"]):
            raise ValueError(
                f"[Band {band_num}] Q Factor {q:.2f} is out of allowed range [{spec['q_min']} to {spec['q_max']}]."
            )


def encode_nothing_payload(profile_name: str, bands: list) -> str:
    """Builds the binary structure, compresses with Gzip, and returns Base64 string."""
    header = b"\x00\x60"
    payload_parts = [
        struct.pack("<3f", float(b["gain_db"]), float(b["frequency_hz"]), float(b["q_factor"]))
        for b in bands
    ]
    payload = b"".join(payload_parts)

    name_bytes = profile_name.strip().encode("utf-8")
    if len(name_bytes) > 255:
        raise ValueError("Profile name is too long (max 255 characters).")
    trailer = bytes([0x01, len(name_bytes)]) + name_bytes

    full_binary = header + payload + trailer
    compressed = gzip.compress(full_binary, mtime=0)
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
        return (qr_mat[2:-2, 2:-2] == 0)

    raise RuntimeError("Neither 'qrcode' nor 'opencv-python' is available to generate QR matrices.")


def biquad_peaking_response_db(f_eval, f0, gain_db, q):
    """Calculates continuous analog/DSP peaking EQ filter frequency response in dB."""
    if abs(gain_db) < 1e-4:
        return np.zeros_like(f_eval)
    A = 10.0 ** (gain_db / 40.0)
    w = f_eval / f0
    num = (1.0 - w**2)**2 + (w * A / q)**2
    den = (1.0 - w**2)**2 + (w / (A * q))**2
    return 10.0 * np.log10(num / den)


def draw_ndot_text(draw, text: str, x0: int, y0: int, dot_r: float = 1.6, pitch: float = 4.6):
    """Renders text in Nothing's signature NDot-55 dot-matrix font style."""
    font_5x7 = {
        'N': [[1,0,0,0,1],[1,1,0,0,1],[1,0,1,0,1],[1,0,0,1,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1]],
        'O': [[0,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[0,1,1,1,0]],
        'T': [[1,1,1,1,1],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0]],
        'H': [[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1]],
        'I': [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0],[0,1,0],[1,1,1]],
        'G': [[0,1,1,1,0],[1,0,0,0,1],[1,0,0,0,0],[1,0,1,1,1],[1,0,0,0,1],[1,0,0,0,1],[0,1,1,1,0]],
        '(': [[0,0,1],[0,1,0],[1,0,0],[1,0,0],[1,0,0],[0,1,0],[0,0,1]],
        ')': [[1,0,0],[0,1,0],[0,0,1],[0,0,1],[0,0,1],[0,1,0],[1,0,0]],
        'R': [[1,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,0],[1,0,1,0,0],[1,0,0,1,0],[1,0,0,0,1]],
        ' ': [[0,0],[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]]
    }
    cur_x = x0
    for ch in text.upper():
        if ch not in font_5x7:
            cur_x += 4 * pitch
            continue
        matrix = font_5x7[ch]
        w_ch = len(matrix[0])
        for r in range(7):
            for c in range(w_ch):
                if matrix[r][c]:
                    cx = cur_x + c * pitch
                    cy = y0 + r * pitch
                    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=(230, 230, 230, 255))
        cur_x += (w_ch + 1) * pitch


def generate_authentic_nothing_x_badge(target_size: int = 74) -> Image.Image:
    """
    Renders the exact Nothing X emblem with 8x supersampling:
    Two crossed rounded capsules forming an 'X' (grey back pill at +45°,
    charcoal front pill at -45° with the vibrant red earbud marker dot).
    """
    scale = 8
    S = target_size * scale
    c = S / 2.0

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Circular base (light-gray #F0F0F0)
    br = (target_size / 2.0) * scale
    draw.ellipse([c - br, c - br, c + br, c + br], fill=(240, 240, 240, 255))

    # Capsule dimensions scaled
    plen = (54.0 / 74.0) * target_size * scale
    pwid = (21.2 / 74.0) * target_size * scale

    # 2. Back pill (Light-grey capsule #D2D2D2 angled at +45°)
    back_canvas = Image.new("RGBA", (int(plen * 1.5), int(plen * 1.5)), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(back_canvas)
    bc = (plen * 1.5) / 2.0
    b_draw.rounded_rectangle(
        [bc - plen / 2, bc - pwid / 2, bc + plen / 2, bc + pwid / 2],
        radius=pwid / 2,
        fill=(210, 210, 210, 255)
    )
    back_rot = back_canvas.rotate(45, resample=Image.Resampling.BICUBIC)
    b_x = int(c - bc)
    b_y = int(c - bc)
    img.paste(back_rot, (b_x, b_y), back_rot)

    # 3. Front pill (Charcoal capsule #202020 angled at -45°)
    front_canvas = Image.new("RGBA", (int(plen * 1.5), int(plen * 1.5)), (0, 0, 0, 0))
    f_draw = ImageDraw.Draw(front_canvas)
    fc = (plen * 1.5) / 2.0
    f_draw.rounded_rectangle(
        [fc - plen / 2, fc - pwid / 2, fc + plen / 2, fc + pwid / 2],
        radius=pwid / 2,
        fill=(32, 32, 32, 255)
    )

    # 4. Red circle indicator at the bottom-right cap
    red_r = (7.8 / 74.0) * target_size * scale
    rcx = fc + plen / 2 - pwid / 2
    rcy = fc
    f_draw.ellipse(
        [rcx - red_r, rcy - red_r, rcx + red_r, rcy + red_r],
        fill=(222, 30, 35, 255)
    )

    front_rot = front_canvas.rotate(-45, resample=Image.Resampling.BICUBIC)
    f_x = int(c - fc)
    f_y = int(c - fc)
    img.paste(front_rot, (f_x, f_y), front_rot)

    # Downscale smoothly to target size
    return img.resize((target_size, target_size), resample=Image.Resampling.LANCZOS)


def create_nothing_qr_image(matrix: np.ndarray, module_size: int = 20, quiet_zone: int = 4) -> Image.Image:
    """Renders Nothing-style QR code with high-resolution supersampling for smooth circular dots."""
    N = matrix.shape[0]
    total_modules = N + 2 * quiet_zone
    img_size = total_modules * module_size
    img = Image.new("RGBA", (img_size, img_size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    def in_finder_zone(r, c):
        if r < 8 and c < 8: return True
        if r < 8 and c >= N - 8: return True
        if r >= N - 8 and c < 8: return True
        return False

    center_r, center_c = N / 2.0, N / 2.0
    center_cutout_radius = 5.6

    def in_center_cutout(r, c):
        return math.hypot(r - center_r + 0.5, c - center_c + 0.5) < center_cutout_radius

    # 1. Circular data modules
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

    # 2. Rounded corner finder patterns
    finder_coords = [(0, 0), (0, N - 7), (N - 7, 0)]
    for fr, fc in finder_coords:
        x = (fc + quiet_zone) * module_size
        y = (fr + quiet_zone) * module_size
        size = 7 * module_size

        r_outer = int(1.5 * module_size)
        draw.rounded_rectangle([x, y, x + size, y + size], radius=r_outer, fill=(0, 0, 0, 255))

        inset1 = 1 * module_size
        r_inner1 = int(1.0 * module_size)
        draw.rounded_rectangle([x + inset1, y + inset1, x + size - inset1, y + size - inset1],
                               radius=r_inner1, fill=(255, 255, 255, 255))

        inset2 = 2 * module_size
        r_inner2 = int(0.7 * module_size)
        draw.rounded_rectangle([x + inset2, y + inset2, x + size - inset2, y + size - inset2],
                               radius=r_inner2, fill=(0, 0, 0, 255))

    # 3. Authentic Nothing X Emblem
    badge_pixel_diameter = int(center_cutout_radius * 2.0 * module_size)
    badge_img = generate_authentic_nothing_x_badge(target_size=badge_pixel_diameter)

    center_px = int((center_c + quiet_zone) * module_size)
    center_py = int((center_r + quiet_zone) * module_size)

    bx = center_px - badge_pixel_diameter // 2
    by = center_py - badge_pixel_diameter // 2
    img.paste(badge_img, (bx, by), badge_img)

    return img


def render_curve_box_accurate(bands: list, box_w: int = 452, box_h: int = 152) -> Image.Image:
    """Renders the authentic Parametric EQ response box with baseline, gradient fill, and control points."""
    img = Image.new("RGBA", (box_w, box_h), (25, 23, 22, 255))
    draw = ImageDraw.Draw(img)

    y_baseline = 86.5
    draw.line([(35, int(y_baseline)), (box_w - 20, int(y_baseline))], fill=(42, 39, 38, 255), width=1)

    x_start = 35
    x_end = box_w - 20
    x_coords = np.arange(x_start, x_end + 1)
    log_freqs = (x_coords + 106.77) / 125.56
    freqs = 10.0 ** log_freqs

    total_db = np.zeros_like(freqs)
    for b in bands:
        total_db += biquad_peaking_response_db(freqs, b["frequency_hz"], b["gain_db"], b["q_factor"])

    y_curve = y_baseline - total_db * 7.5

    overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for x, yc in zip(x_coords, y_curve):
        y_top = min(yc, y_baseline)
        y_bot = max(yc, y_baseline)
        h_col = y_bot - y_top
        if h_col > 0.5:
            for y_step in np.arange(int(y_top), int(y_bot) + 1):
                dist_norm = abs(y_step - yc) / h_col
                alpha = int(45 * (1.0 - 0.4 * dist_norm))
                ov_draw.point((int(x), int(y_step)), fill=(255, 255, 255, alpha))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    pts = list(zip(x_coords, y_curve))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=(140, 138, 136, 255), width=2)

    r_dot = 3.6
    for b in bands:
        dot_x = 125.56 * np.log10(b["frequency_hz"]) - 106.77
        dot_y = y_baseline - b["gain_db"] * 7.5
        draw.ellipse([dot_x - r_dot - 1, dot_y - r_dot - 1, dot_x + r_dot + 1, dot_y + r_dot + 1], fill=(255, 255, 255, 120))
        draw.ellipse([dot_x - r_dot, dot_y - r_dot, dot_x + r_dot, dot_y + r_dot], fill=(255, 255, 255, 255))

    return img


def render_full_share_poster(
    profile_name: str,
    author: str,
    bands: list,
    qr_matrix: np.ndarray,
    output_path: str,
    canvas_w: int = 899,
    canvas_h: int = 1600
):
    """Renders the authentic Nothing share poster matching the official layout and typography scale."""
    poster = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(poster)

    # 1. Header: NOTHING (R) in NDot font
    draw_ndot_text(draw, "NOTHING (R)", 48, 62, dot_r=1.6, pitch=4.6)

    # 2. White QR Card
    card_x, card_y = 39, 434
    card_w, card_h = 452, 466

    qr_card = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
    high_res_qr = create_nothing_qr_image(qr_matrix, module_size=20, quiet_zone=4)
    qr_resized = high_res_qr.resize((card_w, card_w), resample=Image.Resampling.LANCZOS)
    qr_card.paste(qr_resized, (0, 7), qr_resized)

    card_mask = Image.new("L", (card_w, card_h), 0)
    cm_draw = ImageDraw.Draw(card_mask)
    cm_draw.rounded_rectangle([0, 0, card_w, card_h], radius=28, fill=255)
    poster.paste(qr_card, (card_x, card_y), card_mask)

    # 3. Parametric EQ Curve Box
    curve_y = 900
    curve_h = 152
    curve_box_img = render_curve_box_accurate(bands, box_w=card_w, box_h=curve_h)

    cb_mask = Image.new("L", (card_w, curve_h), 0)
    cbm_draw = ImageDraw.Draw(cb_mask)
    cbm_draw.rounded_rectangle([0, 0, card_w, curve_h], radius=18, fill=255)
    poster.paste(curve_box_img, (card_x, curve_y), cb_mask)

    # 4. Serif Typography with 1:1 scale
    font_path = None
    for p in [
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "C:\\Windows\\Fonts\\times.ttf", "C:\\Windows\\Fonts\\georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "times.ttf", "georgia.ttf"
    ]:
        if os.path.exists(p):
            font_path = p
            break

    if font_path:
        title_sz = 80
        while title_sz > 30:
            f_test = ImageFont.truetype(font_path, title_sz)
            bb = f_test.getbbox(profile_name)
            if (bb[2] - bb[0]) <= 440:
                break
            title_sz -= 2
        font_title = ImageFont.truetype(font_path, title_sz)
        font_sub = ImageFont.truetype(font_path, 54)
        font_foot = ImageFont.truetype(font_path, 28)
    else:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_foot = ImageFont.load_default()

    draw.text((47, 1147), profile_name, font=font_title, fill=(255, 255, 255, 255))
    draw.text((48, 1231), f"By {author}", font=font_sub, fill=(255, 255, 255, 255))

    # 5. Footer Text
    draw.text((47, 1391), "Scan using\nNothing X app", font=font_foot, fill=(210, 210, 210, 255), spacing=4)
    draw.text((285, 1391), "Tuned on Nothing Ear\nAdvanced equaliser profile", font=font_foot, fill=(210, 210, 210, 255), spacing=4)

    poster.save(output_path)
    print(f"[✓] Generated authentic Nothing Share Poster: {output_path}")


def print_validation_table(profile_name: str, bands: list):
    """Prints verified parameter table in terminal."""
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
        description="Validate an EQ CSV file and generate an authentic Nothing-style QR code or poster."
    )
    parser.add_argument("csv_path", help="Path to the input CSV file.")
    parser.add_argument("--name", "-n", help="Profile name (defaults to CSV filename).")
    parser.add_argument("--author", "-a", default="Farhan", help="Author name for poster (defaults to 'Farhan').")
    parser.add_argument("--output", "-o", help="Custom path for output file.")
    parser.add_argument("--card", action="store_true", help="Also generate the authentic 9:16 Nothing share poster.")

    args = parser.parse_args()

    try:
        bands = parse_csv(args.csv_path)
    except Exception as e:
        print(f"[X] CSV Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_bands(bands)
    except ValueError as e:
        print(f"\n[X] Validation Failed: {e}", file=sys.stderr)
        sys.exit(1)

    profile_name = args.name.strip() if args.name else Path(args.csv_path).stem
    safe_name = sanitize_filename(profile_name)

    b64_payload = encode_nothing_payload(profile_name, bands)
    print_validation_table(profile_name, bands)
    print(f"\nEncoded Base64 Payload:\n{b64_payload}\n")

    try:
        qr_matrix = generate_qr_matrix(b64_payload)
        # Standalone QR output (supersampled for smooth circular dots)
        qr_img = create_nothing_qr_image(qr_matrix, module_size=20, quiet_zone=4)
        qr_img_scaled = qr_img.resize((800, 800), resample=Image.Resampling.LANCZOS)

        qr_output_path = args.output if args.output else f"{safe_name}_qr.png"
        qr_img_scaled.save(qr_output_path)
        print(f"[✓] Generated Nothing-style QR card: {qr_output_path}")

        if args.card:
            card_path = f"{safe_name}_card.png"
            render_full_share_poster(profile_name, args.author, bands, qr_matrix, card_path)

    except Exception as e:
        print(f"[X] Render Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
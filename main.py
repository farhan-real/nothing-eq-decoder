#!/usr/bin/env python3

import argparse
import base64
import csv
import gzip
import os
import re
import struct
import sys
from pathlib import Path
from typing import Optional

# Optional / Fallback dependencies
try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

# On Linux, pyzbar may raise an Exception if libzbar0 is not installed
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
except Exception:
    pyzbar_decode = None


def decode_nothing_x_payload(raw_str: str) -> dict:
    """
    Decodes a Nothing X base64/gzip string into EQ parameters.
    Format:
      - 2 bytes: Header (e.g. 0x0060)
      - 96 bytes: 8 bands * 12 bytes (Gain, Freq, Q as 32-bit little-endian floats)
      - Trailer: flag byte + length byte + UTF-8 profile name
    """
    try:
        raw_bytes = base64.b64decode(raw_str.strip())
        uncompressed = gzip.decompress(raw_bytes)
    except Exception as e:
        raise ValueError(f"Failed to decompress base64/gzip data: {e}")

    if len(uncompressed) < 98:
        raise ValueError(
            f"Payload too short ({len(uncompressed)} bytes). Expected at least 98 bytes."
        )

    header = uncompressed[:2]
    payload = uncompressed[2:98]
    trailer = uncompressed[98:]

    bands = []
    for i in range(8):
        chunk = payload[i * 12 : (i + 1) * 12]
        gain, freq, q = struct.unpack("<3f", chunk)
        bands.append(
            {
                "band": i + 1,
                "frequency_hz": round(freq, 1),
                "gain_db": round(gain, 2),
                "q_factor": round(q, 2),
            }
        )

    # Extract profile name
    name = "Custom Profile"
    if len(trailer) >= 2:
        str_len = trailer[1]
        if len(trailer) >= 2 + str_len:
            name = trailer[2 : 2 + str_len].decode("utf-8", errors="replace")

    return {
        "name": name,
        "header_hex": header.hex(),
        "bands": bands,
    }


def find_qr_in_image(image_path: str) -> str:
    """
    Scans an image or screenshot for a QR code using pyzbar and OpenCV fallbacks.
    Tolerant of complex screenshots, dark/light UI modes, and high resolutions.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file does not exist: {image_path}")

    # --- Strategy 1: PyZbar ---
    if pyzbar_decode is not None:
        try:
            if Image is not None:
                img = Image.open(path)
                results = pyzbar_decode(img)
            elif cv2 is not None:
                img = cv2.imread(str(path))
                results = pyzbar_decode(img)
            else:
                results = []

            for r in results:
                if r.data:
                    return r.data.decode("utf-8", errors="ignore")
        except Exception:
            pass

    # --- Strategy 2: OpenCV Fallbacks ---
    if cv2 is not None:
        cv_img = cv2.imread(str(path))
        if cv_img is None:
            raise ValueError(f"OpenCV could not open image file: {image_path}")

        detectors = []
        if hasattr(cv2, "QRCodeDetectorAruco"):
            detectors.append(cv2.QRCodeDetectorAruco())
        detectors.append(cv2.QRCodeDetector())

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        variants = [
            gray,
            cv_img,
            cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1],
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 5
            ),
        ]

        # Multi-scale resizing for phone screenshots
        if max(h, w) > 1500:
            scale = 1200 / max(h, w)
            variants.append(cv2.resize(gray, (int(w * scale), int(h * scale))))

        for detector in detectors:
            for var in variants:
                val, _, _ = detector.detectAndDecode(var)
                if val:
                    return val

                _, multi_vals, _, _ = detector.detectAndDecodeMulti(var)
                for item in multi_vals:
                    if item:
                        return item

        # Strategy 3: Crop potential square UI bounding boxes
        edges = cv2.Canny(gray, 100, 200)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, kernel)
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        min_dim = min(h, w)
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect_ratio = float(bw) / float(bh)
            if 0.8 <= aspect_ratio <= 1.25 and (bw * bh) >= (min_dim * 0.1) ** 2:
                pad = int(min(bw, bh) * 0.1)
                x0, y0 = max(0, x - pad), max(0, y - pad)
                x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
                cropped = gray[y0:y1, x0:x1]

                for detector in detectors:
                    val, _, _ = detector.detectAndDecode(cropped)
                    if val:
                        return val

    # Helpful diagnostics if detection failed
    hints = []
    if pyzbar_decode is None:
        hints.append("pyzbar / libzbar0 (Recommended for screenshots)")
    if cv2 is None:
        hints.append("opencv-python")

    msg = "Could not find or decode a QR code in the image."
    if hints:
        msg += f"\n[!] Missing modules: {', '.join(hints)}. Install via requirements.txt."
    raise RuntimeError(msg)


def print_eq_profile(eq_data: dict, raw_text: Optional[str] = None):
    """Prints a clean ASCII table of the EQ profile."""
    name = eq_data["name"]
    bands = eq_data["bands"]

    border = "=" * 66
    divider = "-" * 66

    print("\n" + border)
    print(f"{'NOTHING X ADVANCED EQ PROFILE':^66}")
    print(border)
    print(f" Profile Name : {name}")
    print(f" Total Bands  : {len(bands)}")
    print(divider)
    print(
        f" {'Band #':<8} | {'Frequency (Hz)':<16} | {'Gain (dB)':<14} | {'Q Factor':<12} "
    )
    print(divider)
    for b in bands:
        freq_str = f"{b['frequency_hz']:g} Hz"
        gain_val = b["gain_db"]
        gain_str = f"{gain_val:+.2f} dB" if gain_val != 0 else " 0.00 dB"
        q_str = f"{b['q_factor']:.2f}"
        print(
            f"   {b['band']:<6} | {freq_str:>14}   | {gain_str:>12}   | {q_str:>10}  "
        )
    print(border)


def export_to_csv(eq_data: dict, output_path: str):
    """Exports the EQ bands to a CSV file without markdown comments or band numbers."""
    path = Path(output_path)
    with path.open(mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Frequency (Hz)", "Gain (dB)", "Q Factor"])
        for b in eq_data["bands"]:
            writer.writerow(
                [b["frequency_hz"], b["gain_db"], b["q_factor"]]
            )
    print(f"[✓] Successfully exported EQ profile to: {path.resolve()}")


def sanitize_filename(name: str) -> str:
    """Sanitizes profile name for safe file paths across Windows & Linux."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return sanitized.replace(" ", "_") or "profile"


def main():
    parser = argparse.ArgumentParser(
        description="Decode Nothing X Advanced EQ profiles from images, screenshots, or raw text strings."
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        help="Path to screenshot or image containing the EQ QR code.",
    )
    parser.add_argument(
        "--string",
        "-s",
        help="Directly pass the raw QR base64 text payload instead of an image.",
    )
    parser.add_argument(
        "--csv",
        "-c",
        nargs="?",
        const="",
        default=None,
        help="Export results to CSV. Defaults to '<profile_name>.csv' if no name is given.",
    )

    args = parser.parse_args()

    # Determine input
    raw_str = None
    if args.string:
        raw_str = args.string
    elif args.image_path:
        try:
            print(f"[*] Scanning '{args.image_path}' for QR code...")
            raw_str = find_qr_in_image(args.image_path)
            print("[✓] QR code found and extracted.")
        except Exception as e:
            print(f"[X] Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Decode Nothing X binary payload
    try:
        eq_data = decode_nothing_x_payload(raw_str)
    except Exception as e:
        print(f"[X] Found QR code, but failed to parse Nothing X profile: {e}")
        print(f"Raw QR content:\n{raw_str}")
        sys.exit(1)

    # Print table
    print_eq_profile(eq_data)

    # Export to CSV
    if args.csv is not None:
        if args.csv == "":
            filename = f"{sanitize_filename(eq_data['name'])}.csv"
        else:
            filename = args.csv
        export_to_csv(eq_data, filename)


if __name__ == "__main__":
    main()
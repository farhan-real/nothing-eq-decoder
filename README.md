# Nothing X Advanced EQ Decoder & Encoder

A cross-platform Python toolkit to extract, decode, edit, and generate **Nothing X** 8-band Advanced EQ profiles from images (PNG, JPG, WEBP, BMP), CSV files, or raw QR payloads.

Compatible with **Windows** and **Linux**.

---

## Features

- **Screenshot & Cluttered Image Tolerant**: Automatically isolates and decodes QR codes from screenshots, photos, and dark/light mode interfaces across standard formats (PNG, JPG/JPEG, WEBP, BMP).
- **Binary Format Parsing**: Decodes Nothing X's proprietary Gzip-compressed binary structure into human-readable parameters:
  - Profile Name
  - 8 Bands: Frequency (Hz), Gain (dB), and Q Factor
- **Hardware Limit Validation**: Automatically checks frequencies, gain (-6 to +6 dB), and Q factors (0.1 to 10.0) against Nothing's official hardware limits.
- **Working Nothing-Style QR Generator**: Generates scanner-compliant QR codes featuring Nothing's signature dot-matrix modules, rounded eyes, and central earbud emblem.
- **Full Share Poster Mode**: Optionally creates the complete 9:16 Nothing share card with frequency response curve preview.
- **CSV Import & Export**: Export profiles or create new profiles to and from CSV.
- **Direct String Mode**: Can parse and generate raw Base64 QR text payloads directly.

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/farhan-real/nothing-eq-decoder.git
cd nothing-eq-decoder
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Linux-Specific Requirement
On Linux distributions, `pyzbar` requires the system ZBar shared library:

- **Debian / Ubuntu / Mint**:
  ```bash
  sudo apt-get update && sudo apt-get install -y libzbar0
  ```
- **Fedora / RHEL**:
  ```bash
  sudo dnf install zbar
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -S zbar
  ```

*(On Windows, `pip install pyzbar` includes all required DLLs automatically).*

---

## Usage

### 1. Decoding (`decoder.py`)

#### Scan an Image or Screenshot (PNG, JPG, WEBP, BMP)
```bash
python decoder.py screenshot.png
```

#### Scan and Export to CSV
Export using the profile's name automatically (`<profile_name>.csv`):
```bash
python decoder.py screenshot.png --csv
```

Or specify a custom CSV output path:
```bash
python decoder.py screenshot.png --csv my_profile.csv
```

#### Decode from Raw Text / Base64 String
```bash
python decoder.py -s "H4sIAAAAAAAA/2NIYGBocGBgqHA6e8bHHsL+5WRsbAxkH7BnaDjuPGvmTCCb4QDDgUoXY+PNIDZIDZStAGRXuYLVMjQA8S9XqBogqHIDmcPIk5ZYlJGYp1tSmpeaAgAeLOEhcAAAAA=="
```

---

### 2. Encoding (`encoder.py`)

#### Generate a Nothing-Style QR Code from CSV
Takes an 8-band CSV file, validates each band against hardware limits, and creates `<profile_name>_qr.png`:
```bash
python encoder.py farhan-tuned.csv
```
*(By default, it uses the CSV filename without the extension as the profile name).*

#### Specify a Custom Profile Name
```bash
python encoder.py input.csv --name "Custom Bass"
```

#### Generate Full Share Poster
Generates both the standalone QR card and the full 9:16 Nothing share poster:
```bash
python encoder.py farhan-tuned.csv --card --author "Farhan"
```

---

## Hardware Limits Reference

The encoder automatically validates your CSV data against Nothing's parametric EQ hardware specifications:

| Band | Frequency Range | Gain Limit | Q Factor Limit |
|:---:|:---|:---|:---|
| **1** | 20–99 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **2** | 100–199 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **3** | 200–399 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **4** | 400–999 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **5** | 1,000–2,999 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **6** | 3,000–5,999 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **7** | 6,000–11,999 Hz | -6.0 to +6.0 dB | 0.1–10.0 |
| **8** | 12,000–20,000 Hz | -6.0 to +6.0 dB | 0.1–10.0 |

---

## Example Output

### Terminal Output (`decoder.py`)

```text
[*] Scanning 'screenshot.png' for QR code...
[✓] QR code found and extracted.

==================================================================
                  NOTHING X ADVANCED EQ PROFILE                   
==================================================================
 Profile Name : farhan-tuned
 Total Bands  : 8
------------------------------------------------------------------
 Band #   | Frequency (Hz)   | Gain (dB)      | Q Factor     
------------------------------------------------------------------
   1      |          62 Hz   |     +4.00 dB   |       0.80  
   2      |         125 Hz   |     +4.00 dB   |       0.70  
   3      |         399 Hz   |     +1.50 dB   |       1.20  
   4      |         999 Hz   |     -2.00 dB   |       1.40  
   5      |        2000 Hz   |     +2.00 dB   |       1.40  
   6      |        4000 Hz   |     +2.50 dB   |       1.50  
   7      |        8000 Hz   |     +1.00 dB   |       1.40  
   8      |       16000 Hz   |      0.00 dB   |       0.70  
==================================================================

[✓] Successfully exported EQ profile to: /path/to/farhan-tuned.csv
```

### CSV Format
```csv
Frequency (Hz),Gain (dB),Q Factor
62.0,4.0,0.8
125.0,4.0,0.7
399.0,1.5,1.2
999.0,-2.0,1.4
2000.0,2.0,1.4
4000.0,2.5,1.5
8000.0,1.0,1.4
16000.0,0.0,0.7
```

---

## License

MIT License. Feel free to modify and distribute.
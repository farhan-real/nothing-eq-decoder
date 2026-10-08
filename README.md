# Nothing X Advanced EQ QR Code Decoder

A cross-platform Python tool to extract, decode, and export **Nothing X** 8-band Advanced EQ profiles from screenshots, image files, or raw QR text strings.

Compatible with **Windows** and **Linux**.

---

## Features

- **Screenshot & Cluttered Image Tolerant**: Automatically isolates and decodes QR codes embedded inside phone screenshots, social media posts, and dark/light mode interfaces.
- **Binary Format Parsing**: Decodes Nothing X's proprietary Gzip-compressed binary structure into human-readable parameters:
  - Profile Name
  - 8 Bands: Frequency (Hz), Gain (dB), and Q Factor
- **Formatted Terminal Table**: Clean ASCII display for easy reference.
- **CSV Export**: Export profiles to CSV files for spreadsheets, backup, or importing into Equalizer APO / Peace EQ.
- **Direct String Mode**: Can parse raw Base64 QR text directly without requiring an image.

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/nothing-x-eq-parser.git
cd nothing-x-eq-parser
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Linux-Specific Requirement
On Linux distributions, `pyzbar` requires the system ZBar shared library. Install it using your package manager:

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

### 1. Scan a Screenshot
```bash
python main.py screenshot.png
```

### 2. Scan and Export to CSV
Export using the profile's name automatically (`<profile_name>.csv`):
```bash
python main.py screenshot.png --csv
```

Or specify a custom CSV output path:
```bash
python main.py screenshot.png --csv my_profile.csv
```

### 3. Decode from Raw Text / Base64 String
If you already scanned the QR code with another app or copied the text from a forum:
```bash
python main.py -s "H4sIAAAAAAAA/2NIYGBocGBgqHA6e8bHHsL+5WRsbAxkH7BnaDjuPGvmTCCb4QDDgUoXY+PNIDZIDZStAGRXuYLVMjQA8S9XqBogqHIDmcPIk5ZYlJGYp1tSmpeaAgAeLOEhcAAAAA=="
```

---

## Example Output

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

### Exported CSV Structure
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
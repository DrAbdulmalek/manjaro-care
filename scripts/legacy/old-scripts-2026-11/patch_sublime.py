#!/usr/bin/env python3
import sys
from pathlib import Path


def main():
    # Locate binary
    if len(sys.argv) > 1:
        bin_path = Path(sys.argv[1])
    else:
        bin_path = Path("/opt/sublime_text/sublime_text")
    if not bin_path.exists():
        print(f"Binary not found: {bin_path}")
        sys.exit(1)

    print(f"Patching {bin_path}")

    # Read the file
    data = bytearray(bin_path.read_bytes())

    # Search for pattern: 80 79 05 00 ?? ?? ??
    # We want 80 79 05 00 followed by 0F 94 C? (C0, C1, C2)
    pattern = bytes([0x80, 0x79, 0x05, 0x00])
    replacement = bytes([0xC6, 0x41, 0x05, 0x01, 0xB2, 0x00, 0x90])

    found = False
    offset = 0
    while offset < len(data) - 7:
        if data[offset:offset+4] == pattern:
            # Check next two bytes: 0F 94 C?
            if data[offset+4] == 0x0F and data[offset+5] == 0x94 and data[offset+6] in (0xC0, 0xC1, 0xC2):
                print(f"Found at offset 0x{offset:08x}: {data[offset:offset+7].hex()}")
                # Backup
                backup = bin_path.with_suffix(bin_path.suffix + ".bak")
                if not backup.exists():
                    bin_path.rename(backup)
                    print(f"Backup created: {backup}")
                # Apply patch
                data[offset:offset+7] = replacement
                found = True
                break
        offset += 1

    if not found:
        print("Pattern not found. Exiting.")
        sys.exit(1)

    # Write back
    bin_path.write_bytes(data)
    print("Patched successfully.")
    # Make executable (Linux only)
    if sys.platform.startswith('linux'):
        bin_path.chmod(0o755)
    print("Done. Start Sublime Text and enter any license key.")

if __name__ == "__main__":
    main()

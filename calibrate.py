"""
Prints a single line of ruler-style text (a row of numbers/markers)
at a specified left margin, with an optional double-height toggle,
so we can test whether font_height interferes with the left margin
command. No word wrap, no top margin, no line spacing changes.

Usage:
    python calibrate_left_margin.py <left_margin_inches> [double_height]

Example:
    python calibrate_left_margin.py 0.25
    python calibrate_left_margin.py 0.25 double_height
    python calibrate_left_margin.py 1.5 double_height

Print a few values back to back, with and without double_height, and
compare where the text starts on each line.

Windows only.
"""

import sys

import win32print

PRINTER_NAME = "EPSON FX-2190II ESC/P"
CHARACTERS_PER_INCH = 10  # fixed for this test, independent of settings.json


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python calibrate_left_margin.py <left_margin_inches> [double_height]")
        sys.exit(1)

    try:
        left_margin_inches = float(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid number.")
        sys.exit(1)

    use_double_height = len(sys.argv) == 3 and sys.argv[2] == "double_height"

    left_margin_chars = round(left_margin_inches * CHARACTERS_PER_INCH)

    handle = win32print.OpenPrinter(PRINTER_NAME)
    win32print.StartDocPrinter(handle, 1, ("Left Margin Test", None, "RAW"))
    win32print.StartPagePrinter(handle)

    try:
        win32print.WritePrinter(handle, bytes([0x1B, 0x40]))  # ESC @ reset
        win32print.WritePrinter(handle, bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l

        if use_double_height:
            win32print.WritePrinter(handle, bytes([0x1B, 0x77, 1]))  # ESC w 1

        label = (
            f"MARGIN={left_margin_inches}in ({left_margin_chars}chars) "
            f"DH={use_double_height} >>> HERE\r\n"
        )
        win32print.WritePrinter(handle, label.encode("ascii"))
        win32print.WritePrinter(handle, b"\x0c")  # form feed
    finally:
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
        win32print.ClosePrinter(handle)

    print(
        f"Printed test line at left_margin_inches={left_margin_inches} "
        f"({left_margin_chars} character positions), double_height={use_double_height}."
    )


if __name__ == "__main__":
    main()
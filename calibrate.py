"""
Prints a single line of ruler-style text (a row of numbers/markers)
at a specified left margin, with an optional double-height toggle,
so we can test whether font_height interferes with the left margin
command. No word wrap, no top margin, no line spacing changes.

Also supports --full-sequence, which replicates print_docx_loop.py's
exact set_page_format() + print_top_margin() command order (right
margin, ESC w, ESC 3 line spacing, ESC W, then top margin blank
lines) before printing the test line -- to check whether the bug
only appears when the FULL real command sequence runs, not just
ESC l and ESC w in isolation.

Usage:
    python calibrate_left_margin.py <left_margin_inches> [double_height] [--full-sequence]

Windows only.
"""

import sys

import win32print

PRINTER_NAME = "EPSON FX-2190II ESC/P"
CHARACTERS_PER_INCH = 10


def main() -> None:
    args = sys.argv[1:]
    full_sequence = "--full-sequence" in args
    args = [a for a in args if a != "--full-sequence"]

    if len(args) not in (1, 2):
        print("Usage: python calibrate_left_margin.py <left_margin_inches> [double_height] [--full-sequence]")
        sys.exit(1)

    try:
        left_margin_inches = float(args[0])
    except ValueError:
        print(f"Error: '{args[0]}' is not a valid number.")
        sys.exit(1)

    use_double_height = len(args) == 2 and args[1] == "double_height"

    left_margin_chars = round(left_margin_inches * CHARACTERS_PER_INCH)

    handle = win32print.OpenPrinter(PRINTER_NAME)
    win32print.StartDocPrinter(handle, 1, ("Left Margin Test", None, "RAW"))
    win32print.StartPagePrinter(handle)

    try:
        win32print.WritePrinter(handle, bytes([0x1B, 0x40]))  # ESC @ reset

        if full_sequence:
            # Replicate set_page_format()'s exact command order.
            right_margin_inches = 0.75
            right_margin_position_inches = 8.5 - right_margin_inches
            right_margin_chars = round(right_margin_position_inches * CHARACTERS_PER_INCH)

            win32print.WritePrinter(handle, bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
            win32print.WritePrinter(handle, bytes([0x1B, 0x51, right_margin_chars]))  # ESC Q
            win32print.WritePrinter(handle, bytes([0x1B, 0x77, 1 if use_double_height else 0]))  # ESC w

            line_spacing = 2.25
            line_units = round(30 * line_spacing)
            win32print.WritePrinter(handle, bytes([0x1B, 0x33, line_units]))  # ESC 3
            win32print.WritePrinter(handle, bytes([0x1B, 0x57, 0]))  # ESC W (font_width=1)

            # print_top_margin(): feed blank lines for top_margin_inches
            line_height_inches = line_units / 180
            top_margin_inches = 1.5
            blank_lines = round(top_margin_inches / line_height_inches)
            win32print.WritePrinter(handle, b"\r\n" * blank_lines)
        else:
            win32print.WritePrinter(handle, bytes([0x1B, 0x6C, left_margin_chars]))  # ESC l
            if use_double_height:
                win32print.WritePrinter(handle, bytes([0x1B, 0x77, 1]))  # ESC w 1

        label = (
            f"MARGIN={left_margin_inches}in ({left_margin_chars}chars) "
            f"DH={use_double_height} FULL={full_sequence} >>> HERE\r\n"
        )
        win32print.WritePrinter(handle, label.encode("ascii"))
        win32print.WritePrinter(handle, b"\x0c")  # form feed
    finally:
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
        win32print.ClosePrinter(handle)

    print(
        f"Printed test line at left_margin_inches={left_margin_inches} "
        f"({left_margin_chars} character positions), "
        f"double_height={use_double_height}, full_sequence={full_sequence}."
    )


if __name__ == "__main__":
    main()
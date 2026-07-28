"""
Continuously print pages from a PDF, one page per interval, waiting
between each print. Each PDF page is rendered as a 1-bit (black and
white) bitmap image and sent to the printer using ESC/P raster
graphics mode, rather than extracting/printing text — this sidesteps
font/encoding/word-wrap issues entirely, since the printer just
reproduces the page's actual pixels.

All timing is read from settings.json so it can be changed without
editing this file. Page layout (fonts, spacing, story packing) is no
longer this script's concern at all — that's handled upstream, in
the Google Doc itself, via the Apps Script tools that repack stories
onto pages before the PDF is exported.

The program stops automatically once it has printed every page in
the PDF.

Works on:
  - Windows: sends raw bytes through the existing Windows print
    driver via pywin32 (no libusb/Zadig needed)
  - macOS/Linux: talks directly to the USB device via pyusb
"""

import json
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF

SETTINGS_FILE = Path("settings.json")

IS_WINDOWS = sys.platform.startswith("win")

# ---- Windows-specific setup ----------------------------------------------
if IS_WINDOWS:
    import win32print

    # Must match the exact name shown in Windows' Devices and Printers
    PRINTER_NAME = "EPSON FX-2190II ESC/P"

# ---- macOS/Linux-specific setup -------------------------------------------
else:
    import usb.core
    import usb.util

    EPSON_VENDOR_ID = 0x04B8

# ---------------------------------------------------------------------------
# ESC/P raster graphics parameters.
#
# ESC * m nL nH data... selects "bit image" mode. Mode 33 is
# "high-resolution double-density" on FX-series printers: 240 dots
# per inch horizontally, 180 dots per inch vertically is NOT how
# ESC * works — ESC * addresses horizontal density only; vertical
# resolution is fixed by how many 8-dot-tall strips you send (each
# strip is 1/60th, 1/120th, etc. of an inch tall depending on mode).
#
# Mode 33 (double-density, unidirectional, 240 dpi horizontal) at
# 180 dpi vertical strip height keeps things square-ish for a
# reasonably crisp, reasonably fast print. Adjust PRINT_DPI to
# change output resolution/print speed together.
# ---------------------------------------------------------------------------
ESCP_GRAPHICS_MODE = 33  # 240 dpi horizontal, 8 vertical dots per strip
PRINT_DPI = 240  # rendering resolution for both axes; must match the
                  # printer's horizontal dpi for the chosen graphics mode


# ---------------------------------------------------------------------------
# Output abstraction: both platforms expose a simple `.write(bytes)` object
# so all the printing logic below stays identical either way.
# ---------------------------------------------------------------------------

class WindowsPrinterOutput:
    """Wraps win32print raw-mode printing so it behaves like output_endpoint.write()."""

    def __init__(self, printer_name):
        self.printer_name = printer_name
        self.handle = win32print.OpenPrinter(printer_name)
        self._doc_open = False

    def start_job(self):
        win32print.StartDocPrinter(self.handle, 1, ("ESC/P Job", None, "RAW"))
        self._doc_open = True

    def write(self, data: bytes):
        if not self._doc_open:
            self.start_job()
        win32print.WritePrinter(self.handle, data)

    def end_job(self):
        if self._doc_open:
            win32print.EndDocPrinter(self.handle)
            self._doc_open = False

    def close(self):
        self.end_job()
        win32print.ClosePrinter(self.handle)


def load_settings() -> dict:
    with SETTINGS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def find_printer():
    """macOS/Linux only: locate the USB device."""
    printer = usb.core.find(idVendor=EPSON_VENDOR_ID)
    if printer is None:
        raise RuntimeError("No Epson USB printer was found.")
    return printer


def find_output_endpoint(printer):
    """macOS/Linux only: locate the USB OUT endpoint."""
    printer.set_configuration()
    configuration = printer.get_active_configuration()

    for interface in configuration:
        if interface.bInterfaceClass != 7:
            continue
        for endpoint in interface:
            direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
            if direction == usb.util.ENDPOINT_OUT:
                return interface, endpoint

    raise RuntimeError("Could not find the printer output endpoint.")


def render_page_to_1bit(pdf_path: Path, page_number: int, dpi: int):
    """
    Render one page (0-indexed) of the PDF to a 1-bit (black/white)
    Pillow image at the given DPI.
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_number)
        zoom = dpi / 72  # PDF points are 1/72 inch; fitz matrix is in that unit
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY)

        # PyMuPDF pixmap -> Pillow image
        from PIL import Image
        image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)

        # Convert to 1-bit using a simple threshold with dithering,
        # so the printer gets a clean black/white bitmap.
        image_1bit = image.convert("1", dither=Image.FLOYDSTEINBERG)
        return image_1bit
    finally:
        doc.close()


def get_page_count(pdf_path: Path) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def image_to_escp_raster(image, graphics_mode: int) -> bytes:
    """
    Convert a 1-bit Pillow image into a sequence of ESC/P
    "bit image" (ESC * m nL nH data) commands, one command per
    8-pixel-tall horizontal strip, printing top to bottom.

    Between strips, a line feed (without extra vertical movement
    beyond what the graphics mode already accounts for) advances to
    the next strip. Because ESC/P bit-image mode already advances
    the print head by exactly 8 dots' worth of paper per strip when
    followed by a plain line feed at the configured line spacing,
    we explicitly set line spacing to match 8 dots before printing
    strips, then restore it after.
    """
    width, height = image.size
    pixels = image.load()

    output = bytearray()

    # Set line spacing to 8/180 inch per strip, i.e. exactly the
    # height of one 8-dot strip at 180 units/inch, so consecutive
    # strips tile with no gaps or overlaps.
    output += bytes([0x1B, 0x33, 8])  # ESC 3 n -> n/180 inch line spacing

    n_l = width % 256
    n_h = width // 256

    for strip_top in range(0, height, 8):
        strip_bytes = bytearray()
        for x in range(width):
            byte = 0
            for bit in range(8):
                y = strip_top + bit
                if y < height:
                    # In "1" mode Pillow images, 0 = black, 255 = white.
                    pixel_is_black = pixels[x, y] == 0
                    if pixel_is_black:
                        byte |= 1 << (7 - bit)
            strip_bytes.append(byte)

        output += bytes([0x1B, 0x2A, graphics_mode, n_l, n_h])
        output += bytes(strip_bytes)
        output += b"\r\n"  # advance to next strip (8 dots, per line spacing set above)

    return bytes(output)


def print_pdf_page(output, settings: dict, pdf_path: Path, page_number: int) -> None:
    image = render_page_to_1bit(pdf_path, page_number, PRINT_DPI)
    raster_data = image_to_escp_raster(image, ESCP_GRAPHICS_MODE)

    output.write(b"\x1b@")  # reset to defaults
    output.write(raster_data)
    output.write(b"\x0c")  # form feed to eject the page


def main() -> None:
    settings = load_settings()
    pdf_path = Path(settings["pdf_path"])

    if not pdf_path.is_file():
        print(f"Error: '{pdf_path}' is not a valid file.")
        sys.exit(1)

    page_count = get_page_count(pdf_path)

    if IS_WINDOWS:
        output = WindowsPrinterOutput(PRINTER_NAME)
    else:
        printer = find_printer()
        interface, output = find_output_endpoint(printer)
        usb.util.claim_interface(printer, interface.bInterfaceNumber)

    page_number = 0  # 0-indexed for PyMuPDF

    try:
        while page_number < page_count:
            # Re-read settings each loop, so the delay can be
            # changed without restarting the program.
            settings = load_settings()

            if IS_WINDOWS:
                output.start_job()

            print_pdf_page(output, settings, pdf_path, page_number)

            if IS_WINDOWS:
                output.end_job()

            print(f"Printed page {page_number + 1} of {page_count}")

            page_number += 1

            if page_number < page_count:
                print(f"Waiting {settings['print_delay_seconds']} seconds...\n")
                time.sleep(settings["print_delay_seconds"])

        print("All pages printed. Stopping.")

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        if IS_WINDOWS:
            output.close()
        else:
            usb.util.release_interface(printer, interface.bInterfaceNumber)
            usb.util.dispose_resources(printer)


if __name__ == "__main__":
    main()
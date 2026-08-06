import os
import win32print
from pypdf import PdfReader

# 1. Path to input file
input_path = os.path.join("news_files", "news.pdf")

# 2. Extract text from Page 1 (index 0)
reader = PdfReader(input_path)
page_1_text = reader.pages[0].extract_text()

# Add Form Feed control character (\x0c) so fan-fold paper advances to next page seam
print_data = page_1_text + "\x0c"

# 3. Stream text directly to the Epson FX-2190II in RAW mode
printer_name = win32print.GetDefaultPrinter()
print(f"Sending Page 1 ASCII text to: {printer_name}")

hPrinter = win32print.OpenPrinter(printer_name)
try:
    hJob = win32print.StartDocPrinter(hPrinter, 1, ("Page 1 Print", None, "RAW"))
    win32print.StartPagePrinter(hPrinter)
    win32print.WritePrinter(hPrinter, print_data.encode("ascii", "ignore"))
    win32print.EndPagePrinter(hPrinter)
    win32print.EndDocPrinter(hPrinter)
finally:
    win32print.ClosePrinter(hPrinter)
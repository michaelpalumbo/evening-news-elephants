"""
Split news.docx into one .docx file per REAL rendered page, using
LibreOffice's own layout engine via the UNO API -- not an estimate,
not a manual marker. LibreOffice actually lays the document out the
same way it would for printing/viewing, and we ask it directly which
page each piece of text landed on.

Output: news_docs/news1.docx, news_docs/news2.docx, etc.

This script:
  1. Starts a headless LibreOffice instance listening on a local
     socket.
  2. Connects to it via UNO.
  3. Opens news.docx.
  4. Walks the document's real page layout (via a ViewCursor moved
     page by page) to find where each page's content begins and
     ends.
  5. For each page, creates a copy of the document, deletes
     everything outside that page's paragraph range, and saves it
     as its own .docx.
  6. Closes LibreOffice.

Usage:

run this first:  this oooenv env -t
    then: python split_docx_by_page.py <path_to_docx>

Windows only (paths/LibreOffice executable location assume Windows;
adjust LIBREOFFICE_EXE for other platforms).
"""

import subprocess
import sys
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue

LIBREOFFICE_EXE = r"C:\Program Files\LibreOffice\program\soffice.exe"
UNO_PORT = 2002
OUTPUT_FOLDER = Path("news_docs")
OUTPUT_PREFIX = "news"


def start_libreoffice_listener() -> subprocess.Popen:
    """
    Launches headless LibreOffice listening for UNO connections on
    UNO_PORT. Returns the process handle so it can be terminated
    later.
    """
    process = subprocess.Popen([
        LIBREOFFICE_EXE,
        "--headless",
        "--norestore",
        "--invisible",
        f"--accept=socket,host=localhost,port={UNO_PORT};urp;",
    ])
    return process


def connect_to_libreoffice(max_attempts: int = 20, delay_seconds: float = 1.0):
    """
    Connects to the headless LibreOffice listener via UNO, retrying
    for a few seconds since the listener takes a moment to become
    ready after being launched.
    """
    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_context
    )

    connection_url = (
        f"uno:socket,host=localhost,port={UNO_PORT};"
        f"urp;StarOffice.ComponentContext"
    )

    last_error = None
    for _ in range(max_attempts):
        try:
            context = resolver.resolve(connection_url)
            return context
        except Exception as e:
            last_error = e
            time.sleep(delay_seconds)

    raise RuntimeError(
        f"Could not connect to LibreOffice after {max_attempts} attempts."
    ) from last_error


def make_property_value(name: str, value) -> PropertyValue:
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def open_document(context, docx_path: Path):
    smgr = context.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", context)

    url = uno.systemPathToFileUrl(str(docx_path.resolve()))
    load_props = (make_property_value("Hidden", True),)

    document = desktop.loadComponentFromURL(url, "_blank", 0, load_props)
    return document


def find_paragraph_spanning_page_boundary(document, page_number: int):
    """
    Looks at the CURRENT live state of the document and finds the
    first paragraph whose start is on page_number but whose end is
    on a LATER page (i.e. it visually spans the boundary between
    page_number and the next page). Returns that paragraph, or None
    if no such paragraph exists on this page right now.
    """
    text = document.getText()
    view_cursor = document.getCurrentController().getViewCursor()

    for paragraph in list_paragraphs(text):
        view_cursor.gotoRange(paragraph.getStart(), False)
        start_page = view_cursor.getPage()

        if start_page != page_number:
            continue

        view_cursor.gotoRange(paragraph.getEnd(), False)
        end_page = view_cursor.getPage()

        if end_page > page_number:
            return paragraph

    return None


def move_paragraph_to_next_page(document, paragraph) -> None:
    """
    Inserts a page break immediately before the given paragraph, so
    the whole paragraph -- rather than just part of it -- starts
    fresh on the next page.
    """
    paragraph.BreakType = uno.Enum(
        "com.sun.star.style.BreakType", "PAGE_BEFORE"
    )


def repaginate_spanning_paragraphs(document, max_pages: int) -> None:
    """
    Walks pages 1 through max_pages IN ORDER, on the document's
    current live state (not a pre-computed snapshot). For each page,
    repeatedly finds and moves forward any paragraph spanning into
    the next page, until that page has no more spanning paragraphs
    -- then moves on to the next page number, whose content may now
    include a paragraph that was just pushed into it.
    """
    page_number = 1
    while page_number <= max_pages:
        spanning_paragraph = find_paragraph_spanning_page_boundary(document, page_number)

        if spanning_paragraph is not None:
            move_paragraph_to_next_page(document, spanning_paragraph)
            # Re-check the SAME page number again, in case moving
            # that paragraph reveals another spanning paragraph now
            # sitting at this page's new boundary.
            continue

        page_number += 1


def get_page_count(document) -> int:
    """
    LibreOffice knows the true, rendered page count via the
    document's print settings / layout -- this is the real number,
    computed the same way it would be for printing or the page
    counter shown in the UI.
    """
    return document.getCurrentController().PageCount


def save_document_copy(document, output_path: Path) -> None:
    output_url = uno.systemPathToFileUrl(str(output_path.resolve()))
    save_props = (make_property_value("FilterName", "MS Word 2007 XML"),)
    document.storeToURL(output_url, save_props)


def list_paragraphs(text):
    enumeration = text.createEnumeration()
    paragraphs = []
    while enumeration.hasMoreElements():
        paragraph = enumeration.nextElement()
        if paragraph.supportsService("com.sun.star.text.Paragraph"):
            paragraphs.append(paragraph)
    return paragraphs


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python split_docx_by_page.py <path_to_docx> [max_pages]")
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    if not docx_path.is_file():
        print(f"Error: '{docx_path}' was not found.")
        sys.exit(1)

    max_pages = None
    if len(sys.argv) == 3:
        try:
            max_pages = int(sys.argv[2])
        except ValueError:
            print(f"Error: '{sys.argv[2]}' is not a valid number of pages.")
            sys.exit(1)
        if max_pages < 1:
            print("Error: max_pages must be 1 or greater.")
            sys.exit(1)

    print("Starting LibreOffice...")
    lo_process = start_libreoffice_listener()

    try:
        print("Connecting to LibreOffice via UNO...")
        context = connect_to_libreoffice()

        print(f"Opening {docx_path}...")
        document = open_document(context, docx_path)

        try:
            page_count = get_page_count(document)
            print(f"Document has {page_count} real rendered page(s).")

            pages_to_process = max_pages if max_pages is not None else page_count
            print(f"Repaginating spanning paragraphs across pages 1-{pages_to_process}...")

            repaginate_spanning_paragraphs(document, pages_to_process)

            OUTPUT_FOLDER.mkdir(exist_ok=True)
            verification_path = OUTPUT_FOLDER / "spacedDoc.docx"
            save_document_copy(document, verification_path)
            print(f"Saved {verification_path} for verification.")

        finally:
            document.close(False)

    finally:
        print("Closing LibreOffice...")
        lo_process.terminate()


if __name__ == "__main__":
    main()
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
OUTPUT_FOLDER = Path("news_files")
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


def repaginate_spanning_paragraphs(document, max_pages=None) -> None:
    """
    Single forward pass over the paragraphs. Inserting a page break
    only changes layout from that point on, so each paragraph's
    page is read from the live layout as we reach it. Paragraphs
    already at the top of a page but still spanning (longer than a
    page) are left alone, since a break can't fix them.
    """
    text = document.getText()
    view_cursor = document.getCurrentController().getViewCursor()
    paragraphs = list_paragraphs(text)
    page_break = uno.Enum("com.sun.star.style.BreakType", "PAGE_BEFORE")

    previous_end_page = 0
    moved = 0
    too_long = 0
    total = len(paragraphs)

    for index, paragraph in enumerate(paragraphs, start=1):
        view_cursor.gotoRange(paragraph.getStart(), False)
        start_page = view_cursor.getPage()

        if max_pages is not None and start_page > max_pages:
            break

        view_cursor.gotoRange(paragraph.getEnd(), False)
        end_page = view_cursor.getPage()

        if end_page > start_page:
            at_top_of_page = start_page > previous_end_page
            if at_top_of_page:
                too_long += 1
            else:
                paragraph.BreakType = page_break
                moved += 1
                view_cursor.gotoRange(paragraph.getEnd(), False)
                end_page = view_cursor.getPage()

        previous_end_page = end_page

        if index % 50 == 0 or index == total:
            print(f"  {index}/{total} paragraphs checked, "
                  f"{moved} moved, now on page {end_page}")

    print(f"Moved {moved} paragraph(s) to the next page.")
    if too_long:
        print(f"Warning: {too_long} paragraph(s) are longer than a page "
              f"and still span a boundary.")


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

def split_into_pages(document, output_folder: Path) -> None:
    """
    For each rendered page: delete everything after it and before
    it, save what's left as its own .docx, then undo the deletions
    to get the full document back for the next page. Uses the live
    layout, so page boundaries match what LibreOffice renders.
    """
    controller = document.getCurrentController()
    view_cursor = controller.getViewCursor()
    text = document.getText()
    undo_manager = document.getUndoManager()
    no_break = uno.Enum("com.sun.star.style.BreakType", "NONE")

    page_count = controller.PageCount

    for page in range(1, page_count + 1):
        undo_manager.enterUndoContext(f"split page {page}")
        try:
            # Delete everything after this page.
            view_cursor.jumpToPage(page)
            view_cursor.jumpToEndOfPage()
            tail = text.createTextCursorByRange(view_cursor.getStart())
            tail.gotoEnd(True)
            tail.setString("")

            # Delete everything before this page.
            view_cursor.jumpToPage(page)
            view_cursor.jumpToStartOfPage()
            head = text.createTextCursorByRange(view_cursor.getStart())
            head.gotoStart(True)
            head.setString("")

            # The first paragraph may carry the page break we added,
            # which would otherwise leave a blank first page.
            text.createEnumeration().nextElement().BreakType = no_break
        finally:
            undo_manager.leaveUndoContext()

        output_path = output_folder / f"{OUTPUT_PREFIX}{page}.docx"
        save_document_copy(document, output_path)
        undo_manager.undo()

        if controller.PageCount != page_count:
            raise RuntimeError(
                f"Undo didn't restore the full document after page {page} "
                f"({controller.PageCount} pages instead of {page_count})."
            )

        print(f"  Saved {output_path} ({page}/{page_count})")

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

            print("Repaginating spanning paragraphs...")
            repaginate_spanning_paragraphs(document, max_pages)

            OUTPUT_FOLDER.mkdir(exist_ok=True)
            verification_path = OUTPUT_FOLDER / "spacedDoc.docx"
            save_document_copy(document, verification_path)
            print(f"Saved {verification_path} for verification.")

            print(f"Splitting into {get_page_count(document)} page file(s)...")
            split_into_pages(document, OUTPUT_FOLDER)
        finally:
            document.close(False)

    finally:
        print("Closing LibreOffice...")
        lo_process.terminate()


if __name__ == "__main__":
    main()
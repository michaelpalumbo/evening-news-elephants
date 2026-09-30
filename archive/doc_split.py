"""
Split a .docx into one .docx file per REAL rendered page, using
LibreOffice's own layout engine via the UNO API -- not an estimate,
not a manual marker. LibreOffice actually lays the document out the
same way it would for printing/viewing, and we ask it directly which
page each piece of text landed on.

Output: news_docs/news1.docx, news_docs/news2.docx, etc.
Also saves news_docs/spacedDoc.docx, the whole repaginated document,
for verification.

This script:
  1. Starts a headless LibreOffice instance listening on a local
     socket.
  2. Connects to it via UNO.
  3. Opens the source document.
  4. Walks the real page layout, moving any paragraph that spans a
     page boundary onto the next page so no paragraph is split.
  5. Records which page every paragraph landed on.
  6. For each page, reopens the repaginated document, deletes every
     paragraph not on that page, and saves the result as its own
     .docx.
  7. Closes LibreOffice.

Usage:
    run this first:  oooenv env -t
    then:            python split_docx.py <path_to_docx> [max_pages]

max_pages caps how many pages are processed and written, which is
useful for testing before committing to a long document.

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


def list_paragraphs(text):
    enumeration = text.createEnumeration()
    paragraphs = []
    while enumeration.hasMoreElements():
        paragraph = enumeration.nextElement()
        if paragraph.supportsService("com.sun.star.text.Paragraph"):
            paragraphs.append(paragraph)
    return paragraphs


def move_paragraph_to_next_page(paragraph) -> None:
    """
    Inserts a page break immediately before the given paragraph, so
    the whole paragraph -- rather than just part of it -- starts
    fresh on the next page.
    """
    paragraph.BreakType = uno.Enum(
        "com.sun.star.style.BreakType", "PAGE_BEFORE"
    )


def clear_page_break(paragraph) -> None:
    """
    Removes any page break attached to a paragraph. Used on the
    first paragraph of each split file, since a break carried over
    from repagination would leave a blank leading page.
    """
    paragraph.BreakType = uno.Enum(
        "com.sun.star.style.BreakType", "NONE"
    )


def repaginate_spanning_paragraphs(document, max_pages: int) -> None:
    """
    Walks the document's paragraphs in order, on its current live
    layout. Any paragraph whose start and end fall on different
    pages is pushed onto the next page with a page break, and then
    re-checked in case it still spans after moving.

    Resumes from where it left off rather than rescanning from the
    top each time, which matters on long documents -- each
    ViewCursor query forces LibreOffice to consult its layout, and
    inserting a break invalidates that layout.
    """
    text = document.getText()
    paragraphs = list_paragraphs(text)
    view_cursor = document.getCurrentController().getViewCursor()

    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]

        view_cursor.gotoRange(paragraph.getStart(), False)
        start_page = view_cursor.getPage()

        if start_page > max_pages:
            break

        view_cursor.gotoRange(paragraph.getEnd(), False)
        end_page = view_cursor.getPage()

        if end_page > start_page:
            print(
                f"  paragraph {index} spans pages "
                f"{start_page}-{end_page}, moving it forward."
            )
            move_paragraph_to_next_page(paragraph)
            # Re-check the same paragraph: it may still span even
            # after being moved to a fresh page.
            continue

        index += 1


def get_paragraph_page_map(document) -> list:
    """
    Returns a list of (paragraph_index, page_number) for every
    paragraph, read from the document's current live layout. Call
    this AFTER repagination, so the page numbers reflect the final
    layout.
    """
    text = document.getText()
    view_cursor = document.getCurrentController().getViewCursor()

    page_map = []
    for index, paragraph in enumerate(list_paragraphs(text)):
        view_cursor.gotoRange(paragraph.getStart(), False)
        page_map.append((index, view_cursor.getPage()))

    return page_map


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


def save_single_page(context, source_path: Path, page_map: list,
                     page_number: int, output_path: Path) -> bool:
    """
    Opens a fresh copy of the repaginated document, deletes every
    paragraph that isn't on page_number, and saves what's left.

    Returns True if a file was written, False if this page had no
    paragraphs on it.
    """
    keep = {index for index, page in page_map if page == page_number}

    if not keep:
        return False

    document = open_document(context, source_path)

    try:
        text = document.getText()
        paragraphs = list_paragraphs(text)

        # Delete from the end backwards so earlier indices stay
        # valid as we go.
        for index in reversed(range(len(paragraphs))):
            if index not in keep:
                text.removeTextContent(paragraphs[index])

        remaining = list_paragraphs(text)
        if remaining:
            clear_page_break(remaining[0])

        save_document_copy(document, output_path)

    finally:
        document.close(False)

    return True


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python split_docx.py <path_to_docx> [max_pages]")
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

        page_count = get_page_count(document)
        print(f"Document has {page_count} real rendered page(s).")

        pages_to_process = max_pages if max_pages is not None else page_count
        print(f"Repaginating spanning paragraphs across pages 1-{pages_to_process}...")

        repaginate_spanning_paragraphs(document, pages_to_process)

        OUTPUT_FOLDER.mkdir(exist_ok=True)

        repaginated_path = OUTPUT_FOLDER / "spacedDoc.docx"
        save_document_copy(document, repaginated_path)
        print(f"Saved {repaginated_path} for verification.")

        page_map = get_paragraph_page_map(document)

        if not page_map:
            print("No paragraphs found. Nothing to split.")
            document.close(False)
            return

        last_page = max(page for _, page in page_map)
        pages_to_split = min(pages_to_process, last_page)
        print(
            f"{len(page_map)} paragraphs across {last_page} page(s). "
            f"Splitting {pages_to_split}."
        )

        # Close the source before the loop -- save_single_page
        # reopens from the saved repaginated file instead.
        document.close(False)

        written = 0
        for page_number in range(1, pages_to_split + 1):
            output_path = OUTPUT_FOLDER / f"{OUTPUT_PREFIX}{page_number}.docx"
            if save_single_page(context, repaginated_path, page_map,
                                page_number, output_path):
                print(f"Saved {output_path}")
                written += 1
            else:
                print(f"Page {page_number} had no paragraphs. Skipped.")

        print(f"\nDone. Wrote {written} file(s) to {OUTPUT_FOLDER}/")

    finally:
        print("Closing LibreOffice...")
        lo_process.terminate()


if __name__ == "__main__":
    main()
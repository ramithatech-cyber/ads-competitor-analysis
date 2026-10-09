"""Render an HTML report to PDF with headless Chromium.

Runs as a subprocess (own event loop):  python -m core.pdf_export report.html report.pdf
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

FOOTER = ("<div style='width:100%;font-size:8px;color:#9C9A92;padding:0 10mm;display:flex;justify-content:space-between;"
          "font-family:Segoe UI,Arial,sans-serif'><span>Competitor Ad Intelligence Report</span>"
          "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")


def html_to_pdf(html_path: str, pdf_path: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # ~A4 printable width in CSS px, so the layout is measured at print size.
        page = browser.new_page(viewport={"width": 760, "height": 1100})
        page.goto(pathlib.Path(html_path).resolve().as_uri(), wait_until="load", timeout=90000)
        # Make sure every image (all embedded as data URLs) is decoded before printing.
        page.evaluate("""() => Promise.all([...document.images].map(i => i.complete ? 0 :
            new Promise(r => { i.onload = i.onerror = r })))""")
        page.emulate_media(media="print")
        page.pdf(path=pdf_path, format="A4", print_background=True, display_header_footer=True,
                 header_template="<div></div>", footer_template=FOOTER,
                 margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"})
        browser.close()


if __name__ == "__main__":
    html_to_pdf(sys.argv[1], sys.argv[2])

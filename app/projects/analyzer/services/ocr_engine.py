from typing import Union, Tuple, List, Dict, Any

def extract_text_from_pdf(pdf_source: Union[str, bytes]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts text and embedded hyperlink metadata from a PDF file path or raw in-memory bytes.
    Supports OCR fallback for scanned resumes.
    """
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed.") from exc

    text = ""
    links_data = []

    # Support both file path and in-memory bytes stream
    if isinstance(pdf_source, bytes):
        doc = fitz.open(stream=pdf_source, filetype="pdf")
    else:
        doc = fitz.open(pdf_source)

    with doc as document:
        for page in document:
            page_text = page.get_text()
            if not page_text.strip():
                try:
                    blocks = page.get_text("blocks")
                    block_texts = [
                        b[4] for b in blocks
                        if isinstance(b, (tuple, list)) and len(b) > 4 and isinstance(b[4], str)
                    ]
                    page_text = "\n".join(block_texts)
                except Exception:
                    pass
                if not page_text.strip():
                    try:
                        ocr_tp = page.get_textpage_ocr(language="eng")
                        page_text = ocr_tp.extractText()
                    except Exception:
                        pass
            text += (page_text or "") + "\n"
            links = page.get_links()
            for link in links:
                link_copy = link.copy()
                for key, value in link_copy.items():
                    if hasattr(value, "is_rect") or type(value).__name__ == "Rect":
                        link_copy[key] = list(value)
                if "uri" in link_copy:
                    links_data.append(link_copy)

    return text, links_data

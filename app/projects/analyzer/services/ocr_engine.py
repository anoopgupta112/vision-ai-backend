def extract_text_from_pdf(pdf_path: str):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed.") from exc

    text = ""
    links_data = []
    with fitz.open(pdf_path) as document:
        for page in document:
            text += page.get_text()
            links = page.get_links()
            for link in links:
                link_copy = link.copy()
                for key, value in link_copy.items():
                    if hasattr(value, "is_rect") or type(value).__name__ == "Rect":
                        link_copy[key] = list(value)
                if "uri" in link_copy:
                    links_data.append(link_copy)
    return text, links_data

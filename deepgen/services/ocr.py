from pathlib import Path


def run_ocr(file_path: Path, provider: str) -> str:
    provider = provider.lower()
    if provider != "tesseract":
        raise RuntimeError(
            f"OCR provider '{provider}' is not yet implemented in this scaffold. Use 'tesseract'."
        )
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("Install OCR extras first: pip install .[ocr]") from exc
    image = Image.open(file_path)
    return pytesseract.image_to_string(image)

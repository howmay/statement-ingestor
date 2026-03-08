import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """
    Extract text content from a PDF file.
    
    Uses pdfplumber as primary extractor, with PyPDF2 as fallback.
    MVP assumes text-based PDFs (not scanned images requiring OCR).
    
    Args:
        pdf_path: Path to the PDF file.
    
    Returns:
        Extracted text content, or None if extraction fails.
    
    Raises:
        FileNotFoundError: If PDF file does not exist.
        ValueError: If file is not a valid PDF.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Check file extension
    if not pdf_path.lower().endswith('.pdf'):
        logger.warning(f"File does not have .pdf extension: {pdf_path}")
    
    # Verify file size (empty files are invalid)
    file_size = os.path.getsize(pdf_path)
    if file_size == 0:
        raise ValueError(f"PDF file is empty: {pdf_path}")
    
    logger.info(f"Extracting text from: {pdf_path} ({file_size} bytes)")
    
    # Try pdfplumber first (better text extraction)
    try:
        import pdfplumber
        text = _extract_with_pdfplumber(pdf_path)
        if text and text.strip():
            logger.info(f"Successfully extracted {len(text)} characters using pdfplumber")
            return text
        else:
            logger.warning("pdfplumber returned empty text, trying PyPDF2 fallback")
    except ImportError:
        logger.warning("pdfplumber not available, trying PyPDF2 fallback")
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}, trying PyPDF2 fallback")
    
    # Fallback to PyPDF2
    try:
        import PyPDF2
        text = _extract_with_pypdf2(pdf_path)
        if text and text.strip():
            logger.info(f"Successfully extracted {len(text)} characters using PyPDF2")
            return text
        else:
            logger.warning("PyPDF2 also returned empty text")
    except ImportError:
        logger.error("Neither pdfplumber nor PyPDF2 is available")
        raise ImportError("PDF extraction requires either pdfplumber or PyPDF2. Install with: pip install pdfplumber PyPDF2")
    except Exception as e:
        logger.error(f"PyPDF2 extraction failed: {e}")
    
    # If we get here, extraction failed
    logger.warning(f"No text could be extracted from: {pdf_path}")
    logger.warning("This may be a scanned/image-based PDF (OCR not supported in MVP)")
    return None


def _extract_with_pdfplumber(pdf_path: str) -> str:
    """
    Extract text using pdfplumber library.
    
    Args:
        pdf_path: Path to the PDF file.
    
    Returns:
        Extracted text content.
    """
    import pdfplumber
    
    all_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        logger.debug(f"PDF has {len(pdf.pages)} page(s)")
        
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text()
                if text:
                    all_text.append(f"--- Page {i+1} ---\n{text}")
                    logger.debug(f"Page {i+1}: extracted {len(text)} characters")
            except Exception as e:
                logger.warning(f"Error extracting text from page {i+1}: {e}")
                continue
    
    return "\n\n".join(all_text)


def _extract_with_pypdf2(pdf_path: str) -> str:
    """
    Extract text using PyPDF2 library (fallback).
    
    Args:
        pdf_path: Path to the PDF file.
    
    Returns:
        Extracted text content.
    """
    import PyPDF2
    
    all_text = []
    
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            logger.debug(f"PDF has {len(reader.pages)} page(s)")
            
            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text()
                    if text:
                        all_text.append(f"--- Page {i+1} ---\n{text}")
                        logger.debug(f"Page {i+1}: extracted {len(text)} characters")
                except Exception as e:
                    logger.warning(f"Error extracting text from page {i+1}: {e}")
                    continue
    except Exception as e:
        raise ValueError(f"Failed to read PDF with PyPDF2: {e}")
    
    return "\n\n".join(all_text)


def is_text_based_pdf(pdf_path: str) -> bool:
    """
    Check if a PDF appears to be text-based (not scanned images).
    
    This is a heuristic check - extracts a small sample and checks
    if meaningful text is found.
    
    Args:
        pdf_path: Path to the PDF file.
    
    Returns:
        True if PDF appears to contain extractable text.
    """
    try:
        text = extract_text_from_pdf(pdf_path)
        if text is None:
            return False
        
        # Check if extracted text has meaningful content
        # (at least some alphanumeric characters)
        import re
        has_content = bool(re.search(r'[a-zA-Z0-9\u4e00-\u9fff]', text))
        
        if not has_content:
            logger.warning(f"PDF appears to be image-based (no extractable text): {pdf_path}")
        
        return has_content
        
    except Exception as e:
        logger.error(f"Error checking PDF: {e}")
        return False


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python src/pdf/pdf_to_text.py <pdf_file>")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    
    try:
        text = extract_text_from_pdf(pdf_file)
        if text:
            print(f"\n{'='*60}")
            print(f"Extracted text from: {pdf_file}")
            print(f"{'='*60}\n")
            # Show first 500 characters as preview
            preview = text[:500]
            print(preview)
            if len(text) > 500:
                print(f"\n... ({len(text) - 500} more characters)")
            print(f"\n{'='*60}")
            print(f"Total: {len(text)} characters")
            print(f"{'='*60}")
        else:
            print("No text could be extracted from this PDF.")
            print("It may be a scanned/image-based PDF (OCR not supported).")
            sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

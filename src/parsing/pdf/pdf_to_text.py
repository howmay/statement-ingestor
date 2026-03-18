import os
import logging
import re
import time
from typing import Optional, Dict, Any

from src.support.performance import profile, PerformanceMonitor
from src.parsing.pdf.pdf_cache import get_pdf_cache
from src.parsing.pdf.preload import preload_pdf_libraries, ensure_libraries_preloaded

logger = logging.getLogger(__name__)

# Preload libraries in background when module is imported
preload_pdf_libraries(background=True)


def select_pdf_library(pdf_path: str, password: str = None) -> str:
    """
    Always select pdfplumber as the primary library to prioritize extraction accuracy.
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Always returns 'pdfplumber'
    """
    return 'pdfplumber'


@profile
def extract_text_from_pdf(pdf_path: str, password: str = None) -> Optional[str]:
    """
    Extract text content from a PDF file using pdfplumber as the primary engine.
    Accuracy is prioritized over speed.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Check file extension
    if not pdf_path.lower().endswith('.pdf'):
        logger.warning(f"File does not have .pdf extension: {pdf_path}")
    
    # Verify file size
    file_size = os.path.getsize(pdf_path)
    if file_size == 0:
        raise ValueError(f"PDF file is empty: {pdf_path}")
    
    # Check cache first
    cache = get_pdf_cache()
    cached_text = cache.get(pdf_path, password)
    if cached_text is not None:
        logger.info(f"Cache hit for {pdf_path}, returning cached text ({len(cached_text)} chars)")
        return cached_text
    
    logger.info(f"Extracting text using pdfplumber (Accuracy Priority): {pdf_path}")
    
    # Primary: pdfplumber, Fallbacks only for extreme cases
    extraction_order = ['pdfplumber', 'pypdfium2', 'pdftotext', 'pypdf']
    
    last_exception = None
    for library in extraction_order:
        try:
            if library == 'pdfplumber':
                import pdfplumber
                text = _extract_with_pdfplumber(pdf_path, password)
            elif library == 'pypdfium2':
                text = _extract_with_pdfium(pdf_path, password)
            elif library == 'pdftotext':
                text = _extract_with_pdftotext(pdf_path, password)
            elif library == 'pypdf':
                text = _extract_with_pypdf(pdf_path, password)
            else:
                continue

            if text and text.strip():
                logger.info(f"Successfully extracted {len(text)} characters using {library}")
                cache.set(pdf_path, text, password)
                return text
        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()
            if 'password' in error_msg or 'encrypt' in error_msg:
                logger.debug(f"{library} extraction failed: {e}")
            else:
                logger.warning(f"{library} extraction failed: {e}")
            continue
            
    if last_exception:
        raise last_exception
        
    return None


def _extract_with_pdfium(pdf_path: str, password: str = None) -> str:
    """
    Extract text using pypdfium2 library (fastest option).
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Extracted text content.
    """
    import pypdfium2 as pdfium
    
    all_text = []
    
    try:
        # Load the PDF
        pdf = pdfium.PdfDocument(pdf_path, password=password)
        logger.debug(f"PDF has {len(pdf)} page(s)")
        
        for i in range(len(pdf)):
            page = None
            text_page = None
            try:
                page = pdf[i]

                # pypdfium2 API compatibility:
                # - newer: get_textpage()
                # - older: get_text_page()
                textpage_getter = getattr(page, 'get_textpage', None) or getattr(page, 'get_text_page', None)
                if textpage_getter is None:
                    raise AttributeError('PdfPage has no textpage getter')

                text_page = textpage_getter()
                text = text_page.get_text_range()

                if text and text.strip():
                    all_text.append(f"--- Page {i+1} ---\n{text}")
                    logger.debug(f"Page {i+1}: extracted {len(text)} characters")
            except Exception as e:
                logger.warning(f"Error extracting text from page {i+1}: {e}")
                continue
            finally:
                if text_page is not None:
                    try:
                        text_page.close()
                    except Exception:
                        pass
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
        
        pdf.close()
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise ValueError("PDF is encrypted and incorrect or missing password")
        else:
            raise ValueError(f"Failed to read PDF with pypdfium2: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error with pypdfium2: {e}")
    
    return "\n\n".join(all_text)


def _extract_with_pdftotext(pdf_path: str, password: str = None) -> str:
    """
    Extract text using pdftotext CLI tool (poppler-utils).
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Extracted text content.
    """
    import subprocess
    import shutil
    
    if not shutil.which('pdftotext'):
        return ""
        
    cmd = ['pdftotext', '-layout']
    if password:
        cmd.extend(['-opw', password, '-upw', password])
    cmd.extend([pdf_path, '-'])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        logger.debug(f"pdftotext execution failed: {e}")
        
    return ""


def _extract_with_pdfplumber(pdf_path: str, password: str = None) -> str:
    """
    Extract text using pdfplumber library.
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Extracted text content.
    """
    import pdfplumber
    
    all_text = []
    
    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
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
    except Exception as e:
        # Check if it's a password-related error
        error_str = str(e).lower()
        if "password" in error_str or "encrypted" in error_str:
            raise ValueError(f"Incorrect password or encrypted PDF: {e}")
        # Check for specific PDFPasswordIncorrect exception from pdfminer
        try:
            from pdfminer.pdfdocument import PDFPasswordIncorrect
            if isinstance(e, PDFPasswordIncorrect):
                raise ValueError("Incorrect password for encrypted PDF")
        except ImportError:
            pass
        # Re-raise other exceptions
        raise
    
    return "\n\n".join(all_text)


def _extract_with_pypdf(pdf_path: str, password: str = None) -> str:
    """
    Extract text using pypdf library (fallback).
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Extracted text content.
    """
    import pypdf
    
    all_text = []
    
    try:
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f, password=password)
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
    except pypdf.errors.FileNotDecryptedError:
        raise ValueError("PDF is encrypted and no password provided")
    except pypdf.errors.PdfReadError as e:
        if "incorrect password" in str(e).lower():
            raise ValueError("Incorrect password for encrypted PDF")
        else:
            raise ValueError(f"Failed to read PDF with pypdf: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read PDF with pypdf: {e}")
    
    return "\n\n".join(all_text)


def is_text_based_pdf(pdf_path: str, password: str = None) -> bool:
    """
    Check if a PDF appears to be text-based (not scanned images).
    
    This is a heuristic check - extracts a small sample and checks
    if meaningful text is found.
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        True if PDF appears to contain extractable text.
    """
    try:
        text = extract_text_from_pdf(pdf_path, password)
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


def main(argv=None) -> int:
    """CLI entrypoint for standalone PDF text extraction."""
    import sys

    args = argv if argv is not None else sys.argv[1:]

    logging.basicConfig(level=logging.INFO)

    if len(args) < 1:
        print("Usage: python src/pdf/pdf_to_text.py <pdf_file> [password]")
        print("")
        print("Examples:")
        print("  python src/pdf/pdf_to_text.py document.pdf")
        print("  python src/pdf/pdf_to_text.py encrypted.pdf mypassword")
        return 1

    pdf_file = args[0]
    password = args[1] if len(args) >= 2 else None

    try:
        text = extract_text_from_pdf(pdf_file, password)
        if text:
            print(f"\n{'='*60}")
            print(f"Extracted text from: {pdf_file}")
            if password:
                print(f"Using password: {'*' * len(password)}")
            print(f"{'='*60}\n")
            preview = text[:500]
            print(preview)
            if len(text) > 500:
                print(f"\n... ({len(text) - 500} more characters)")
            print(f"\n{'='*60}")
            print(f"Total: {len(text)} characters")
            print(f"{'='*60}")
            return 0

        print("No text could be extracted from this PDF.")
        if password:
            print("Possible reasons: incorrect password, or PDF is scanned/image-based.")
        else:
            print("Possible reasons: PDF is encrypted (needs password), or scanned/image-based.")
        return 1

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())

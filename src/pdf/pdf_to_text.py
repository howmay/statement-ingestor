import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str, password: str = None) -> Optional[str]:
    """
    Extract text content from a PDF file, optionally with password for encrypted PDFs.
    
    Uses pdfplumber as primary extractor, with PyPDF2 as fallback.
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
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
    
    if password:
        logger.info(f"Extracting text from encrypted PDF: {pdf_path} ({file_size} bytes)")
    else:
        logger.info(f"Extracting text from: {pdf_path} ({file_size} bytes)")
    
    # Try pypdfium2 first (fastest)
    try:
        import pypdfium2 as pdfium
        text = _extract_with_pdfium(pdf_path, password)
        if text and text.strip():
            logger.info(f"Successfully extracted {len(text)} characters using pypdfium2 (fast)")
            return text
        else:
            logger.warning("pypdfium2 returned empty text, trying next extractor")
    except ImportError:
        logger.debug("pypdfium2 not available, trying next extractor")
    except Exception as e:
        logger.warning(f"pypdfium2 extraction failed: {e}, trying next extractor")
    
    # Try pdfplumber second (better accuracy for complex layouts)
    try:
        import pdfplumber
        text = _extract_with_pdfplumber(pdf_path, password)
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
        text = _extract_with_pypdf2(pdf_path, password)
        if text and text.strip():
            logger.info(f"Successfully extracted {len(text)} characters using PyPDF2")
            return text
        else:
            logger.warning("PyPDF2 also returned empty text")
    except ImportError:
        logger.error("No PDF extraction library available (pypdfium2, pdfplumber, or PyPDF2)")
        raise ImportError("PDF extraction requires one of: pypdfium2, pdfplumber, or PyPDF2. Install with: pip install pypdfium2")
    except Exception as e:
        logger.error(f"PyPDF2 extraction failed: {e}")
    
    # If we get here, extraction failed
    if password:
        logger.warning(f"No text could be extracted from encrypted PDF: {pdf_path}")
        logger.warning("Password may be incorrect, or PDF may be scanned/image-based")
    else:
        logger.warning(f"No text could be extracted from: {pdf_path}")
        logger.warning("This may be an encrypted or scanned/image-based PDF")
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
            try:
                page = pdf[i]
                text = page.get_text_page().get_text_range()
                page.close()
                if text and text.strip():
                    all_text.append(f"--- Page {i+1} ---\n{text}")
                    logger.debug(f"Page {i+1}: extracted {len(text)} characters")
            except Exception as e:
                logger.warning(f"Error extracting text from page {i+1}: {e}")
                continue
        
        pdf.close()
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise ValueError("PDF is encrypted and incorrect or missing password")
        else:
            raise ValueError(f"Failed to read PDF with pypdfium2: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error with pypdfium2: {e}")
    
    return "\n\n".join(all_text)


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


def _extract_with_pypdf2(pdf_path: str, password: str = None) -> str:
    """
    Extract text using PyPDF2 library (fallback).
    
    Args:
        pdf_path: Path to the PDF file.
        password: Optional password for encrypted PDFs.
    
    Returns:
        Extracted text content.
    """
    import PyPDF2
    
    all_text = []
    
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f, password=password)
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
    except PyPDF2.errors.FileNotDecryptedError:
        raise ValueError("PDF is encrypted and no password provided")
    except PyPDF2.errors.PdfReadError as e:
        if "incorrect password" in str(e).lower():
            raise ValueError("Incorrect password for encrypted PDF")
        else:
            raise ValueError(f"Failed to read PDF with PyPDF2: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read PDF with PyPDF2: {e}")
    
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


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python src/pdf/pdf_to_text.py <pdf_file> [password]")
        print("")
        print("Examples:")
        print("  python src/pdf/pdf_to_text.py document.pdf")
        print("  python src/pdf/pdf_to_text.py encrypted.pdf mypassword")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) >= 3 else None
    
    try:
        text = extract_text_from_pdf(pdf_file, password)
        if text:
            print(f"\n{'='*60}")
            print(f"Extracted text from: {pdf_file}")
            if password:
                print(f"Using password: {'*' * len(password)}")
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
            if password:
                print("Possible reasons: incorrect password, or PDF is scanned/image-based.")
            else:
                print("Possible reasons: PDF is encrypted (needs password), or scanned/image-based.")
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

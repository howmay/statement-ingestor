import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
    
    logger.info(f"Extracting text using pdfplumber (Accuracy Priority): {pdf_path}")
    
    # pdfplumber first (accuracy), pypdfium2 as fallback.
    last_exception = None
    for library, extract in (('pdfplumber', _extract_with_pdfplumber), ('pypdfium2', _extract_with_pdfium)):
        try:
            text = extract(pdf_path, password)
            if text and text.strip():
                logger.info(f"Successfully extracted {len(text)} characters using {library}")
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

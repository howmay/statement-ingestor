"""
PDF library preloading for first-call performance optimization.
"""
import importlib
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class PDFLibraryPreloader:
    """
    Preload PDF libraries to reduce first-call latency.
    """
    
    def __init__(self):
        self.libraries = {
            'pypdfium2': 'pypdfium2',
            'pdfplumber': 'pdfplumber',
            'pypdf': 'pypdf'
        }
        self.preloaded = False
        self.preload_lock = threading.Lock()
        self.preload_thread: Optional[threading.Thread] = None
    
    def preload_libraries(self, background: bool = True):
        """
        Preload PDF libraries.
        
        Args:
            background: If True, preload in background thread.
        """
        with self.preload_lock:
            if self.preloaded:
                return
            
            if background:
                # Start background preloading
                self.preload_thread = threading.Thread(
                    target=self._preload_libraries_sync,
                    name="PDFLibraryPreloader",
                    daemon=True
                )
                self.preload_thread.start()
                logger.debug("Started background PDF library preloading")
            else:
                # Preload synchronously
                self._preload_libraries_sync()
    
    def _preload_libraries_sync(self):
        """
        Synchronously preload all PDF libraries.
        """
        logger.debug("Preloading PDF libraries...")
        
        for lib_name, module_name in self.libraries.items():
            try:
                start_time = importlib.import_module('time').perf_counter()
                module = importlib.import_module(module_name)
                end_time = importlib.import_module('time').perf_counter()
                
                logger.debug(f"Preloaded {lib_name} in {(end_time - start_time):.3f}s")
                
                # For pypdfium2, also preload some internal structures
                if lib_name == 'pypdfium2':
                    try:
                        # Try to create a dummy document to preload native libraries
                        import tempfile
                        import os
                        
                        # Create a minimal PDF for testing
                        dummy_pdf = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n92\n%%EOF'
                        
                        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                            f.write(dummy_pdf)
                            temp_path = f.name
                        
                        try:
                            # Try to load the dummy PDF
                            pdf = module.PdfDocument(temp_path)
                            pdf.close()
                        except Exception:
                            pass  # Ignore errors in preloading
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(temp_path)
                            except OSError:
                                pass
                    except Exception as e:
                        logger.debug(f"Could not preload pypdfium2 internals: {e}")
            
            except ImportError as e:
                logger.debug(f"Could not preload {lib_name}: {e}")
            except Exception as e:
                logger.debug(f"Error preloading {lib_name}: {e}")
        
        with self.preload_lock:
            self.preloaded = True
        
        logger.debug("PDF library preloading completed")
    
    def is_preloaded(self) -> bool:
        """
        Check if libraries have been preloaded.
        
        Returns:
            True if preloaded, False otherwise.
        """
        with self.preload_lock:
            return self.preloaded
    
    def wait_for_preload(self, timeout: float = 5.0) -> bool:
        """
        Wait for preloading to complete.
        
        Args:
            timeout: Maximum time to wait in seconds.
        
        Returns:
            True if preloaded, False if timeout.
        """
        if self.preload_thread is not None:
            self.preload_thread.join(timeout=timeout)
        
        return self.is_preloaded()


# Global preloader instance
_global_preloader: Optional[PDFLibraryPreloader] = None


def get_preloader() -> PDFLibraryPreloader:
    """
    Get global PDF library preloader.
    
    Returns:
        Global PDFLibraryPreloader instance.
    """
    global _global_preloader
    if _global_preloader is None:
        _global_preloader = PDFLibraryPreloader()
    return _global_preloader


def preload_pdf_libraries(background: bool = True):
    """
    Preload PDF libraries.
    
    Args:
        background: If True, preload in background thread.
    """
    preloader = get_preloader()
    preloader.preload_libraries(background)


def ensure_libraries_preloaded(timeout: float = 2.0) -> bool:
    """
    Ensure PDF libraries are preloaded, preloading if necessary.
    
    Args:
        timeout: Maximum time to wait for preloading.
    
    Returns:
        True if libraries are preloaded, False otherwise.
    """
    preloader = get_preloader()
    
    if not preloader.is_preloaded():
        # Preload synchronously with short timeout
        preloader.preload_libraries(background=False)
    
    return preloader.is_preloaded()
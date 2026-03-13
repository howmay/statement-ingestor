import pdfplumber
import os

class PDFExtractor:
    def __init__(self, filepath):
        self.filepath = filepath

    def extract_text(self):
        """
        Extracts all text from the given PDF file.
        Returns a single string containing text from all pages.
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"PDF file not found: {self.filepath}")

        extracted_text = []
        try:
            with pdfplumber.open(self.filepath) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        extracted_text.append(text)
            
            # Join all pages with a newline separator
            return "\n".join(extracted_text)
        except Exception as e:
            print(f"Error extracting text from {self.filepath}: {e}")
            return ""

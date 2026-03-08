import re

class BaseParser:
    def __init__(self, raw_text):
        self.raw_text = raw_text

    def parse(self):
        """Must return a dictionary with keys: date, amount, name, type, source"""
        return {
            "Date": self.extract_date(),
            "Amount": self.extract_amount(),
            "Expense Name / Item": self.extract_name(),
            "Type": self.extract_type(),
            "Source": self.get_source()
        }

    def extract_date(self):
        return "Unknown Date"

    def extract_amount(self):
        return "0.00"

    def extract_name(self):
        return "Unknown Expense"

    def extract_type(self):
        return "Misc"

    def get_source(self):
        return "Unknown Source"

class AppleParser(BaseParser):
    def extract_date(self):
        # Example: 'DATE 01 Jan 2024' or 'Billed On: ...'
        match = re.search(r'(?:Date|Billed On)[\s:]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "Unknown Date"

    def extract_amount(self):
        # Example: 'TOTAL $ 14.99' or 'Total: $14.99'
        match = re.search(r'Total(?:[\s:]*)(?:\$|USD)?\s*(\d+\.\d{2})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "0.00"

    def extract_name(self):
        return "Apple Services" # Default for MVP without complex line-item parsing

    def extract_type(self):
        return "Software/Subscription"

    def get_source(self):
        return "Apple"

class UberParser(BaseParser):
    def extract_date(self):
        match = re.search(r'(?:Date)[\s:]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "Unknown Date"

    def extract_amount(self):
        match = re.search(r'Total(?:[\s:]*)(?:\$|USD)?\s*(\d+\.\d{2})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "0.00"

    def extract_name(self):
        return "Uber Ride/Eats"

    def extract_type(self):
        return "Travel/Food"

    def get_source(self):
        return "Uber"

class AmazonParser(BaseParser):
    def extract_date(self):
        match = re.search(r'(?:Order Date|Date)[\s:]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "Unknown Date"

    def extract_amount(self):
        match = re.search(r'(?:Grand Total|Total)(?:[\s:]*)(?:\$|USD)?\s*(\d+\.\d{2})', self.raw_text, re.IGNORECASE)
        return match.group(1) if match else "0.00"

    def extract_name(self):
        return "Amazon Purchase"

    def extract_type(self):
        return "Shopping"

    def get_source(self):
        return "Amazon"

def get_parser(sender, raw_text):
    sender = sender.lower()
    if 'apple.com' in sender:
        return AppleParser(raw_text)
    elif 'uber.com' in sender:
        return UberParser(raw_text)
    elif 'amazon.com' in sender:
        return AmazonParser(raw_text)
    else:
        # Fallback to base parser
        return BaseParser(raw_text)

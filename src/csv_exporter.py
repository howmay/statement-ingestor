import pandas as pd
import os
from datetime import datetime

class CSVExporter:
    def __init__(self, data, output_dir):
        """
        data: list of dictionaries representing rows
        output_dir: directory to save the CSV
        """
        self.data = data
        self.output_dir = output_dir

    def export(self):
        if not self.data:
            print("No data to export.")
            return None
        
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"expenses_{timestamp}.csv")
        
        df = pd.DataFrame(self.data)
        # Reorder columns to match spec if needed
        columns_order = ["Date", "Amount", "Expense Name / Item", "Type", "Source"]
        # Filter only existing columns just in case
        columns_order = [col for col in columns_order if col in df.columns]
        
        # Append any extra fields
        for col in df.columns:
            if col not in columns_order:
                columns_order.append(col)
                
        df = df[columns_order]
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"Exported data to CSV: {filepath}")
        return filepath

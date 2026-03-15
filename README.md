# Gmail Expense Parser

Extract monthly bank statements and credit-card statements directly from your Gmail, parse the attachments (PDFs/CSVs), and export normalized, analysis-ready CSV files.

**Core Philosophy:**
- **Accuracy First:** Uses `pdfplumber` to accurately read complex PDF layouts. Uses mathematical "Running Balance" verification to distinguish between deposits and withdrawals, overcoming the column-flattening problem inherent in PDF text extraction.
- **Statement Focused:** Scans exclusively for official electronic bank statements and credit card bills, not random merchant receipts.
- **Privacy & Security:** Runs entirely locally. If a bank format is unrecognized, it can optionally fall back to a Local LLM (like Ollama) for parsing, keeping your financial data off the cloud.

---

## Supported Statements

We currently offer strict, deterministic, Regex-based parsers for the following banks:

| Country | Bank | Bank Account | Credit Card | CSV |
| --- | --- | :---: | :---: | :---: |
| Taiwan | 匯豐銀行 HSBC Taiwan | ✓ | ✓ |  |
| Singapore | 匯豐銀行 HSBC Singapore | ✓ | ✓ |  |
| Taiwan | 台北富邦銀行 Taipei Fubon Bank | ✓ | ✓ |  |
| Taiwan | 玉山銀行 E.SUN Bank | ✓ | ✓ |  |
| Singapore | 星展銀行 DBS Singapore | ✓ | ✓ |  |
| Taiwan | 台新銀行 Taishin Bank | ✓ | ✓ |  |
| Taiwan | 永豐銀行 Bank SinoPac |  | ✓ |  |
| Taiwan | 第一銀行 First Bank |  | ✓ |  |
| Lithuania / Global | Revolut |  |  | ✓ |

*Notes:*
- **Zero-Transaction Handling:** Smart enough to ignore "本期無消費資料" (No consumption data) without throwing errors.
- **Manually Forwarded Statements:** If you manually download a statement and forward it to yourself, the system scans the PDF content (e.g., "Account Summary", "DBS Bank") to automatically select the correct parser.
- **LLM Fallback:** If a format is not deterministically supported, it can fall back to an integrated LLM pipeline for extraction.

---

## How to Setup and Run (Step-by-Step Guide)

Follow these steps to get the code running on your local machine.

### Step 1: Environment Setup

Ensure you have **Python 3.13** installed.

1. **Clone the repository and enter the directory.**
2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   ```
4. **Setup Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and configure your settings. The most critical setting is `BANK_PASSWORDS`, which allows the script to decrypt your PDF statements automatically.
   ```env
   # Comma-separated list of passwords to try for encrypted PDFs
   BANK_PASSWORDS=A123456789,B987654321,0425
   
   # Optional: Configure LLM for fallback parsing
   LLM_PROVIDER=local
   LOCAL_BASE_URL=http://0.0.0.0:30000/v1
   LOCAL_MODEL=qwen3.5-9b
   ```

### Step 2: Apply for Gmail API (OAuth 2.0)

To allow the script to search and download your emails, you need a Google Cloud Project with the Gmail API enabled.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "Gmail Expense Parser").
3. Navigate to **APIs & Services > Library**, search for **"Gmail API"**, and click **Enable**.
4. Navigate to **APIs & Services > OAuth consent screen**:
   - Choose **External** (or Internal if using Google Workspace).
   - Fill in the required fields (App name, Support email).
   - Click **Save and Continue** until you reach "Test users".
   - **Add your own Gmail address** to the Test users list.
5. Navigate to **APIs & Services > Credentials**:
   - Click **Create Credentials > OAuth client ID**.
   - Application type: **Desktop application**.
   - Name it (e.g., "Python CLI").
   - Click **Create**.
6. **Download the JSON file**, rename it to **`client_secrets.json`**, and place it inside the `config/` directory of this project.

### Step 3: Run the Code (First Time Authorization)

Run the script for the first time. It will prompt you to log in via your browser.

```bash
python main.py
```

1. A browser window will open asking you to choose your Google account.
2. Because your app is in "Testing" mode, Google will show a warning: *"Google hasn't verified this app"*. Click **Advanced** -> **Go to [Your App Name] (unsafe)**.
3. Grant the script permission to read your emails.
4. The script will save a `config/token.json` file. You won't need to log in again unless the token expires or you delete it.

### Step 4: Normal Usage

Once authorized, you can run the script to process a specific date range:

```bash
python main.py --date-from 2026-02-01 --date-to 2026-02-28
```

**Debug Mode:** If you want to see detailed logs about PDF password attempts and extraction logic:
```bash
python main.py --debug
```

---

## Output Format

Once finished, the script generates a deduplicated CSV file in the `output/` directory, partitioned by month (e.g., `output/expenses_2026-02.csv`).

| date | income | expense | currency | expense_name | expense_type | source | source_file |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-02-02 | | 2000.00 | SGD | REFYIB1-55722 SGV... | Other | HSBC Singapore Bank | HSBC_SG_28FEB2026...pdf |
| 2026-02-05 | 7.04 | | SGD | EVERYDAY+BONUSINTEREST | Other | HSBC Singapore Bank | HSBC_SG_28FEB2026...pdf |
| 2026-02-26 | 11360.00 | | SGD | SGL26026M858RHLR SALA | Other | HSBC Singapore Bank | HSBC_SG_28FEB2026...pdf |

*Note: The script safely merges data across reruns. Existing files are appended and deduplicated.*

---

## FAQ / Troubleshooting

**Q: The script runs but says "Found 0 matching email(s)".**
- **A:** By default, the script searches for emails containing keywords like "statement", "對帳單", and specific bank domains. Check if your statements are archived, deleted, or missing attachments. You can test your search directly in Gmail using: `("statement" OR "對帳單") has:attachment filename:pdf`.

**Q: A PDF was downloaded, but it failed to extract text (Password Incorrect).**
- **A:** Ensure the correct password (usually ID number or birthdate) is listed in `BANK_PASSWORDS` in your `.env` file. The script will try every password in that list automatically.

**Q: The parser matched the bank, but extracted 0 transactions.**
- **A:** This can happen if the statement has no transactions for the month (e.g., "本期無消費"). The script handles this gracefully. If you *know* there are transactions, run `python main.py --debug` to see if the PDF text was extracted cleanly. Sometimes banks change their layouts, requiring an update to the Regex parser.

**Q: What happens if I manually download a statement and forward it to myself?**
- **A:** The system will download it. Since the sender is "you", it won't know which bank it is immediately. It will try *all* passwords in `BANK_PASSWORDS` to unlock it, then read the first few pages. If it finds keywords like "DBS Bank" or "HSBC Bank (Singapore)", it will automatically apply the correct parser.

**Q: I get a "RateLimitError" from OpenAI/LLM.**
- **A:** If a statement format isn't natively supported, the system splits the text into chunks and sends it to the LLM. If your PDF is massive (e.g., 30 pages), the concurrent requests might hit the API's rate limit. The script has built-in retries, but consider using a local LLM or adding a deterministic parser for that specific bank.

**Q: Port 8080 is already in use when I try to authenticate.**
- **A:** Open `.env` and add `OAUTH_PORT=8081`. **Important:** You must also add `http://localhost:8081/` to your *Authorized redirect URIs* in the Google Cloud Console.

## Development

Run all tests to ensure parsers are working correctly:
```bash
pytest
```

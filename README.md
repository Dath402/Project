# Document Extractor (Invoice / Purchase Order / Delivery Receipt)

A Streamlit app that reads a PDF or image and returns structured JSON:
document ID, vendor, date, currency, line items, subtotal, tax and total.

It uses simple rules, not AI. It works on many common layouts but **not all of
them**, so every extracted value should be reviewed by a person. Anything it
cannot find is `null`.

## Project layout

```
app.py                  Streamlit interface
src/pipeline.py         file -> text -> data (safety checks, PDF/OCR choice)
src/extract_fields.py   rules that find the fields and line items
src/ocr_reader.py       optional PaddleOCR wrapper
src/validation.py       arithmetic and structure checks (warnings only)
tests/                  automated tests (synthetic data only)
requirements.txt        core packages
requirements-ocr.txt    optional OCR packages
```

## Run on Replit

1. Create a new **Python** Repl and upload all files, keeping the `src`, `tests`
   and `.streamlit` folders. (Replit's file panel lets you upload a ZIP and
   unzip it with `unzip invoice_extractor.zip` in the Shell.)
2. In the **Shell** install the core packages:
   ```
   pip install -r requirements.txt
   ```
3. Start the app:
   ```
   streamlit run app.py
   ```
   The included `.replit` and `.streamlit/config.toml` already set the address
   (`0.0.0.0`), port (`8501`) and the 10 MB upload limit. Press **Run** to do the same.

## Test in two steps

**Step 1 – digital PDFs (no OCR needed).** Upload a PDF whose text you can
select. The text source should say `PyMuPDF (digital PDF)`.

**Step 2 – scans and photos (OCR).** Install the optional packages:
```
pip install -r requirements-ocr.txt
```
OCR is large (several hundred MB) and downloads models the first time it runs,
so the first image can take a minute. If Replit runs out of space or memory,
keep using digital PDFs. Without OCR the app shows a clear message instead of
crashing. OCR code targets PaddleOCR 3.x (`paddleocr>=3.0,<4`).

## Run the automated tests
```
pip install pytest
python -m pytest -q
```

## JSON format (same for every document type)
```json
{
  "document_type": "Invoice",
  "document_id": "INV-001",
  "vendor": "ABC Supplies",
  "document_date": "2026-10-20",
  "currency": "INR",
  "items": [{"name": "...", "quantity": "10", "unit_price": "500.00", "line_total": "5000.00"}],
  "subtotal": "5000.00",
  "tax": null,
  "total": "5000.00",
  "source_filename": "invoice.pdf"
}
```
Numbers are strings so no precision is lost; dates are `YYYY-MM-DD`.

## Known limits
- Only documents in English; one currency per document.
- Line items need four columns: description, quantity, unit price, line total.
  Rows with extra columns (for example a tax column) are reported, not guessed.
- Numeric dates such as `03/04/2026` are read as day/month and flagged.
- Number formats like `1.234,56` are left empty because they are ambiguous.
- Validation warnings are hints; discounts, shipping or rounding can be legitimate.
- Three-way matching is not part of this project stage.

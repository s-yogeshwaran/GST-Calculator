# GST Invoice Reverse Calculator

A production-ready Streamlit application for Glass Works that behaves like a GST invoice generator. Enter item-level net totals that already include GST, and the app reverse-calculates before-tax amount, unit rate, SGST, CGST, and invoice totals.

## Features

- Dynamic invoice rows with add and delete actions
- Invoice columns for Items, Pcs, Qty, Unit, Rate, Tax %, and Amount
- Internal item master with unit and GST percentage
- Reverse GST calculation from tax-inclusive totals
- Company header fields for name, address, phone number, and GSTIN
- Professional invoice-style output
- PDF export
- Excel export
- Print invoice action
- Session-state based row persistence
- Validation for PCS, quantity, and net total
- Amount chargeable in words

## Run Locally

Create and activate an isolated virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the application:

```powershell
streamlit run app.py
```

## Example

Input:

- Item: `4mm Plain`
- PCS: `2`
- Qty: `120`
- Net Total Including GST: `6945`

Expected output:

- Amount Before Tax: `₹5,885.59`
- SGST @ 9%: `₹529.70`
- CGST @ 9%: `₹529.70`
- NET TOTAL: `₹6,945.00`

## Formula

```python
before_tax = net_total / (1 + tax_percentage / 100)
rate = before_tax / qty
sgst = before_tax * 9 / 100
cgst = before_tax * 9 / 100
```

The validation uses unrounded values internally so the GST equation remains accurate even when displayed values are rounded to two decimals.

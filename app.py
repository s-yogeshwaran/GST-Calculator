"""GST Invoice Reverse Calculator.

A production-ready Streamlit app that turns GST-inclusive invoice totals into
before-tax invoice lines, SGST, CGST, and exportable invoice files.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


ITEMS = [
    {"item": "4mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "5mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "6mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "8mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "10mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "12mm Plain", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Rubik Blue", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Grille Grey", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Rubik Grey", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm D-Sq Grey", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Swastik Grey", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Grille White", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm DD White", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Rubik White", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm D-Sq White", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Swastik White", "unit": "Sqft", "tax": 18},
    {"item": "4mm Reeded White", "unit": "Sqft", "tax": 18},
    {"item": "3.5mm Pinhead White", "unit": "Sqft", "tax": 18},
    {"item": "4mm Pinhead White", "unit": "Sqft", "tax": 18},
    {"item": "5mm Pinhead White", "unit": "Sqft", "tax": 18},
    {"item": "Floor Spring", "unit": "Nos", "tax": 18},
    {"item": "Novapan Sheet", "unit": "Sqft", "tax": 18},
    {"item": "Labour Charges", "unit": "Job", "tax": 18},
    {"item": "4mm Mirror", "unit": "Sqft", "tax": 18},
    {"item": "5mm Mirror", "unit": "Sqft", "tax": 18},
    {"item": "6mm Mirror", "unit": "Sqft", "tax": 18},
    {"item": "8mm Mirror", "unit": "Sqft", "tax": 18},
]

ITEM_MASTER = {record["item"]: record for record in ITEMS}
ITEM_NAMES = list(ITEM_MASTER.keys())
RUPEE = "\u20b9"
TWO_PLACES = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    """Convert user-entered numeric values into Decimal safely."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def money(value: Decimal | float | int) -> Decimal:
    """Round an amount to two decimal places."""
    return to_decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_inr(value: Decimal | float | int) -> str:
    """Format a value as Indian Rupees with separators and two decimals."""
    return f"{RUPEE}{money(value):,.2f}"


def number_to_words_indian(number: int) -> str:
    """Convert an integer amount to Indian English words."""
    if number == 0:
        return "Zero"

    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def below_thousand(value: int) -> str:
        parts: list[str] = []
        if value >= 100:
            parts.append(f"{ones[value // 100]} Hundred")
            value %= 100
        if value >= 20:
            parts.append(tens[value // 10])
            value %= 10
        if value:
            parts.append(ones[value])
        return " ".join(parts)

    groups = [
        ("Crore", 10_000_000),
        ("Lakh", 100_000),
        ("Thousand", 1_000),
        ("", 1),
    ]
    words: list[str] = []
    for label, divisor in groups:
        if number >= divisor:
            chunk = number // divisor
            number %= divisor
            words.append(f"{below_thousand(chunk)} {label}".strip())
    return " ".join(words)


def amount_in_words(value: Decimal | float | int) -> str:
    """Return a rupee amount in words for the invoice footer."""
    rounded = money(value)
    rupees = int(rounded)
    paise = int((rounded - Decimal(rupees)) * 100)
    words = f"{number_to_words_indian(rupees)} Rupees"
    if paise:
        words += f" and {number_to_words_indian(paise)} Paise"
    return f"{words} Only"


def default_row(row_id: int) -> dict[str, object]:
    """Return a default editable invoice line."""
    return {
        "id": row_id,
        "item": ITEM_NAMES[0],
        "pcs": 1,
        "qty": 1.0,
        "net_total": 0.0,
    }


def initialize_state() -> None:
    """Set up all session state used by the invoice app."""
    st.session_state.setdefault("rows", [default_row(1)])
    st.session_state.setdefault("next_row_id", 2)
    st.session_state.setdefault("calculated", False)


def add_row() -> None:
    """Append an empty invoice line."""
    st.session_state.rows.append(default_row(st.session_state.next_row_id))
    st.session_state.next_row_id += 1
    st.session_state.calculated = False


def delete_row(row_id: int) -> None:
    """Delete an invoice line while keeping at least one editable row."""
    st.session_state.rows = [row for row in st.session_state.rows if row["id"] != row_id]
    if not st.session_state.rows:
        st.session_state.rows = [default_row(st.session_state.next_row_id)]
        st.session_state.next_row_id += 1
    st.session_state.calculated = False


def reset_invoice() -> None:
    """Reset the invoice to a clean starting state."""
    st.session_state.rows = [default_row(1)]
    st.session_state.next_row_id = 2
    st.session_state.calculated = False


def calculate_line(serial_number: int, row: dict[str, object]) -> dict[str, object]:
    """Calculate a single GST reverse invoice line."""
    item_data = ITEM_MASTER[str(row["item"])]
    qty = to_decimal(row["qty"])
    pcs = int(row["pcs"])
    net_total = to_decimal(row["net_total"])
    tax = Decimal(str(item_data["tax"]))
    divisor = Decimal("1") + (tax / Decimal("100"))

    before_tax_raw = net_total / divisor
    rate_raw = before_tax_raw / qty if qty > 0 else Decimal("0")
    gst_raw = net_total - before_tax_raw
    sgst_raw = before_tax_raw * Decimal("0.09")
    cgst_raw = before_tax_raw * Decimal("0.09")

    return {
        "S.No": serial_number,
        "Items": row["item"],
        "PCS": pcs,
        "Qty": qty,
        "Unit": item_data["unit"],
        "Rate": rate_raw,
        "Tax": f"{item_data['tax']}%",
        "Tax %": item_data["tax"],
        "Amount (Before Tax)": before_tax_raw,
        "SGST": sgst_raw,
        "CGST": cgst_raw,
        "GST": gst_raw,
        "Net Total": net_total,
    }


def validate_rows(rows: list[dict[str, object]]) -> list[str]:
    """Return validation errors for editable invoice rows."""
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        qty = to_decimal(row.get("qty"))
        pcs = to_decimal(row.get("pcs"))
        net_total = to_decimal(row.get("net_total"))
        if pcs <= 0:
            errors.append(f"Row {index}: PCS must be greater than zero.")
        if qty <= 0:
            errors.append(f"Row {index}: Qty must be greater than zero.")
        if net_total <= 0:
            errors.append(f"Row {index}: Net Total must be greater than zero.")
    return errors


def calculate_invoice(rows: list[dict[str, object]]) -> tuple[pd.DataFrame, dict[str, Decimal]]:
    """Calculate all invoice rows and summary totals."""
    calculated_rows = [calculate_line(index, row) for index, row in enumerate(rows, start=1)]
    df = pd.DataFrame(calculated_rows)

    summary = {
        "before_tax": sum(df["Amount (Before Tax)"], Decimal("0")),
        "sgst": sum(df["SGST"], Decimal("0")),
        "cgst": sum(df["CGST"], Decimal("0")),
        "net_total": sum(df["Net Total"], Decimal("0")),
    }
    return df, summary


def display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a user-facing invoice table with formatted display values."""
    display_df = df.copy()
    for column in ["Qty", "Rate", "Amount (Before Tax)"]:
        display_df[column] = display_df[column].map(lambda value: f"{money(value):,.2f}")
    display_df["Tax %"] = display_df["Tax %"].map(lambda value: f"{value}%")
    display_df = display_df.rename(columns={"PCS": "Pcs", "Amount (Before Tax)": "Amount"})
    return display_df[["S.No", "Items", "Pcs", "Qty", "Unit", "Rate", "Tax %", "Amount"]]


def export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return an export-friendly DataFrame with rounded numeric values."""
    export_df = df.copy()
    for column in ["Qty", "Rate", "Amount (Before Tax)", "SGST", "CGST", "GST", "Net Total"]:
        export_df[column] = export_df[column].map(lambda value: float(money(value)))
    export_df = export_df.rename(columns={"PCS": "Pcs", "Amount (Before Tax)": "Amount"})
    return export_df


def invoice_is_verified(summary: dict[str, Decimal]) -> bool:
    """Validate the unrounded GST equation before formatting for display."""
    calculated_total = summary["before_tax"] + summary["sgst"] + summary["cgst"]
    return abs(calculated_total - summary["net_total"]) <= Decimal("0.01")


def create_excel_file(
    df: pd.DataFrame,
    summary: dict[str, Decimal],
    company: dict[str, object],
) -> bytes:
    """Build an Excel invoice workbook in memory."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_dataframe(df).to_excel(writer, sheet_name="Invoice", index=False, startrow=6)
        ws = writer.sheets["Invoice"]
        ws["A1"] = company["Company Name"]
        ws["A2"] = company["Address"]
        ws["A3"] = company["Phone Number"]
        ws["A4"] = f"GSTIN: {company['GST Number']}"
        start = len(df) + 9
        ws[f"G{start}"] = "Total"
        ws[f"H{start}"] = float(money(summary["before_tax"]))
        ws[f"G{start + 1}"] = "SGST @ 9%"
        ws[f"H{start + 1}"] = float(money(summary["sgst"]))
        ws[f"G{start + 2}"] = "CGST @ 9%"
        ws[f"H{start + 2}"] = float(money(summary["cgst"]))
        ws[f"G{start + 3}"] = "NET TOTAL"
        ws[f"H{start + 3}"] = float(money(summary["net_total"]))
        ws[f"G{start + 5}"] = "Amount Chargeable (in words)"
        ws[f"H{start + 5}"] = amount_in_words(summary["net_total"])
    return output.getvalue()


def create_pdf_file(
    df: pd.DataFrame,
    summary: dict[str, Decimal],
    company: dict[str, object],
) -> bytes:
    """Build a strict black-and-white A4 GST invoice PDF in memory."""
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_width, page_height = A4
    margin = 12 * mm
    left = margin
    right = page_width - margin
    bottom = margin
    top = page_height - margin
    width = right - left
    height = top - bottom

    header_height = 45 * mm
    words_height = 32 * mm
    summary_height = 26 * mm
    header_bottom = top - header_height
    words_top = bottom + words_height
    summary_top = words_top + summary_height
    summary_left = left + (width * 0.55)
    item_top = header_bottom
    item_bottom = summary_top

    def draw_text(x: float, y: float, text: str, size: int = 10, bold: bool = False, align: str = "left") -> None:
        font = "Helvetica-Bold" if bold else "Helvetica"
        pdf.setFont(font, size)
        if align == "center":
            pdf.drawCentredString(x, y, text)
        elif align == "right":
            pdf.drawRightString(x, y, text)
        else:
            pdf.drawString(x, y, text)

    def amount_text(value: Decimal) -> str:
        return f"Rs. {money(value):,.2f}"

    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setLineWidth(2)
    pdf.rect(left, bottom, width, height, stroke=1, fill=0)

    pdf.setLineWidth(1)
    pdf.line(left, header_bottom, right, header_bottom)
    pdf.line(left, item_bottom, right, item_bottom)
    pdf.line(left, words_top, right, words_top)
    pdf.line(summary_left, item_bottom, summary_left, words_top)

    center_x = left + (width / 2)
    draw_text(center_x, top - 18 * mm, str(company["Company Name"]).upper(), 28, True, "center")
    draw_text(center_x, top - 28 * mm, str(company["Address"]), 10, True, "center")
    draw_text(center_x, top - 35 * mm, str(company["Phone Number"]), 10, True, "center")
    draw_text(center_x, top - 42 * mm, f"GSTIN: {company['GST Number']}", 10, True, "center")

    columns = [
        ("S.No", 0.07, "center"),
        ("Items", 0.34, "left"),
        ("Pcs", 0.10, "center"),
        ("Qty", 0.12, "right"),
        ("Unit", 0.10, "center"),
        ("Rate", 0.12, "right"),
        ("Tax %", 0.08, "center"),
        ("Amount", 0.17, "right"),
    ]
    scale = sum(col[1] for col in columns)
    col_widths = [width * (col[1] / scale) for col in columns]
    x_positions = [left]
    for col_width in col_widths:
        x_positions.append(x_positions[-1] + col_width)

    header_row_height = 40
    table_header_bottom = item_top - header_row_height
    pdf.setLineWidth(1)
    for x in x_positions:
        pdf.line(x, item_top, x, item_bottom)
    pdf.setLineWidth(2)
    pdf.line(left, table_header_bottom, right, table_header_bottom)
    pdf.setLineWidth(1)

    for idx, (label, _, align) in enumerate(columns):
        x1 = x_positions[idx]
        x2 = x_positions[idx + 1]
        x = (x1 + x2) / 2 if align == "center" else x1 + 4
        if align == "right":
            x = x2 - 4
        draw_text(x, item_top - 24, label, 10, True, align)

    data_rows = []
    for _, row in df.iterrows():
        data_rows.append(
            [
                str(row["S.No"]),
                str(row["Items"]),
                str(row["PCS"]),
                f"{money(row['Qty']):,.2f}",
                str(row["Unit"]),
                f"{money(row['Rate']):,.2f}",
                f"{row['Tax %']}%",
                f"{money(row['Amount (Before Tax)']):,.2f}",
            ]
        )
    minimum_rows = 15
    row_count = max(minimum_rows, len(data_rows))
    available_height = table_header_bottom - item_bottom
    row_height = min(38, available_height / row_count)

    y = table_header_bottom
    for row_index in range(row_count):
        y_next = y - row_height
        if row_index < len(data_rows):
            for col_index, value in enumerate(data_rows[row_index]):
                align = columns[col_index][2]
                x1 = x_positions[col_index]
                x2 = x_positions[col_index + 1]
                text_x = (x1 + x2) / 2 if align == "center" else x1 + 4
                if align == "right":
                    text_x = x2 - 4
                draw_text(text_x, y_next + (row_height / 2) - 4, value, 9, False, align)
        y = y_next
    pdf.line(left, item_bottom, right, item_bottom)

    summary_rows = [
        ("Description", "Amount", True),
        ("Total", amount_text(summary["before_tax"]), False),
        ("SGST @ 9%", amount_text(summary["sgst"]), False),
        ("CGST @ 9%", amount_text(summary["cgst"]), False),
        ("NET TOTAL", amount_text(summary["net_total"]), True),
    ]
    summary_col_split = summary_left + ((right - summary_left) * 0.58)
    row_h = summary_height / len(summary_rows)
    pdf.line(summary_col_split, item_bottom, summary_col_split, words_top)
    for index in range(len(summary_rows) + 1):
        y_line = item_bottom - (index * row_h)
        pdf.line(summary_left, y_line, right, y_line)
    for index, (description, amount, bold) in enumerate(summary_rows):
        text_y = item_bottom - ((index + 0.65) * row_h)
        draw_text(summary_left + 5, text_y, description, 9, bold)
        draw_text(right - 5, text_y, amount, 9, bold, "right")

    words_left = left + 8
    draw_text(words_left, words_top - 11 * mm, "Amount Chargeable (in words)", 14, True)
    draw_text(words_left, words_top - 21 * mm, f"Rupees: {amount_in_words(summary['net_total'])}", 11, False)

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def render_css() -> None:
    """Apply lightweight invoice styling."""
    st.markdown(
        """
        <style>
        .block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 1180px;}
        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 14px 16px;
        }
        .invoice-shell {
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 22px;
            background: #ffffff;
        }
        .invoice-title {
            text-align: center;
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: 0;
            border-top: 2px solid #0f172a;
            border-bottom: 2px solid #0f172a;
            padding: 12px 0;
            margin-bottom: 18px;
        }
        .muted {color: #64748b;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_company_details() -> dict[str, object]:
    """Render company and invoice detail inputs."""
    st.subheader("Company Details")
    col1, col2, col3 = st.columns(3)
    company_name = col1.text_input("Company Name", value="Glass Works GST Invoice")
    gst_number = col2.text_input("GSTIN", value="12ABCDE3456F7GH")
    phone = col3.text_input("Phone Number", value="0123456789")
    address = st.text_area(
        "Address",
        value="Salem, Tamil Nadu, India",
        height=70,
    )

    return {
        "Company Name": company_name,
        "GST Number": gst_number,
        "Address": address,
        "Phone Number": phone,
    }


def render_entry_rows() -> None:
    """Render editable invoice rows using session state."""
    st.subheader("Invoice Entry")
    st.caption("Enter the GST-inclusive net total for each item. Unit and tax are populated from item master data.")

    header = st.columns([0.55, 3.2, 0.8, 1, 1.7, 0.8])
    for label, column in zip(["S.No", "Items", "Pcs", "Qty", "Net Total", ""], header):
        column.markdown(f"**{label}**")

    for index, row in enumerate(st.session_state.rows, start=1):
        row_id = row["id"]
        cols = st.columns([0.55, 3.2, 0.8, 1, 1.7, 0.8])
        cols[0].write(index)
        row["item"] = cols[1].selectbox(
            "Items",
            ITEM_NAMES,
            index=ITEM_NAMES.index(str(row["item"])),
            key=f"item_{row_id}",
            label_visibility="collapsed",
        )
        row["pcs"] = cols[2].number_input(
            "PCS",
            min_value=1,
            step=1,
            value=int(row["pcs"]),
            key=f"pcs_{row_id}",
            label_visibility="collapsed",
        )
        row["qty"] = cols[3].number_input(
            "Qty",
            min_value=0.0,
            step=0.01,
            value=float(row["qty"]),
            format="%.2f",
            key=f"qty_{row_id}",
            label_visibility="collapsed",
        )
        row["net_total"] = cols[4].number_input(
            "Net Total",
            min_value=0.0,
            step=1.0,
            value=float(row["net_total"]),
            format="%.2f",
            key=f"net_total_{row_id}",
            label_visibility="collapsed",
        )
        if cols[5].button("Delete", key=f"delete_{row_id}", use_container_width=True):
            delete_row(int(row_id))
            st.rerun()

    action_cols = st.columns([1.2, 1.6, 1.6, 4])
    if action_cols[0].button("Add Item", use_container_width=True):
        add_row()
        st.rerun()
    if action_cols[1].button("Calculate Invoice", type="primary", use_container_width=True):
        errors = validate_rows(st.session_state.rows)
        if errors:
            st.session_state.calculated = False
            for error in errors:
                st.error(error)
        else:
            st.session_state.calculated = True
    if action_cols[2].button("Reset Invoice", use_container_width=True):
        reset_invoice()
        st.rerun()


def render_invoice(df: pd.DataFrame, summary: dict[str, Decimal], company: dict[str, object]) -> None:
    """Render the invoice output, summary, validation, and exports."""
    st.divider()
    st.markdown('<div class="invoice-shell">', unsafe_allow_html=True)
    st.markdown(f'<div class="invoice-title">{company["Company Name"]}</div>', unsafe_allow_html=True)

    st.markdown(f"**Address:** {company['Address']}")
    st.markdown(f"**Phone:** {company['Phone Number']}")
    st.markdown(f"**GSTIN:** {company['GST Number']}")

    st.subheader("Items")
    st.dataframe(display_dataframe(df), hide_index=True, use_container_width=True)

    st.subheader("Summary")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Total", format_inr(summary["before_tax"]))
    metric_cols[1].metric("SGST @ 9%", format_inr(summary["sgst"]))
    metric_cols[2].metric("CGST @ 9%", format_inr(summary["cgst"]))
    metric_cols[3].metric("NET TOTAL", format_inr(summary["net_total"]))

    st.subheader("Amount Chargeable (in words)")
    st.markdown(f"**Rupees:** {amount_in_words(summary['net_total'])}")

    if invoice_is_verified(summary):
        st.success("Invoice verified successfully.")
    else:
        st.warning("Calculation mismatch")

    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Reverse GST Formula", expanded=False):
        st.code(
            "before_tax = net_total / (1 + tax_percentage / 100)\n"
            "rate = before_tax / qty\n"
            "sgst = before_tax * 9 / 100\n"
            "cgst = before_tax * 9 / 100",
            language="python",
        )

    pdf_bytes = create_pdf_file(df, summary, company)
    excel_bytes = create_excel_file(df, summary, company)

    export_cols = st.columns([1.4, 1.4, 1.4, 4])
    export_cols[0].download_button(
        "Export PDF",
        data=pdf_bytes,
        file_name="kumar_glass_invoice.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Export Excel",
        data=excel_bytes,
        file_name="kumar_glass_invoice.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    if export_cols[2].button("Print Invoice", use_container_width=True):
        components.html("<script>window.parent.print();</script>", height=0)


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="GST Invoice Reverse Calculator", page_icon=RUPEE, layout="wide")
    initialize_state()
    render_css()

    st.title("GST Invoice Reverse Calculator")
    st.write(
        "Create a GST invoice from final item totals that already include tax. "
        "The app reverse-calculates before-tax amount, rate, SGST, CGST, and invoice totals."
    )

    company = render_company_details()
    st.divider()
    render_entry_rows()

    if st.session_state.calculated:
        try:
            invoice_df, summary = calculate_invoice(st.session_state.rows)
            render_invoice(invoice_df, summary, company)
        except Exception as exc:  # pragma: no cover - Streamlit-facing safeguard.
            st.error(f"Unable to calculate invoice: {exc}")


if __name__ == "__main__":
    main()

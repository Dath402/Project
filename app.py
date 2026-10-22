import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.ocr_reader import is_ocr_available
from src.pipeline import MAX_FILE_BYTES, process_document
from src.validation import validate_structure

st.set_page_config(page_title="Invoice Document Extractor", page_icon="📄", layout="wide")

st.markdown(
    """
    <style>
    :root { --accent: #6366f1; --accent-2: #06b6d4; }
    .block-container { padding-top: 2.2rem; max-width: 1100px; }
    .hero h1 {
        font-size: 2.1rem; font-weight: 800; margin: 0 0 .25rem 0;
        background: linear-gradient(90deg, var(--accent), var(--accent-2));
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .hero p { opacity: .75; margin: 0 0 1.2rem 0; }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.25); border-radius: 12px;
        padding: .8rem 1rem; background: rgba(99,102,241,.05);
    }
    .field-card {
        border: 1px solid rgba(128,128,128,.25); border-radius: 12px;
        padding: .7rem 1rem; margin-bottom: .6rem; border-left: 4px solid var(--accent);
    }
    .field-card .lbl { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; opacity: .6; }
    .field-card .val { font-size: 1.05rem; font-weight: 600; word-break: break-word; }
    .totals { border-radius: 12px; padding: .8rem 1rem; background: rgba(6,182,212,.07);
              border: 1px solid rgba(6,182,212,.3); margin-top: .8rem; }
    .totals div { display: flex; justify-content: space-between; padding: .15rem 0; }
    .totals .grand { border-top: 1px solid rgba(128,128,128,.3); margin-top: .35rem;
                     padding-top: .45rem; font-weight: 800; font-size: 1.1rem; }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, var(--accent), var(--accent-2)); border: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><h1>📄 Document Extractor</h1>'
    "<p>Upload a Purchase Order, Invoice, or Delivery Receipt. Get structured data back.</p></div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("How it works")
    st.markdown(
        "1. Read digital PDF text with **PyMuPDF**.\n"
        "2. If the PDF has no usable text, or the file is an image, use **PaddleOCR** (optional).\n"
        "3. Extract fields using rules and table-row patterns.\n"
        "4. Check the numbers and show warnings.\n"
        "5. Review, edit and export JSON."
    )
    if is_ocr_available():
        st.success("OCR is installed.")
    else:
        st.info("OCR is not installed. Digital PDFs work; images and scans need `requirements-ocr.txt`.")
    st.caption("Rule-based extraction is a prototype. Always review extracted values.")

DOC_TYPES = ["Invoice", "Purchase Order", "Delivery Receipt / GRN"]
doc_type = st.radio("Document type", DOC_TYPES, horizontal=True)
uploaded = st.file_uploader(
    f"Upload PDF, PNG, JPG or JPEG (max {MAX_FILE_BYTES // (1024 * 1024)} MB)",
    type=["pdf", "png", "jpg", "jpeg"],
)

if uploaded:
    raw = uploaded.getvalue()
    st.caption(f"📎 {uploaded.name} · {len(raw):,} bytes")
    if st.button("Extract information", type="primary"):
        with st.spinner("Reading document and extracting fields..."):
            try:
                st.session_state["result"] = process_document(raw, uploaded.name, doc_type)
            except Exception as e:  # last safety net; process_document normally never raises
                st.session_state.pop("result", None)
                st.error(f"Could not process this file: {e}")


def esc(value) -> str:
    """Escape untrusted text before it goes into HTML."""
    return html.escape("" if value is None else str(value))


def field_card(label: str, value) -> str:
    shown = esc(value) if value not in (None, "") else "—"
    return f'<div class="field-card"><div class="lbl">{esc(label)}</div><div class="val">{shown}</div></div>'


def money(currency, value) -> str:
    return esc(f"{currency or ''} {value}".strip()) if value is not None else "—"


if "result" in st.session_state:
    result = st.session_state["result"]
    data = result["data"]

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Document type", data.get("document_type") or "—")
    c2.metric("Text source", result["text_source"])
    c3.metric("Characters extracted", f'{len(result["raw_text"]):,}')

    st.caption("Extracted values may contain mistakes. Please review them before relying on them.")
    if result["warnings"]:
        with st.expander(f"Review notes ({len(result['warnings'])})", expanded=True):
            for warning in result["warnings"]:
                st.warning(warning)

    tab_doc, tab_json, tab_raw = st.tabs(["Document view", "Edit JSON", "Raw text"])

    with tab_doc:
        a, b, c = st.columns(3)
        a.markdown(field_card("Document ID", data.get("document_id")), unsafe_allow_html=True)
        b.markdown(field_card("Vendor", data.get("vendor")), unsafe_allow_html=True)
        c.markdown(field_card("Date", data.get("document_date")), unsafe_allow_html=True)

        items = data.get("items") or []
        if items:
            df = pd.DataFrame(items)
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.info("No line items detected.")

        cur = data.get("currency")
        st.markdown(
            f'<div class="totals">'
            f'<div><span>Subtotal</span><span>{money(cur, data.get("subtotal"))}</span></div>'
            f'<div><span>Tax</span><span>{money(cur, data.get("tax"))}</span></div>'
            f'<div class="grand"><span>Total</span><span>{money(cur, data.get("total"))}</span></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    with tab_json:
        edited = st.text_area(
            "Correct any extraction errors here",
            value=json.dumps(data, indent=2, ensure_ascii=False),
            height=360,
        )
        try:
            parsed = json.loads(edited)
            for problem in validate_structure(parsed):
                st.warning(problem)
            st.download_button(
                "Download structured JSON",
                data=json.dumps(parsed, indent=2, ensure_ascii=False),
                file_name=f'{Path(result["filename"]).stem}_extracted.json',
                mime="application/json",
            )
        except json.JSONDecodeError as e:
            st.error(f"JSON is not valid yet: {e}")

    with tab_raw:
        st.text(result["raw_text"] or "(No text could be extracted.)")

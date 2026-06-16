import streamlit as st
import pandas as pd
import tempfile
import os
import requests
from io import StringIO

API_URL = "https://extraction-api.nanonets.com/api/v1/extract/sync"

st.title("Image to CSV Table Extractor")

API_KEY = st.text_input("Enter your Docstrange API Key", type="password")
if not API_KEY:
    st.stop()

uploaded_files = st.file_uploader(
    "Upload images or PDFs",
    type=['png', 'jpg', 'jpeg', 'pdf'],
    accept_multiple_files=True
)

def parse_html_tables(html_content):
    """Parse HTML tables into DataFrames"""
    try:
        dfs = pd.read_html(StringIO(html_content))
        cleaned = []
        for df in dfs:
            # Drop fully empty rows and columns
            df.dropna(how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            df.reset_index(drop=True, inplace=True)
            if not df.empty:
                cleaned.append(df)
        return cleaned
    except Exception as e:
        st.error(f"HTML parse error: {e}")
        return []

if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        st.subheader(f"📄 {uploaded_file.name}")
        ext = uploaded_file.name.split('.')[-1].lower()

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner(f"Extracting from {uploaded_file.name}..."):
                with open(tmp_path, "rb") as f:
                    response = requests.post(
                        API_URL,
                        headers={"Authorization": f"Bearer {API_KEY}"},
                        files={"file": (uploaded_file.name, f)},
                        data={"output_format": "html"}
                    )

            if response.status_code != 200:
                st.error(f"API Error {response.status_code}: {response.text}")
                continue

            result = response.json()

            # Extract HTML content from response
            html_content = (
                result.get("result", {}).get("html", {}).get("content") or
                result.get("html", {}).get("content") or
                result.get("content") or ""
            )

            if not html_content:
                st.warning(f"No content extracted from {uploaded_file.name}")
                st.json(result)
                continue

            dfs = parse_html_tables(html_content)

            if not dfs:
                st.warning(f"No tables found in {uploaded_file.name}")
                continue

            for idx, df in enumerate(dfs):
                # Use first row as header if it looks like one
                if df.iloc[0].astype(str).str.isupper().sum() > len(df.columns) // 2:
                    df.columns = df.iloc[0]
                    df = df[1:].reset_index(drop=True)

                st.write(f"Table {idx + 1} — {len(df)} rows")
                st.dataframe(df)
                all_dfs.append(df)

                st.download_button(
                    label=f"⬇ Download Table {idx + 1}",
                    data=df.to_csv(index=False),
                    file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_table{idx + 1}.csv",
                    mime="text/csv",
                    key=f"dl_{uploaded_file.name}_{idx}"
                )

        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    if len(all_dfs) > 1:
        st.subheader("📦 Combined CSV")
        combined = pd.concat(all_dfs, ignore_index=True)
        st.dataframe(combined)
        st.download_button(
            label="⬇ Download Combined CSV",
            data=combined.to_csv(index=False),
            file_name="combined_output.csv",
            mime="text/csv",
            key="dl_combined"
        )

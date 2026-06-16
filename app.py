import os
import tempfile
from io import BytesIO, StringIO

import pandas as pd
import requests
import streamlit as st

API_URL = "https://extraction-api.nanonets.com/api/v1/extract/sync"

st.title("Image to Excel Table Extractor")

API_KEY = st.text_input("Enter your Docstrange API Key", type="password")
if not API_KEY:
    st.stop()

uploaded_files = st.file_uploader(
    "Upload images or PDFs",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
)


def parse_html_tables(html_content):
    """Parse HTML tables into DataFrames."""
    try:
        dfs = pd.read_html(StringIO(html_content))
        cleaned = []
        for df in dfs:
            df.dropna(how="all", inplace=True)
            df.dropna(axis=1, how="all", inplace=True)
            df.reset_index(drop=True, inplace=True)
            if not df.empty:
                cleaned.append(df)
        return cleaned
    except Exception as e:
        st.error(f"HTML parse error: {e}")
        return []


def make_unique_columns(columns, reserved=()):
    seen = {}
    unique_columns = []
    reserved_names = set(reserved)

    for position, column in enumerate(columns, start=1):
        if pd.isna(column):
            base_name = f"column_{position}"
        else:
            base_name = str(column).strip()
            if not base_name or base_name.lower().startswith("unnamed:"):
                base_name = f"column_{position}"

        if base_name in reserved_names:
            base_name = f"{base_name}_extracted"

        count = seen.get(base_name, 0) + 1
        seen[base_name] = count
        unique_columns.append(base_name if count == 1 else f"{base_name}_{count}")

    return unique_columns


def prepare_extracted_table(df, source_file, source_table):
    df = df.copy()

    if df.iloc[0].astype(str).str.isupper().sum() > len(df.columns) // 2:
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)

    df.columns = make_unique_columns(
        df.columns,
        reserved=("source_file", "source_table"),
    )
    df.insert(0, "source_file", source_file)
    df.insert(1, "source_table", source_table)
    return df


def dataframe_to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Extracted Tables")
    return output.getvalue()


if uploaded_files:
    all_dfs = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for file_number, uploaded_file in enumerate(uploaded_files, start=1):
        status_text.write(
            f"Processing {file_number} of {len(uploaded_files)}: {uploaded_file.name}"
        )
        st.subheader(f"File: {uploaded_file.name}")
        ext = uploaded_file.name.split(".")[-1].lower()

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
                        data={"output_format": "html"},
                    )

            if response.status_code != 200:
                st.error(f"API Error {response.status_code}: {response.text}")
                continue

            result = response.json()

            html_content = (
                result.get("result", {}).get("html", {}).get("content")
                or result.get("html", {}).get("content")
                or result.get("content")
                or ""
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
                table_source = uploaded_file.name.rsplit(".", 1)[0]
                df = prepare_extracted_table(df, uploaded_file.name, idx + 1)

                st.write(f"Table {idx + 1} - {len(df)} rows")
                st.dataframe(df)
                all_dfs.append(df)

                st.download_button(
                    label=f"Download Table {idx + 1} CSV",
                    data=df.to_csv(index=False),
                    file_name=f"{table_source}_table{idx + 1}.csv",
                    mime="text/csv",
                    key=f"dl_{uploaded_file.name}_{idx}",
                )

        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            progress_bar.progress(file_number / len(uploaded_files))

    status_text.write(f"Finished processing {len(uploaded_files)} file(s).")

    if all_dfs:
        st.subheader("Combined Excel")
        combined = pd.concat(all_dfs, ignore_index=True)
        st.dataframe(combined)
        st.download_button(
            label="Download Combined Excel",
            data=dataframe_to_excel_bytes(combined),
            file_name="combined_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_combined_excel",
        )

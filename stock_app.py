import streamlit as st
import datetime
import os
import json
import urllib.parse
import urllib.request
from typing import List, Dict, Union
from dotenv import load_dotenv
import zipfile
import io
import pandas as pd
import chardet
import re

# --- ユーティリティ ---
def sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-_\. ]', '_', name)

# --- 環境変数ロード ---
load_dotenv()
EDINET_API_KEY = os.environ.get('EDINET_API_KEY')

if not EDINET_API_KEY:
    st.error("`.env` に `EDINET_API_KEY` が設定されていません。")
    st.stop()

# --- EDINET API 基本関数 ---
def disclosure_documents(date: Union[str, datetime.date], type: int = 2) -> Dict:
    if isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    elif isinstance(date, str):
        date_str = date
    else:
        raise TypeError("Date must be string (YYYY-MM-DD) or datetime.date")

    url = "https://disclosure.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "date": date_str,
        "type": type,
        "Subscription-Key": EDINET_API_KEY
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    with urllib.request.urlopen(full_url) as response:
        return json.loads(response.read().decode('utf-8'))

def get_document(doc_id: str) -> bytes:
    url = f'https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}'
    params = {
        "type": 5,
        "Subscription-Key": EDINET_API_KEY
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f'{url}?{query_string}'
    with urllib.request.urlopen(full_url) as response:
        return response.read()

def extract_financial_metrics(zip_data: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)['encoding']
                    df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                    if not set(["項目ID", "金額"]).issubset(df.columns):
                        continue
                    metrics = {
                        "NetSales": "売上高",
                        "OperatingIncome": "営業利益",
                        "OrdinaryIncome": "経常利益",
                        "NetIncome": "当期純利益"
                    }
                    extracted = []
                    for key, label in metrics.items():
                        match = df[df["項目ID"].astype(str).str.contains(key, na=False)]
                        if not match.empty:
                            val = match.iloc[0]["金額"]
                            extracted.append({"指標": label, "金額": val})
                    return pd.DataFrame(extracted)
    return pd.DataFrame()

# --- UI構成 ---
st.title("EDINET 開示書類 検索＆財務指標の可視化")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("開始日", datetime.date.today() - datetime.timedelta(days=7))
with col2:
    end_date = st.date_input("終了日", datetime.date.today())

edinet_codes_input = st.text_input("EDINETコード（カンマ区切りで複数指定可、例：E03614,E03615）")
doc_type_codes_input = st.text_input("書類種別コード（例：120,130）")

if st.button("🔍 検索実行"):
    if start_date > end_date:
        st.error("開始日は終了日より前にしてください")
        st.stop()

    codes = [c.strip() for c in edinet_codes_input.split(",") if c.strip()]
    doc_types = [d.strip() for d in doc_type_codes_input.split(",") if d.strip()]
    results = []

    with st.spinner("EDINETからデータ取得中..."):
        current_date = start_date
        while current_date <= end_date:
            try:
                docs_res = disclosure_documents(date=current_date)
                for doc in docs_res.get("results", []):
                    if (not codes or doc['edinetCode'] in codes) and (not doc_types or doc['docTypeCode'] in doc_types):
                        results.append(doc)
            except Exception as e:
                st.warning(f"{current_date} のデータ取得に失敗しました: {e}")
            current_date += datetime.timedelta(days=1)

    if not results:
        st.warning("該当する書類は見つかりませんでした。")
    else:
        st.success(f"{len(results)} 件の書類が見つかりました。")
        df_results = []
        for r in results:
            df_results.append({
                "docID": r.get("docID"),
                "企業名": r.get("filerName"),
                "EDINETコード": r.get("edinetCode"),
                "書類種別": r.get("docTypeCode"),
                "提出日": r.get("submitDateTime"),
                "説明": r.get("docDescription")
            })
        st.dataframe(df_results)

        for doc in results:
            doc_id = doc['docID']
            filer = doc.get("filerName", "Unknown")
            file_name = sanitize_filename(f"{doc_id}_{filer}.zip")
            zip_data = get_document(doc_id)

            st.download_button(
                label=f"⬇ {filer} のCSV ZIPをダウンロード",
                data=zip_data,
                file_name=file_name,
                mime="application/zip"
            )

            # 財務指標の抽出と表示
            st.subheader(f"📊 財務指標（{filer}）")
            df_metrics = extract_financial_metrics(zip_data)
            if df_metrics.empty:
                st.info("財務指標を抽出できませんでした。")
            else:
                st.table(df_metrics)

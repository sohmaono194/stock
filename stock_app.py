import streamlit as st
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta

API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📊 企業名からEDINET財務データを自動取得・可視化")

# ============================
# 🔍 指定日の提出書類から企業名で検索
# ============================
def search_docid_by_company_name(company_name, days_back=90):
    date = datetime.today()
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    for _ in range(days_back):
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {"date": date.strftime('%Y-%m-%d'), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            for doc in res.json().get("results", []):
                name = doc.get("filerName", "")
                if company_name in name and doc.get("csvFlag") == "1":
                    return doc.get("docID"), name, doc.get("docDescription")
        except:
            continue
    return None, None, None

# ============================
# 📥 docID → CSV取得
# ============================
def fetch_csv_from_docid(doc_id):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 5}
    res = requests.get(url, headers=headers, params=params, timeout=20)
    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("このdocIDにはCSVが存在しません")
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)["encoding"]
                    return pd.read_csv(io.BytesIO(raw), encoding=encoding), file_name
    raise FileNotFoundError("CSVファイルがZIPに見つかりません")

# ============================
# 📊 財務指標抽出（例: 売上、営業利益）
# ============================
def extract_financial_metrics(df):
    keywords = ["NetSales", "OperatingIncome", "OrdinaryIncome", "NetIncome"]
    extracted = {}
    for kw in keywords:
        candidates = df[df["項目ID"].str.contains(kw, na=False)]
        if not candidates.empty:
            val = candidates.iloc[0].get("金額", "")
            extracted[kw] = val
    return extracted

# ============================
# Streamlit UI
# ============================
st.header("🔍 企業名からdocIDを自動検索 & 財務データ表示")
company = st.text_input("企業名を入力（例: トヨタ自動車）")

if st.button("検索して財務データ表示"):
    if not company:
        st.warning("企業名を入力してください")
    else:
        with st.spinner("EDINETでdocID検索中..."):
            doc_id, name, desc = search_docid_by_company_name(company)
            if not doc_id:
                st.error("該当する企業のCSV対応docIDが見つかりませんでした")
            else:
                st.success(f"✅ 見つかりました：{name}｜{desc}｜docID: {doc_id}")
                try:
                    df, fname = fetch_csv_from_docid(doc_id)
                    st.write(f"📁 ファイル名: {fname}")
                    st.dataframe(df.head(30))
                    metrics = extract_financial_metrics(df)
                    st.subheader("📈 抽出された財務指標")
                    for k, v in metrics.items():
                        st.write(f"{k}: {v}")
                except Exception as e:
                    st.error(f"CSV取得・解析でエラーが発生しました: {e}")

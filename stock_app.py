import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta

# 環境変数からAPIキーを取得（Streamlit Cloudなどを想定）
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📊 企業名からEDINET財務データを自動取得・可視化")

# ----------------------------
# 🔍 書類一覧APIからCSV対応docIDを企業名で検索
# ----------------------------
def search_docid_by_company_name(company_name, days_back=90):
    date = datetime.today()
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    for _ in range(days_back):
        date -= timedelta(days=1)
        if date.weekday() >= 5:  # 土日スキップ
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {"date": date.strftime('%Y-%m-%d'), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for doc in res.json().get("results", []):
                name = doc.get("filerName", "")
                if company_name in name and doc.get("csvFlag") == "1":
                    return doc.get("docID"), name, doc.get("docDescription")
        except Exception:
            continue
    return None, None, None

# ----------------------------
# 📥 docIDからCSVを取得
# ----------------------------
def fetch_csv_from_docid(doc_id):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 1}  # ZIPで取得
    res = requests.get(url, headers=headers, params=params, timeout=20)
    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("このdocIDにはZIPファイルが存在しません")
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)["encoding"]
                    return pd.read_csv(io.BytesIO(raw), encoding=encoding), file_name
    raise FileNotFoundError("CSVファイルがZIP内に見つかりませんでした")

# ----------------------------
# 📊 財務指標を抽出
# ----------------------------
def extract_financial_metrics(df):
    keywords = ["NetSales", "OperatingIncome", "OrdinaryIncome", "NetIncome"]
    extracted = {}
    for kw in keywords:
        matches = df[df["項目ID"].astype(str).str.contains(kw, na=False)]
        if not matches.empty:
            val = matches.iloc[0].get("金額", "")
            extracted[kw] = val
    return extracted

# ----------------------------
# Streamlit UI
# ----------------------------
st.header("🔍 企業名からdocIDを検索し財務CSVを可視化")
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
                    st.error(f"CSV取得・解析中にエラーが発生しました: {e}")

import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env から環境変数読み込み
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📊 企業名からEDINET四半期財務データを自動取得・可視化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` ファイルまたは環境変数 'EDINET_API_KEY' を確認してください。")
    st.stop()

# ----------------------------
# 🔍 四半期報告書のみ対象にdocID検索
# ----------------------------
def search_quarterly_docid(company_name, days_back=180):
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
            res.raise_for_status()
            for doc in res.json().get("results", []):
                name = doc.get("filerName", "")
                desc = doc.get("docDescription", "")
                doc_type = doc.get("docTypeCode", "")
                # ✅ 四半期報告書（docTypeCode = "140"）のみ対象
                if company_name in name and doc_type == "140":
                    return doc.get("docID"), name, desc
        except Exception:
            continue
    return None, None, None

# ----------------------------
# docIDからCSVを取得
# ----------------------------
def fetch_csv_from_docid(doc_id):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 5}
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
# 財務指標抽出
# ----------------------------
def extract_financial_metrics(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {"エラー": "CSVフォーマットが不明です（必要な列が存在しません）"}
    
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
st.header("🔍 四半期報告書を検索し財務データを表示")
company = st.text_input("企業名を入力（例: トヨタ自動車株式会社）")

if st.button("検索して表示"):
    if not company:
        st.warning("企業名を入力してください")
    else:
        with st.spinner("四半期報告書のdocIDを検索中..."):
            doc_id, name, desc = search_quarterly_docid(company)
            if not doc_id:
                st.error("四半期報告書が見つかりません（またはCSV未対応）")
            else:
                st.success(f"✅ 見つかりました：{name}｜{desc}｜docID: {doc_id}")
                try:
                    df, fname = fetch_csv_from_docid(doc_id)
                    st.write(f"📂 ファイル名: {fname}")
                    st.dataframe(df.head(30))

                    metrics = extract_financial_metrics(df)
                    if "エラー" in metrics:
                        st.error(metrics["エラー"])
                    else:
                        st.subheader("📈 財務指標（四半期）")
                        result_df = pd.DataFrame([{"指標": k, "金額": v} for k, v in metrics.items()])
                        st.table(result_df)
                except Exception as e:
                    st.error(f"CSV取得・解析中にエラーが発生しました: {e}")

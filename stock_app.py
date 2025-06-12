import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# .env からAPIキー取得
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("企業名からEDINET財務データを自動取得・可視化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` ファイルまたは環境変数 'EDINET_API_KEY' を確認してください。")
    st.stop()

# ----------------------------
# docIDを企業名で検索（csvFlag=1優先）
# ----------------------------
def search_docid_by_company_name(company_name, days_back=180):
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
                csv_flag = doc.get("csvFlag", "0")
                if company_name in name:
                    return doc.get("docID"), name, desc, csv_flag
        except Exception:
            continue
    return None, None, None, "0"

# ----------------------------
# CSVから財務指標抽出
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
# XBRLから財務指標抽出
# ----------------------------
def extract_metrics_from_xbrl(xml_content):
    soup = BeautifulSoup(xml_content, "xml")
    results = {}

    tag_map = {
        "NetSales": ["NetSales", "NetSalesConsolidated", "NetSalesOfReportingSegment"],
        "OperatingIncome": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "OrdinaryIncome": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "NetIncome": ["NetIncome", "Profit", "NetIncomeAttributableToOwnersOfParent"],
    }

    for label, tags in tag_map.items():
        for tag in tags:
            found = soup.find(tag)
            if found and found.text.strip().isdigit():
                results[label] = found.text.strip()
                break
        if label not in results:
            results[label] = "N/A"

    return results

# ----------------------------
# docIDからCSVまたはXBRLを取得して抽出
# ----------------------------
def fetch_data_by_docid(doc_id, use_csv=True):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"

    if use_csv:
        try:
            res = requests.get(url, headers=headers, params={"type": 5}, timeout=15)
            if "zip" in res.headers.get("Content-Type", ""):
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    for file_name in z.namelist():
                        if file_name.endswith(".csv"):
                            with z.open(file_name) as f:
                                raw = f.read()
                                encoding = chardet.detect(raw)["encoding"]
                                df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                                return extract_financial_metrics(df), "CSV"
        except Exception as e:
            st.warning(f"[CSV取得失敗] {e}")

    # XBRLで再取得
    try:
        res = requests.get(url, headers=headers, params={"type": 1}, timeout=20)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for file_name in z.namelist():
                    if "PublicDoc" in file_name and file_name.endswith(".xbrl"):
                        with z.open(file_name) as f:
                            xml_data = f.read()
                            return extract_metrics_from_xbrl(xml_data), "XBRL"
    except Exception as e:
        st.warning(f"[XBRL取得失敗] {e}")

    raise ValueError("CSV・XBRLともに取得できませんでした。")

# ----------------------------
# Streamlit UI
# ----------------------------
st.header("企業名からEDINET財務データ検索")
company = st.text_input("企業名を入力（例: トヨタ自動車株式会社）")

if st.button("検索して財務データ表示"):
    if not company:
        st.warning("企業名を入力してください")
    else:
        with st.spinner("EDINETでdocID検索中..."):
            doc_id, name, desc, csv_flag = search_docid_by_company_name(company)
            if not doc_id:
                st.error("docIDが見つかりませんでした（対象書類がない可能性）")
            else:
                st.success(f"見つかりました：{name}｜{desc}｜docID: {doc_id}｜CSV: {csv_flag}")
                try:
                    metrics, source = fetch_data_by_docid(doc_id, use_csv=(csv_flag == "1"))
                    st.subheader(f"抽出された財務指標（{source}から取得）")
                    result_df = pd.DataFrame([{"指標": k, "金額": v} for k, v in metrics.items()])
                    st.table(result_df)
                except Exception as e:
                    st.error(f"データ取得に失敗しました: {e}")
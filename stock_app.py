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
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 日本語フォント設定（Cloud向け：NotoやIPAなどが有効な可能性あり）
plt.rcParams['font.family'] = 'Noto Sans CJK JP'

# .env 読み込み
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

st.title("📊 企業名からEDINET財務データを自動取得・グラフ化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` に 'EDINET_API_KEY' を追加してください。")
    st.stop()

# docID 検索（四半期報告書を優先）
def search_docid(company_name, days_back=180):
    date = datetime.today()
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    for _ in range(days_back):
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue
        url = f"{API_ENDPOINT}/documents.json"
        params = {"date": date.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for doc in res.json().get("results", []):
                if company_name in doc.get("filerName", "") and "四半期報告書" in doc.get("docDescription", ""):
                    return doc.get("docID"), doc.get("filerName"), doc.get("docDescription"), doc.get("csvFlag", "0")
        except:
            continue
    return None, None, None, "0"

# CSVから指標を抽出
def extract_from_csv(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {}
    keywords = {
        "売上高": "NetSales",
        "営業利益": "OperatingIncome",
        "経常利益": "OrdinaryIncome",
        "純利益": "NetIncome"
    }
    results = {}
    for jp, en in keywords.items():
        match = df[df["項目ID"].astype(str).str.contains(en, na=False)]
        if not match.empty:
            results[jp] = int(match.iloc[0]["金額"])
    return results

# XBRLから指標を抽出
def extract_from_xbrl(xml):
    soup = BeautifulSoup(xml, "xml")
    tags = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "経常利益": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "純利益": ["NetIncome", "NetIncomeAttributableToOwnersOfParent"]
    }
    result = {}
    for label, options in tags.items():
        for tag in options:
            found = soup.find(tag)
            if found and found.text.strip().isdigit():
                result[label] = int(found.text.strip())
                break
        if label not in result:
            result[label] = None
    return result

# docIDからデータ取得
def fetch_metrics(doc_id, use_csv=True):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url = f"{API_ENDPOINT}/documents/{doc_id}"

    if use_csv:
        try:
            res = requests.get(url, headers=headers, params={"type": 5}, timeout=15)
            if "zip" in res.headers.get("Content-Type", ""):
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    for name in z.namelist():
                        if name.endswith(".csv"):
                            raw = z.read(name)
                            enc = chardet.detect(raw)["encoding"]
                            df = pd.read_csv(io.BytesIO(raw), encoding=enc)
                            return extract_from_csv(df), "CSV"
        except Exception as e:
            st.warning(f"[CSVエラー] {e}")

    # fallback to XBRL
    try:
        res = requests.get(url, headers=headers, params={"type": 1}, timeout=20)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for name in z.namelist():
                    if name.endswith(".xbrl"):
                        xml = z.read(name)
                        return extract_from_xbrl(xml), "XBRL"
    except Exception as e:
        st.warning(f"[XBRLエラー] {e}")

    return {}, "取得失敗"

# グラフ描画
def plot_metrics(metrics, company_name):
    labels = list(metrics.keys())
    values = list(metrics.values())

    fig, ax = plt.subplots()
    ax.bar(labels, values)
    ax.set_title(f"{company_name} の財務指標")
    ax.set_ylabel("金額（百万円）")
    plt.xticks(rotation=30)
    st.pyplot(fig)

# UI
st.header("🔍 企業名から検索")
company = st.text_input("例: トヨタ自動車株式会社")

if st.button("財務データを取得・グラフ表示"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("EDINETからdocID検索中..."):
            docID, name, desc, csv_flag = search_docid(company)
        if not docID:
            st.error("docIDが見つかりませんでした。")
        else:
            st.success(f"✅ 見つかりました：{name}｜{desc}｜docID: {docID}｜CSV対応: {csv_flag}")
            metrics, source = fetch_metrics(docID, use_csv=(csv_flag == "1"))
            if not metrics:
                st.error("財務データが見つかりませんでした。")
            else:
                st.subheader(f"📊 抽出結果（{source}）")
                st.dataframe(pd.DataFrame(metrics.items(), columns=["指標", "金額"]))
                plot_metrics(metrics, name)

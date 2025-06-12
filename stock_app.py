import os
import io
import zipfile
import requests
import chardet
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import matplotlib.pyplot as plt

# 日本語フォント（Streamlit Cloud 向け）
plt.rcParams['font.family'] = 'Noto Sans CJK JP'

# 環境変数から APIキー取得
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

st.title("📦 企業名からEDINET ZIPを取得→解凍→財務指標を可視化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` に 'EDINET_API_KEY' を追加してください。")
    st.stop()

# ----------------------------
# docID 検索（四半期報告書を優先）
# ----------------------------
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

# ----------------------------
# ZIPを取得して保存・解凍
# ----------------------------
def download_and_extract_zip(docID, type=5):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url = f"{API_ENDPOINT}/documents/{docID}"
    params = {"type": type}
    res = requests.get(url, headers=headers, params=params, timeout=20)
    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("ZIPファイルが取得できませんでした。")

    temp_dir = f"temp_{docID}"
    os.makedirs(temp_dir, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        z.extractall(temp_dir)

    return temp_dir

# ----------------------------
# CSVから指標抽出
# ----------------------------
def extract_from_csv_folder(folder_path):
    for file in os.listdir(folder_path):
        if file.endswith(".csv"):
            with open(os.path.join(folder_path, file), "rb") as f:
                raw = f.read()
                enc = chardet.detect(raw)["encoding"]
                df = pd.read_csv(io.BytesIO(raw), encoding=enc)
                return extract_financials_from_df(df)
    return {}

# ----------------------------
# XBRLから指標抽出
# ----------------------------
def extract_from_xbrl_folder(folder_path):
    for file in os.listdir(folder_path):
        if file.endswith(".xbrl"):
            with open(os.path.join(folder_path, file), "rb") as f:
                xml = f.read()
                return extract_from_xbrl(xml)
    return {}

def extract_financials_from_df(df):
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

# ----------------------------
# グラフ描画
# ----------------------------
def plot_metrics(metrics, company_name):
    labels = list(metrics.keys())
    values = list(metrics.values())

    fig, ax = plt.subplots()
    ax.bar(labels, values)
    ax.set_title(f"{company_name} の財務指標")
    ax.set_ylabel("金額（百万円）")
    plt.xticks(rotation=30)
    st.pyplot(fig)

# ----------------------------
# UI 部分
# ----------------------------
st.header("🔍 企業名から財務データ検索・ZIP保存")
company = st.text_input("例：トヨタ自動車株式会社")

if st.button("ZIP取得・指標抽出・グラフ表示"):
    if not company:
        st.warning("企業名を入力してください")
    else:
        with st.spinner("docID検索中..."):
            docID, name, desc, csv_flag = search_docid(company)
        if not docID:
            st.error("docIDが見つかりませんでした。")
        else:
            st.success(f"✅ 見つかりました：{name}｜{desc}｜docID: {docID}｜CSV: {csv_flag}")
            with st.spinner("ZIPファイルをダウンロード・解凍中..."):
                folder = download_and_extract_zip(docID, type=5 if csv_flag == "1" else 1)

            st.write(f"📁 解凍先： `{folder}`")

            # データ抽出
            metrics = extract_from_csv_folder(folder) if csv_flag == "1" else extract_from_xbrl_folder(folder)

            if not metrics:
                st.error("財務指標が見つかりませんでした。")
            else:
                st.subheader(f"📈 財務指標（{desc}）")
                st.dataframe(pd.DataFrame(metrics.items(), columns=["指標", "金額"]))
                plot_metrics(metrics, name)

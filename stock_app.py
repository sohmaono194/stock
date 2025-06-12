import os
import io
import zipfile
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

# --- 初期設定 ---
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_URL = "https://api.edinet-fsa.go.jp/api/v2"

st.title("📦 EDINET 四半期報告書 ZIP → 財務指標グラフ")

if not API_KEY:
    st.error("APIキーが未設定です")
    st.stop()

# --- 関数定義 ---

# docID 検索（四半期報告書限定）
def find_docid(company_name, days=90):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for i in range(days):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:
            continue
        try:
            res = requests.get(
                f"{API_URL}/documents.json",
                params={"date": date.strftime("%Y-%m-%d"), "type": 2},
                headers=headers,
                timeout=10
            )
            res.raise_for_status()
            for item in res.json().get("results", []):
                name = item.get("filerName")
                desc = item.get("docDescription")
                if name and desc and company_name in name and "報告書" in desc:
                    return item["docID"], desc
        except Exception:
            continue
    return None, None


# ZIPファイルダウンロード・解凍
def download_and_extract_zip(doc_id, doc_type=5):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    res = requests.get(f"{API_URL}/documents/{doc_id}", params={"type": doc_type}, headers=headers, timeout=20)
    if "zip" not in res.headers.get("Content-Type", ""):
        return None

    folder = f"tmp_{doc_id}"
    os.makedirs(folder, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        z.extractall(folder)
    return folder

# CSV解析
def parse_csv(folder_path):
    for fname in os.listdir(folder_path):
        if fname.endswith(".csv"):
            with open(os.path.join(folder_path, fname), "rb") as f:
                raw = f.read()
                encoding = "utf-8"  # fallback
                try:
                    import chardet
                    encoding = chardet.detect(raw)["encoding"]
                except:
                    pass
                df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                return df
    return None

# XBRL解析
def parse_xbrl(folder_path):
    for fname in os.listdir(folder_path):
        if fname.endswith(".xbrl"):
            with open(os.path.join(folder_path, fname), "rb") as f:
                return f.read()
    return None

# 財務指標抽出（CSV or XBRL）
def extract_metrics(df=None, xml=None):
    keywords = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "経常利益": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "純利益": ["NetIncome", "Profit", "NetIncomeAttributableToOwnersOfParent"],
    }
    results = {}

    if df is not None:
        for label, keys in keywords.items():
            found = pd.Series(dtype=str)
            for k in keys:
                found = df[df["項目ID"].astype(str).str.contains(k, na=False)]
                if not found.empty:
                    break
            results[label] = int(found.iloc[0]["金額"]) if not found.empty else None

    elif xml is not None:
        soup = BeautifulSoup(xml, "xml")
        for label, keys in keywords.items():
            val = None
            for tag in keys:
                el = soup.find(tag)
                if el and el.text.strip().isdigit():
                    val = int(el.text.strip())
                    break
            results[label] = val

    return results

# グラフ描画
def show_graph(data):
    df = pd.DataFrame(data.items(), columns=["指標", "金額"])
    df["金額"] = pd.to_numeric(df["金額"], errors="coerce")
    sns.set_style("whitegrid")
    plt.figure(figsize=(6, 4))
    sns.barplot(data=df, x="指標", y="金額")
    plt.title("財務指標")
    st.pyplot(plt.gcf())
    plt.clf()

# --- Streamlit UI ---
st.header("企業名から docID を検索 → 財務データ取得")
company = st.text_input("企業名を入力（例：トヨタ自動車株式会社）")

if st.button("実行"):
    if not company:
        st.warning("企業名を入力してください")
        st.stop()

    with st.spinner("docIDを検索中..."):
        doc_id, desc = find_docid(company)
        if not doc_id:
            st.error("該当する四半期報告書が見つかりませんでした")
            st.stop()
        st.success(f"✅ 見つかりました：{desc}｜docID: {doc_id}")

    with st.spinner("ZIPファイルを取得中..."):
        folder = download_and_extract_zip(doc_id, doc_type=5)
        if not folder:
            st.warning("CSV取得に失敗。XBRLに切り替えます...")
            folder = download_and_extract_zip(doc_id, doc_type=1)
            xml = parse_xbrl(folder)
            if not xml:
                st.error("XBRLも取得できませんでした。")
                st.stop()
            metrics = extract_metrics(xml=xml)
        else:
            df = parse_csv(folder)
            if df is None:
                st.warning("CSV解析に失敗。XBRLに切り替えます...")
                folder = download_and_extract_zip(doc_id, doc_type=1)
                xml = parse_xbrl(folder)
                metrics = extract_metrics(xml=xml)
            else:
                metrics = extract_metrics(df=df)

    st.subheader("📊 抽出された財務指標")
    st.write(metrics)
    show_graph(metrics)

import os
import time
import zipfile
import io

import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from dotenv import load_dotenv
from datetime import datetime, timedelta
import chardet

# フォント指定（Windows用: MS Gothic）
plt.rcParams["font.family"] = "MS Gothic"

# .envからAPIキーを読み込む
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

st.title("📊 EDINET 財務データ可視化アプリ")

if not API_KEY:
    st.error("EDINET_API_KEY が .env または環境変数に設定されていません")
    st.stop()

# -----------------------------
# docID検索関数（報告書を対象）
# -----------------------------
def find_docid(company_name, days_back=90):
    today = datetime.today()
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    for i in range(days_back):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        params = {"date": date_str, "type": 2}
        try:
            res = requests.get(f"{API_ENDPOINT}/documents.json", headers=headers, params=params, timeout=10)
            res.raise_for_status()
            results = res.json().get("results", [])
            for item in results:
                if company_name in item.get("filerName", "") and "報告書" in item.get("docDescription", ""):
                    return item.get("docID"), item.get("docDescription", "")
        except:
            continue
    return None, None

# -----------------------------
# ZIPダウンロード＋解凍処理
# -----------------------------
def download_and_extract_zip(docID, extract_dir):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 5}
    url = f"{API_ENDPOINT}/documents/{docID}"
    res = requests.get(url, headers=headers, params=params, timeout=15)

    if res.status_code != 200 or "zip" not in res.headers.get("Content-Type", ""):
        return False

    os.makedirs(extract_dir, exist_ok=True)
    temp_zip_path = os.path.join(extract_dir, f"{docID}.zip")

    with open(temp_zip_path, "wb") as f:
        f.write(res.content)

    with zipfile.ZipFile(temp_zip_path, "r") as z:
        z.extractall(extract_dir)

    os.remove(temp_zip_path)
    return True

# -----------------------------
# 財務指標の抽出
# -----------------------------
def extract_metrics_from_csv(folder):
    result = {}
    for file in os.listdir(folder):
        if file.endswith(".csv"):
            path = os.path.join(folder, file)
            raw = open(path, "rb").read()
            enc = chardet.detect(raw)["encoding"]
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=enc)
                if {"項目ID", "金額"}.issubset(df.columns):
                    for key in ["NetSales", "OperatingIncome", "OrdinaryIncome", "NetIncome"]:
                        match = df[df["項目ID"].str.contains(key, na=False)]
                        if not match.empty:
                            result[key] = match.iloc[0]["金額"]
            except:
                continue
    return result

# -----------------------------
# グラフ描画
# -----------------------------
def plot_metrics(metrics):
    if not metrics:
        st.warning("財務データが見つかりませんでした")
        return

    labels = {"NetSales": "売上高", "OperatingIncome": "営業利益", "OrdinaryIncome": "経常利益", "NetIncome": "純利益"}
    values = [int(metrics[k]) for k in metrics if metrics[k].isdigit()]
    keys = [labels[k] for k in metrics if metrics[k].isdigit()]

    fig, ax = plt.subplots()
    ax.bar(keys, values)
    ax.set_ylabel("金額（単位: 百万円）")
    ax.set_title("抽出された財務指標")
    st.pyplot(fig)

# -----------------------------
# Streamlit UI本体
# -----------------------------
company = st.text_input("企業名を入力（例: トヨタ自動車株式会社）")

if st.button("データ取得・表示"):
    if not company:
        st.warning("企業名を入力してください")
        st.stop()

    with st.spinner("EDINETからdocIDを検索中..."):
        docID, description = find_docid(company)

    if not docID:
        st.error("該当する報告書が見つかりませんでした")
    else:
        st.success(f"docID: {docID}｜{description}")
        extract_dir = f"temp_{docID}"
        with st.spinner("ZIPファイルをダウンロードして解凍中..."):
            if download_and_extract_zip(docID, extract_dir):
                metrics = extract_metrics_from_csv(extract_dir)
                plot_metrics(metrics)
            else:
                st.error("ZIPファイルの取得または解凍に失敗しました")

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
import japanize_matplotlib

# 初期設定
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")
API_BASE = "https://disclosure.edinet-fsa.go.jp/api/v2"

st.title("📊 EDINET 財務データ 自動取得 & グラフ化アプリ")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` に 'EDINET_API_KEY' を設定してください。")
    st.stop()

# docID検索（報告書）
def find_docid(company_name, days=90):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for i in range(days):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:
            continue
        try:
            res = requests.get(f"{API_BASE}/documents.json",
                               params={"date": date.strftime("%Y-%m-%d"), "type": 2},
                               headers=headers, timeout=10)
            for item in res.json().get("results", []):
                name = item.get("filerName", "")
                desc = item.get("docDescription", "")
                if company_name in name and "報告書" in desc:
                    return item["docID"], desc
        except:
            continue
    return None, None

# CSV抽出
def parse_csv_metrics(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        raise ValueError("CSVに必要な列がありません。")
    metrics = {}
    key_map = {
        "NetSales": "売上高", "OperatingIncome": "営業利益",
        "OrdinaryIncome": "経常利益", "NetIncome": "純利益"
    }
    for key, label in key_map.items():
        match = df[df["項目ID"].astype(str).str.contains(key, na=False)]
        if not match.empty:
            try:
                metrics[label] = int(match.iloc[0]["金額"])
            except:
                metrics[label] = match.iloc[0]["金額"]
        else:
            metrics[label] = None
    return metrics

# XBRL抽出
def parse_xbrl_metrics(xml_data):
    soup = BeautifulSoup(xml_data, "xml")
    results = {}
    tag_map = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "経常利益": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "純利益": ["NetIncome", "Profit", "NetIncomeAttributableToOwnersOfParent"],
    }
    for label, tags in tag_map.items():
        for tag in tags:
            found = soup.find(tag)
            if found and found.text.strip().isdigit():
                results[label] = int(found.text.strip())
                break
        if label not in results:
            results[label] = None
    return results

# ZIP取得と解析
def fetch_and_parse_zip(doc_id):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    # CSV優先
    try:
        res = requests.get(f"{API_BASE}/documents/{doc_id}", params={"type": 5}, headers=headers, timeout=15)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for name in z.namelist():
                    if name.endswith(".csv"):
                        with z.open(name) as f:
                            raw = f.read()
                            enc = chardet.detect(raw)["encoding"]
                            df = pd.read_csv(io.BytesIO(raw), encoding=enc)
                            return parse_csv_metrics(df), "CSV"
    except Exception as e:
        st.warning(f"[CSV失敗] {e}")
    # XBRL fallback
    try:
        res = requests.get(f"{API_BASE}/documents/{doc_id}", params={"type": 1}, headers=headers, timeout=15)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for name in z.namelist():
                    if "PublicDoc" in name and name.endswith(".xbrl"):
                        with z.open(name) as f:
                            return parse_xbrl_metrics(f.read()), "XBRL"
    except Exception as e:
        st.warning(f"[XBRL失敗] {e}")
    raise ValueError("ZIPファイルが取得できませんでした。")

# UI本体
company = st.text_input("企業名を入力（例：トヨタ自動車）")
if st.button("財務データ取得"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docID検索中..."):
            doc_id, desc = find_docid(company)
            if not doc_id:
                st.error("該当する報告書が見つかりませんでした。")
            else:
                st.success(f"{desc}｜docID: {doc_id}")
                try:
                    metrics, source = fetch_and_parse_zip(doc_id)
                    df = pd.DataFrame([{"指標": k, "金額": v} for k, v in metrics.items()])
                    st.subheader(f"{source}から抽出された財務指標")
                    st.table(df)

                    st.subheader("📊 グラフ")
                    df_plot = df[df["金額"].notnull()]
                    fig, ax = plt.subplots()
                    ax.bar(df_plot["指標"], df_plot["金額"])
                    ax.set_ylabel("金額（円）")
                    st.pyplot(fig)
                except Exception as e:
                    st.error(f"データ取得または解析に失敗しました：{e}")

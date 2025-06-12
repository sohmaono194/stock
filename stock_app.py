import os, io, zipfile, requests, chardet
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_URL = "https://api.edinet-fsa.go.jp/api/v2"

st.title("EDINET 四半期報告書 ZIP → 指標抽出 + グラフ化")

if not API_KEY:
    st.error("APIキーが未設定です")
    st.stop()

# docID探索
def find_docid(company, days=365):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()
    for i in range(days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            res = requests.get(f"{API_URL}/documents.json",
                               params={"date": d.strftime("%Y-%m-%d"), "type":2},
                               headers=headers, timeout=10)
            if res.status_code != 200:
                continue

            for it in res.json().get("results", []):
                name = it.get("filerName")
                desc = it.get("docDescription")
                if name and desc and company in name and "四半期報告書" in desc:
                    return it["docID"], desc
        except Exception:
            continue
    return None, None


# ZIP取得＆展開
def download_zip(doc_id, doc_type=5):
    res = requests.get(f"{API_URL}/documents/{doc_id}", params={"type": doc_type},
                       headers={"Ocp-Apim-Subscription-Key":API_KEY}, timeout=20)
    if "zip" not in res.headers.get("Content-Type",""):
        st.warning("ZIP取得できませんでした")
        return None
    folder = f"tmp_{doc_id}"
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        z.extractall(folder)
    return folder

# CSV解析
def parse_csv_files(folder):
    for f in os.listdir(folder):
        if f.endswith(".csv"):
            raw = open(os.path.join(folder,f),"rb").read()
            enc = chardet.detect(raw)["encoding"]
            df = pd.read_csv(io.BytesIO(raw), encoding=enc)
            return df
    return None

# 指標取得（CSV/XBRL共用）
def extract_metrics(df=None, xml=None):
    metrics = {"売上高":"NetSales", "営業利益":"OperatingIncome",
               "経常利益":"OrdinaryIncome", "純利益":"NetIncome"}
    out = {}
    if df is not None:
        for jp, en in metrics.items():
            m = df[df["項目ID"].astype(str).str.contains(en,na=False)]
            out[jp] = int(m.iloc[0]["金額"]) if not m.empty else None
    elif xml is not None:
        soup = BeautifulSoup(xml, "xml")
        for jp, tags in metrics.items():
            for t in [tags, tags+"Consolidated"]:
                e = soup.find(t)
                if e and e.text.strip().isdigit():
                    out[jp] = int(e.text.strip())
                    break
            if jp not in out: out[jp] = None
    return out

# グラフ化
def plot_metrics(data):
    df = pd.DataFrame(data.items(), columns=["Item","Value"])
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    sns.barplot(x="Item", y="Value", data=df)
    st.pyplot(plt.gcf())
    plt.clf()

# UI
company = st.text_input("企業名（例：トヨタ自動車株式会社）")
if st.button("実行"):
    if not company.strip():
        st.warning("企業名を入力してください")
    else:
        doc_id, desc = find_docid(company)
        if not doc_id:
            st.error("該当書類なし")
        else:
            st.success(f"{desc} → docID: {doc_id}")
            folder = download_zip(doc_id, doc_type=5)
            df = parse_csv_files(folder) if folder else None
            if df is not None:
                metrics = extract_metrics(df=df)
                st.write(metrics)
                plot_metrics(metrics)
            else:
                # XBRL fallback
                z2 = download_zip(doc_id, doc_type=1)
                xml = None
                for f in os.listdir(z2):
                    if f.endswith(".xbrl"):
                        xml = open(os.path.join(z2,f),"rb").read()
                        break
                if xml:
                    metrics = extract_metrics(xml=xml)
                    st.write(metrics)
                    plot_metrics(metrics)
                else:
                    st.error("データ取得失敗")

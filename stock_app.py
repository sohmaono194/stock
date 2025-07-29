import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env から環境変数を読み込む
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📊 企業名からEDINET財務データを自動取得・可視化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` ファイルまたは環境変数 'EDINET_API_KEY' を確認してください。")
    st.stop()

# ----------------------------
# docIDを企業名で検索
# ----------------------------
def search_docid_by_company_name(company_name, days_back=180):
    date = datetime.today()
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    for _ in range(days_back):
        date -= timedelta(days=1)
        if date.weekday() >= 5:  # 土日をスキップ
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {"date": date.strftime('%Y-%m-%d'), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for doc in res.json().get("results", []):
                name = doc.get("filerName", "")
                desc = doc.get("docDescription", "")
                if company_name in name and any(kw in desc for kw in ["有価証券報告書", "四半期報告書", "半期報告書"]):
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
        candidates = []
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)["encoding"]
                    try:
                        df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                        if "項目ID" in df.columns and "金額" in df.columns:
                            candidates.append((df, file_name, len(df)))
                    except Exception:
                        continue
        if not candidates:
            raise FileNotFoundError("CSVファイルが見つかりませんでした")
        # 行数が最も多いものを選ぶ
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[0][0], candidates[0][1]

# ----------------------------
# 財務指標を抽出
# ----------------------------
def extract_financial_metrics(df):
    keywords = {
        "NetSales": "売上高",
        "OperatingIncome": "営業利益",
        "OrdinaryIncome": "経常利益",
        "NetIncome": "当期純利益"
    }
    extracted = []
    for kw, label in keywords.items():
        matches = df[df["項目ID"].astype(str).str.contains(kw, na=False)]
        if not matches.empty:
            latest = matches.iloc[0]  # 最新の行を選ぶ
            amount = latest.get("金額", "")
            try:
                amount_fmt = f"{int(amount):,}"
            except:
                amount_fmt = amount
            extracted.append({"指標": label, "英語ID": kw, "金額": amount_fmt})
    return pd.DataFrame(extracted)

# ----------------------------
# UI
# ----------------------------
st.header("🔍 企業名からdocIDを検索し、財務CSVを取得")
company = st.text_input("企業名を入力（例: トヨタ自動車株式会社）")

if st.button("検索して財務データ表示"):
    if not company:
        st.warning("企業名を入力してください")
    else:
        with st.spinner("EDINETでdocIDを検索中..."):
            doc_id, name, desc = search_docid_by_company_name(company)
            if not doc_id:
                st.error("該当する企業のdocIDが見つかりませんでした（CSV対応書類でない可能性あり）")
            else:
                st.success(f"✅ 見つかりました：{name}｜{desc}｜docID: {doc_id}")
                try:
                    df, fname = fetch_csv_from_docid(doc_id)
                    st.write(f"📂 ファイル名: {fname}")
                    st.dataframe(df.head(30))

                    st.subheader("📈 抽出された財務指標")
                    metrics_df = extract_financial_metrics(df)
                    if metrics_df.empty:
                        st.warning("主要な財務指標が見つかりませんでした。")
                    else:
                        st.table(metrics_df)
                        # グラフ表示
                        st.bar_chart(metrics_df.set_index("指標")["金額"].astype(str).str.replace(",", "").astype(float))
                except Exception as e:
                    st.error(f"CSVの取得または解析中にエラーが発生しました: {e}")

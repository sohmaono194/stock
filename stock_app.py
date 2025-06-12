# app.py
import streamlit as st
import os
import zipfile
import requests
import pandas as pd
import chardet
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"


def search_docid_by_company(company_name, days_back=60):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for _ in range(days_back):
        today -= timedelta(days=1)
        if today.weekday() >= 5:
            continue

        url = f"{API_ENDPOINT}/documents.json"
        params = {"date": today.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for item in res.json().get("results", []):
                name = item.get("filerName", "")
                desc = item.get("docDescription", "")
                doc_id = item.get("docID", "")
                csv_flag = item.get("csvFlag", "0")
                if company_name in name and any(x in desc for x in ["四半期報告書", "有価証券報告書", "半期報告書"]):
                    return doc_id, name, desc, csv_flag
        except Exception:
            continue

    return None, None, None, "0"


def fetch_and_extract_csv(docID, doc_type=5):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url = f"{API_ENDPOINT}/documents/{docID}?type={doc_type}"

    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        st.error(f"[ERROR] 書類取得に失敗: {e}")
        return None

    temp_zip_path = f"{docID}.zip"
    with open(temp_zip_path, "wb") as f:
        f.write(res.content)

    try:
        with zipfile.ZipFile(temp_zip_path, "r") as z:
            for file_name in z.namelist():
                if file_name.endswith(".csv"):
                    with z.open(file_name) as f:
                        raw = f.read()
                        encoding = chardet.detect(raw)['encoding']
                        df = pd.read_csv(pd.io.common.BytesIO(raw), encoding=encoding)
                        return df
    except zipfile.BadZipFile:
        st.error("ZIPファイルが壊れています")
    finally:
        os.remove(temp_zip_path)

    return None


def extract_financial_metrics(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {"エラー": "CSVに必要な列（項目ID、金額）がありません"}

    keywords = {
        "売上高": ["NetSales", "SalesRevenue"],
        "営業利益": ["OperatingIncome"],
        "経常利益": ["OrdinaryIncome"],
        "純利益": ["NetIncome", "ProfitAttributableToOwnersOfParent"]
    }

    result = {}
    for label, tag_list in keywords.items():
        for tag in tag_list:
            row = df[df["項目ID"].astype(str).str.contains(tag, na=False)]
            if not row.empty:
                result[label] = row.iloc[0]["金額"]
                break
        else:
            result[label] = "N/A"
    return result


# Streamlit UI
st.title("📊 EDINET 財務データ 自動取得アプリ")

if not API_KEY:
    st.error("環境変数 'EDINET_API_KEY' が設定されていません。")
    st.stop()

company = st.text_input("企業名を入力してください（例：トヨタ自動車株式会社）")

if st.button("検索して財務指標を表示"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docIDを検索中..."):
            doc_id, name, desc, csv_flag = search_docid_by_company(company)
        if doc_id:
            st.success(f"✅ 書類見つかりました：{name}｜{desc}｜docID: {doc_id}")
            if csv_flag == "1":
                with st.spinner("CSV ZIPからデータ抽出中..."):
                    df = fetch_and_extract_csv(doc_id)
                    if df is not None:
                        metrics = extract_financial_metrics(df)
                        st.subheader("📈 財務指標")
                        st.dataframe(pd.DataFrame([metrics]))
            else:
                st.warning("CSV形式ではありません（XBRL対応が必要です）")
        else:
            st.error("該当する書類が見つかりませんでした。")

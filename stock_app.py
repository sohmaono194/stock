import streamlit as st
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta

# --- APIキーの読み込み（Streamlit Cloudでは環境変数から直接取得） ---
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📄 EDINET提出書類から財務情報を抽出・可視化するアプリ")

# ============================
# 🧩 docID ZIP → XBRL読み取り
# ============================

def extract_xbrl_from_zip(doc_id):
    url = f"https://disclosure.edinet-fsa.go.jp/api/v1/documents/{doc_id}"
    params = {"type": 1}
    res = requests.get(url, params=params, timeout=20, verify=False)

    content_type = res.headers.get("Content-Type", "")
    if "zip" in content_type:
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            for file_name in z.namelist():
                if file_name.endswith(".xbrl"):
                    with z.open(file_name) as xbrl_file:
                        return xbrl_file.read().decode("utf-8")
        raise FileNotFoundError("XBRLファイルが見つかりませんでした")
    elif "pdf" in content_type:
        raise ValueError("このdocIDはPDFファイルであり、XBRLデータは含まれていません。")
    elif "html" in content_type:
        raise ValueError("このdocIDはHTML形式です。無効または公開期限切れの可能性があります。")
    elif "json" in content_type:
        raise ValueError("このdocIDはXBRL等のファイルを提供していません。別のdocIDをお試しください。")
    else:
        raise ValueError(f"未知のファイル形式です（Content-Type: {content_type}）")

# ============================
# 📥 docID → CSV読み込み（API v2）
# ============================

def fetch_csv_from_docid(doc_id):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 5}  # CSV取得
    res = requests.get(url, headers=headers, params=params, timeout=20)

    content_type = res.headers.get("Content-Type", "")
    if "zip" not in content_type:
        raise ValueError(f"CSVファイルではありません（Content-Type: {content_type}）")

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)["encoding"]
                    return pd.read_csv(io.BytesIO(raw), encoding=encoding), file_name
    raise FileNotFoundError("CSVファイルがZIP内に見つかりませんでした。")

# ============================
# 🔍 XBRLから数値を抽出
# ============================

def extract_financial_data_from_xbrl(xbrl_text):
    root = ET.fromstring(xbrl_text)
    ns = {"jp": "http://www.xbrl.go.jp/jp/fr/gaap/2023-03-31"}

    items = {
        "売上高": ["jp:NetSales", "jp:OperatingRevenue"],
        "営業利益": ["jp:OperatingIncome"],
        "経常利益": ["jp:OrdinaryIncome"],
        "純利益": ["jp:ProfitAttributableToOwnersOfParent", "jp:NetIncome"]
    }

    results = {}
    for key, tags in items.items():
        for tag in tags:
            elem = root.find(f".//{tag}", ns)
            if elem is not None and elem.text:
                results[key] = elem.text
                break
        if key not in results:
            results[key] = "取得失敗"
    return results

# ============================
# 🔍 全財務タグ一覧表示
# ============================

def list_all_financial_tags(xbrl_text):
    root = ET.fromstring(xbrl_text)
    tags = set()
    for elem in root.iter():
        if elem.tag.startswith("{http://www.xbrl.go.jp/jp/fr/gaap"):
            tag_clean = elem.tag.split("}")[-1]
            tags.add(tag_clean)
    return sorted(tags)

# ============================
# ✅ docIDがZIPファイルかチェック
# ============================

def is_zip_doc(doc_id):
    url = f"https://disclosure.edinet-fsa.go.jp/api/v1/documents/{doc_id}"
    try:
        res = requests.get(url, params={"type": 1}, timeout=10, verify=False)
        return "zip" in res.headers.get("Content-Type", "")
    except:
        return False

# ============================
# 🔍 EDINETから最新docIDを取得（ZIP形式のみ）
# ============================

def fetch_recent_doc_ids(limit=20):
    results = []
    checked = 0
    date = datetime.today()

    while len(results) < limit and checked < 90:
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue

        url = "https://disclosure.edinet-fsa.go.jp/api/v1/documents.json"
        params = {"date": date.strftime('%Y-%m-%d'), "type": 2}

        try:
            res = requests.get(url, params=params, timeout=10, verify=False)
            docs = res.json().get("results", [])
            for doc in docs:
                if doc.get("xbrlFlag") == "1" and is_zip_doc(doc["docID"]):
                    results.append({
                        "date": date.strftime('%Y-%m-%d'),
                        "docID": doc.get("docID"),
                        "filerName": doc.get("filerName"),
                        "docDescription": doc.get("docDescription")
                    })
                    if len(results) >= limit:
                        break
        except Exception as e:
            st.warning(f"{date.strftime('%Y-%m-%d')} の取得失敗: {e}")
        checked += 1
    return results

# ============================
# Streamlit UI
# ============================

st.header("📥 docIDを入力して財務情報を取得")
doc_id = st.text_input("EDINETのdocIDを入力（例: S100UP32）")

if st.button("財務データを抽出"):
    if not doc_id:
        st.warning("docIDを入力してください")
    else:
        with st.spinner("データ抽出中..."):
            try:
                xbrl_text = extract_xbrl_from_zip(doc_id)
                data = extract_financial_data_from_xbrl(xbrl_text)
                st.success("✅ 抽出成功！")
                for k, v in data.items():
                    st.write(f"{k}: {v}")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

if st.button("🔍 全財務タグを表示"):
    if not doc_id:
        st.warning("docIDを入力してください")
    else:
        with st.spinner("タグ抽出中..."):
            try:
                xbrl_text = extract_xbrl_from_zip(doc_id)
                tags = list_all_financial_tags(xbrl_text)
                st.success(f"📄 タグ数: {len(tags)} 件")
                st.code("\n".join(tags))
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

st.header("📄 最新のEDINET提出書類（XBRLありdocID一覧）")
if st.button("📥 直近のdocIDを取得"):
    with st.spinner("最新提出書類を取得中..."):
        docs = fetch_recent_doc_ids(limit=30)
        if docs:
            for d in docs:
                st.write(f"{d['date']}｜{d['filerName']}｜{d['docDescription']}｜docID: {d['docID']}")
        else:
            st.warning("docIDが取得できませんでした。通信環境や日付を確認してください。")

st.header("📊 docIDからCSV財務データ取得（API経由）")
csv_doc_id = st.text_input("CSVファイルを取得するdocID（例: S100UP32）")

if st.button("CSVを取得＆表示"):
    if not csv_doc_id:
        st.warning("docIDを入力してください。")
    else:
        with st.spinner("CSVデータ取得中..."):
            try:
                df, fname = fetch_csv_from_docid(csv_doc_id)
                st.success(f"✅ CSV取得成功: {fname}")
                st.dataframe(df.head(30))
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

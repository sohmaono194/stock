import os
import time
import zipfile
import requests
import pandas as pd
import chardet

API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

def fetch_and_extract_csv(docID, doc_type=5):
    headers = {"Ocp-Apim-Subscription-Key": os.environ.get("EDINET_API_KEY")}
    url = f"{API_ENDPOINT}/documents/{docID}?type={doc_type}"
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 書類取得に失敗: {e}")
        return None

    # 一時ZIP保存
    temp_zip_path = f"{docID}.zip"
    with open(temp_zip_path, "wb") as f:
        f.write(res.content)

    # ZIP解凍とCSV読み込み
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
        print("[ERROR] ZIPファイルが壊れています")
    finally:
        os.remove(temp_zip_path)

    print("[WARNING] CSVファイルが見つかりませんでした")
    return None

def extract_financial_metrics(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {"エラー": "必要な列（項目ID、金額）が存在しません"}

    # 英語のタグ名で検索（jpcrp_cor:〜 や NetSales など）
    keywords = {
        "売上高": ["NetSales", "SalesRevenue", "Revenue"],
        "営業利益": ["OperatingIncome"],
        "経常利益": ["OrdinaryIncome"],
        "純利益": ["NetIncome", "ProfitAttributableToOwnersOfParent"]
    }

    result = {}
    for label, tag_list in keywords.items():
        for tag in tag_list:
            row = df[df["項目ID"].str.contains(tag, na=False)]
            if not row.empty:
                result[label] = row.iloc[0]["金額"]
                break
        else:
            result[label] = "N/A"

    return result

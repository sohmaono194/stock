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

API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"  # v2を使用する


def save_csv(docID, type=5):
    """EDINETからデータを取得してフォルダに保存する

    Args:
        docID (str): DocID
    """
    assert type in [1, 2, 3, 4, 5], "typeの指定が間違っている"
    if type == 1:
        print(f"{docID}のXBRLデータを取得中")
    elif type == 2:
        print(f"{docID}のpdfデータを取得中")
    elif type in {3, 4}:
        print(f"{docID}のデータを取得中")
    elif type == 5:
        print(f"{docID}のcsvデータを取得中")
        time.sleep(5)

    r = requests.get(
        f"{API_ENDPOINT}/documents/{docID}",
        {
            "type": type,
            "Subscription-Key": os.environ.get("EDINET_API_KEY"),
        },
    )

    if r is None:
        print("データの取得に失敗しました。csvFlag==1かどうか確認してください。")
    else:
        os.makedirs(f"{docID}", exist_ok=True)
        temp_zip = "uuid_89FD71B5_CD7B_4833-B30D‗5AA5006097E2.zip"

        with open(temp_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                f.write(chunk)

        with zipfile.ZipFile(temp_zip) as z:
            z.extractall(f"{docID}")

        os.remove(temp_zip)

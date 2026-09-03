import os
import time
import random
import requests
import pandas as pd
import json

def fetch_from_mops(stock_id: str, year: int, season: int, market_type: str) -> pd.DataFrame:
    """向 MOPS 發送請求並回傳原始 DataFrame"""
    url = "https://mops.twse.com.tw/mops/web/ajax_t164sb05"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    payload = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": market_type,  # 'sii' 或 'otc'
        "isnew": "false",
        "co_id": stock_id,
        "year": str(year),
        "season": str(season)
    }

    response = requests.post(url, data=payload, headers=headers, timeout=20)
    response.raise_for_status()
    dfs = pd.read_html(response.text)
    if len(dfs) >= 2:
        return dfs[1]
    return pd.DataFrame()

def audit_mops_cash_flow(stock_id: str, year: int, season: int) -> dict:
    """自動偵測上市 (sii) 與上櫃 (otc)，提取現金流量表核心數據"""
    df = pd.DataFrame()
    detected_market = "sii"

    # 第一階段：先以上市 (sii) 請求
    try:
        df = fetch_from_mops(stock_id, year, season, "sii")
    except Exception:
        df = pd.DataFrame()

    # 第二階段：若無資料，自動切換至上櫃 (otc) 回退重試
    if df.empty or "營業活動之淨現金流入" not in df.to_string():
        try:
            df = fetch_from_mops(stock_id, year, season, "otc")
            detected_market = "otc"
        except Exception as e:
            return {"status": "error", "stock_id": stock_id, "message": f"上市櫃端點請求均失敗: {str(e)}"}

    if df.empty:
        return {"status": "error", "stock_id": stock_id, "message": "查無有效財報數據"}

    try:
        df.columns = ["會計項目", "本期金額", "去年同期金額"]
        operating_cf_row = df[df['會計項目'].str.contains("營業活動之淨現金流入", na=False)]
        capex_row = df[df['會計項目'].str.contains("取得不動產、廠房及設備", na=False)]

        if operating_cf_row.empty or capex_row.empty:
            return {"status": "error", "stock_id": stock_id, "message": "關鍵會計欄位缺失"}

        operating_cf = float(str(operating_cf_row.iloc[0]["本期金額"]).replace(',', ''))
        capex = float(str(capex_row.iloc[0]["本期金額"]).replace(',', ''))
        fcf = operating_cf - abs(capex)

        return {
            "status": "success",
            "stock_id": stock_id,
            "market": detected_market,
            "operating_cf": operating_cf,
            "capex": capex,
            "free_cash_flow": fcf,
            "audit_signal": "PASS" if fcf > 0 else "WARNING_NEGATIVE_FCF"
        }
    except Exception as e:
        return {"status": "error", "stock_id": stock_id, "message": f"解析異常: {str(e)}"}

def main():
    # 範例清單：奇鋐 (3017 - 上市), 雙鴻 (3324 - 上櫃)
    target_stocks = ["3017", "3324"]
    audit_results = []

    print(f"啟動台股 AI 核心板塊稽核，共 {len(target_stocks)} 檔標的...")

    for idx, stock in enumerate(target_stocks):
        print(f"正在稽核標的: {stock} ...")
        # 以民國 113 年第 2 季為例 (可依據回測年份調整)
        report = audit_mops_cash_flow(stock, 113, 2)
        audit_results.append(report)

        # 隨機延遲防禦：避免 MOPS 防火牆觸發 Rate Limiting 封鎖 IP
        if idx < len(target_stocks) - 1:
            delay = round(random.uniform(3.0, 5.0), 2)
            print(f"冷卻等待 {delay} 秒以避免 IP 阻斷...")
            time.sleep(delay)

    print("=== 稽核最終報告 ===")
    print(json.dumps(audit_results, ensure_ascii=False, indent=2))

    # 若 GitHub Secrets 有注入 N8N_WEBHOOK_URL，則拋出數據
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if webhook_url:
        try:
            res = requests.post(webhook_url, json={"reports": audit_results}, timeout=10)
            print(f"n8n 推播狀態碼: {res.status_code}")
        except Exception as e:
            print(f"n8n 推播失敗: {e}")

if __name__ == "__main__":
    main()

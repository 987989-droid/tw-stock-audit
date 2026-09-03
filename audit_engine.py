import os
import requests
import pandas as pd
import json

def audit_mops_cash_flow(stock_id: str, year: int, season: int) -> dict:
    url = "https://mops.twse.com.tw/mops/web/ajax_t164sb05"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": "sii",
        "isnew": "false",
        "co_id": stock_id,
        "year": str(year),
        "season": str(season)
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        response.raise_for_status()
        
        dfs = pd.read_html(response.text)
        if len(dfs) < 2:
            return {"status": "error", "message": f"{stock_id} 無有效財報表格"}
            
        df = dfs[1]
        df.columns = ["會計項目", "本期金額", "去年同期金額"]
        
        operating_cf_row = df[df['會計項目'].str.contains("營業活動之淨現金流入", na=False)]
        capex_row = df[df['會計項目'].str.contains("取得不動產、廠房及設備", na=False)]
        
        if operating_cf_row.empty or capex_row.empty:
            return {"status": "error", "message": f"{stock_id} 關鍵欄位缺失"}

        operating_cf = float(str(operating_cf_row.iloc[0]["本期金額"]).replace(',', ''))
        capex = float(str(capex_row.iloc[0]["本期金額"]).replace(',', ''))
        fcf = operating_cf - abs(capex)

        return {
            "status": "success",
            "stock_id": stock_id,
            "operating_cf": operating_cf,
            "capex": capex,
            "free_cash_flow": fcf,
            "audit_signal": "PASS" if fcf > 0 else "WARNING_NEGATIVE_FCF"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    # 測試標的清單：奇鋐 (3017)
    target_stocks = ["3017"]
    audit_results = []

    # 執行稽核 (以民國 113 年第 2 季為例，可視需求調整)
    for stock in target_stocks:
        report = audit_mops_cash_flow(stock, 113, 2)
        audit_results.append(report)

    print("=== 稽核完成報告 ===")
    print(json.dumps(audit_results, ensure_ascii=False, indent=2))

    # 若 GitHub Actions 有配置 n8n Webhook，則自動發送結果
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if webhook_url:
        try:
            res = requests.post(webhook_url, json={"reports": audit_results}, timeout=10)
            print(f"n8n 推播狀態碼: {res.status_code}")
        except Exception as e:
            print(f"n8n 推播失敗: {e}")
    else:
        print("未設定 N8N_WEBHOOK_URL，跳過遠端推播。")

if __name__ == "__main__":
    main()

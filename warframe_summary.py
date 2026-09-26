"""Warframe 中文更新日誌（論壇）的摘要模組。

刻意跟 ai_summary.py 分開寫：兩者的公告「文體」差異很大——
楓之谷公告是活動/商城/維護，Warframe 論壇貼文是「改動 + 落落長的修正清單」，
硬塞進同一套 prompt/驗證規則只會讓兩邊都變得難維護。

低階的「呼叫 Gemini + 模型 fallback」邏輯直接重用 ai_summary.py，
不重複實作一份。
"""

from ai_summary import _api_key, _summarize_with_fallback


def build_warframe_prompt(title, body, url):
    return f"""你是 Warframe 繁體中文論壇「更新日誌」的 Discord 懶人包整理助手。
你的任務是把落落長的更新/熱修貼文，整理成一般玩家能快速掃過的懶人包。
只根據原文整理，不要推測、不要補充原文沒提到的資訊。

【貼文資訊】
標題：{title}
網址：{url}

【論壇原文】
{body[:40000]}

【輸出格式固定，只能輸出以下 4 個區塊，不要有多餘的開場白或結語】

📌 重點摘要
- 3～6 點，先讓玩家快速知道這次更新/熱修的重點方向（例如：主打修正什麼問題、
  有沒有數值調整、是否有退款/補償代碼）。
- 如果原文一開頭是感謝/閒聊性質的內容，這裡不需要整理，直接跳過。

⚖️ 改動與調整
- 列出原文中實際的數值調整、機制改動、平衡調整。
- 有具體數字（生命值、護盾、護甲、機率、傷害減免百分比等）務必完整保留，
  這些是玩家最在意、最容易被隨手摘要掉的部分。
- 如果原文沒有這類內容，寫「• 本次沒有數值或機制調整。」

🐛 修正的問題
- 原文的「修正」清單通常很長，不需要逐條照抄；把同類型、瑣碎的修正
  （例如多個裝飾/貼圖偏移問題）合併成一兩句概括帶過即可。
- 但牽涉到「崩潰」「進度遺失」「卡關/卡死」「無法遊玩」這類嚴重問題的修正，
  必須個別列出，不要被合併掉。
- 目標 5～10 點，抓大放小，不追求把原文全部修正項目都列完。

🔗 更多資訊
- 如果原文有提到「已知問題」討論串連結、回饋子論壇連結等，列在這裡（保留超連結網址）。
- 如果原文沒有這類連結，寫「• 原文沒有提供額外連結。」

【注意事項】
1. 不要輸出以上 4 個區塊以外的任何文字，第一行必須是「📌 重點摘要」。
2. 不要輸出 Markdown 的 # 標題。
3. 數字、代碼名稱、道具/裝備名稱只能引用原文，不要自行翻譯或改寫成別的說法。
4. 不要在最後加「以上」「希望有幫助」等聊天式結語。
"""


def _validate_warframe_summary(summary):
    if not summary:
        return False
    required = ["📌 重點摘要", "⚖️ 改動與調整", "🐛 修正的問題", "🔗 更多資訊"]
    if not all(x in summary for x in required):
        return False
    if len(summary) < 150:
        return False
    return True


def summarize_warframe(title, body, url):
    if not _api_key():
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_warframe_prompt(title, body, url)
    try:
        result, model_used = _summarize_with_fallback(prompt)
        print(f"Warframe 摘要使用模型：{model_used}")

        if _validate_warframe_summary(result):
            return result

        print("Warframe 摘要格式不完整，重新整理一次...")
        repair_prompt = prompt + f"""

上一版輸出格式不完整（缺少必要區塊或內容過短），請重新完整輸出，
務必包含「📌 重點摘要」「⚖️ 改動與調整」「🐛 修正的問題」「🔗 更多資訊」這 4 個區塊。
上一版輸出僅供參考，不要引用其中的錯誤格式：
{(result or "")[:4000]}
"""
        repaired, _repair_model = _summarize_with_fallback(repair_prompt)
        if _validate_warframe_summary(repaired):
            return repaired

        print("Warframe 摘要二次整理仍未完全通過格式檢查，使用二次結果送出。")
        return repaired or result
    except Exception as e:
        print(f"Warframe 摘要失敗：{e}")
        return None

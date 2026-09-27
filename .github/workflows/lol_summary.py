"""《英雄聯盟》版更公告的摘要模組。

這個網站的公告量級跟 Warframe/楓之谷完全不同——一篇版更公告
常常包含 15~20 位英雄改動、道具、系統、經典模式、大亂鬥、競技場，
硬套用「條列每一項」的格式，懶人包會比原文還長。
所以這裡的 prompt 刻意要求「精簡＋分類」，而不是逐條翻譯。
"""

from ai_summary import _api_key, _summarize_with_fallback


def build_lol_prompt(title, body, url):
    return f"""你是《英雄聯盟》繁體中文版更新公告的 Discord 懶人包整理助手。
原文通常很長（可能包含十幾位英雄改動、道具、系統、經典模式、大亂鬥、競技場等），
你的任務不是逐條翻譯，而是幫玩家快速抓到「這個版本影響大局的重點」。
只根據原文整理，不要推測、不要補充原文沒提到的資訊。

【公告資訊】
標題：{title}
網址：{url}

【原文】
{body[:60000]}

【輸出格式固定，只能輸出以下 5 個區塊，不要有多餘的開場白或結語】

📌 本次重點
- 2～4 點，這個版本的主軸方向是什麼（例如：世界大賽前置調整、削弱哪個強勢英雄、
  推出哪些新內容）。看完這一區塊，玩家應該大致知道「這個版本在幹嘛」。

⚔️ 英雄改動
- 用「強化：A、B、C」「削弱：D、E」「調整（有加有減）：F、G」這種一行帶過的方式列出，
  不要逐條列出每個技能的數值變化。
- 例外：如果某個英雄的改動明顯是本次「重點英雄」（原文用較長篇幅描述、或改動特別大、
  或標題/開場白特別提到），可以多加一句話說明改了什麼方向（強化清野、削弱後期等），
  但依然不要照抄原始數值。
- 如果本次沒有一般模式（召喚峽谷）的英雄改動，寫「• 本次沒有召喚峽谷英雄改動。」

🧪 道具與系統改動
- 簡短列出道具改動、系統改動（例如傳送、經濟、符文相關）的方向，一樣不用逐條列數值。
- 如果沒有，寫「• 本次沒有道具或系統改動。」

🎮 其他模式
- 如果原文有大亂鬥、競技場、經典模式（測試模式）等內容，各用 1～2 點簡述重點方向。
- 只列有出現在原文的模式，沒提到的模式不要寫。
- 如果原文完全沒有其他模式的內容，這區塊寫「• 本次沒有其他模式的更新內容。」

🔗 完整公告
- 固定寫一句提醒：「懶人包僅整理方向，詳細數值請點擊下方連結查看原文。」

【注意事項】
1. 不要輸出以上 5 個區塊以外的任何文字，第一行必須是「📌 本次重點」。
2. 不要輸出 Markdown 的 # 標題。
3. 英雄名稱、道具名稱只能引用原文用詞，不要自行翻譯或簡稱。
4. 不要在最後加「以上」「希望有幫助」等聊天式結語。
"""


def _validate_lol_summary(summary):
    if not summary:
        return False
    required = ["📌 本次重點", "⚔️ 英雄改動", "🧪 道具與系統改動", "🎮 其他模式"]
    if not all(x in summary for x in required):
        return False
    if len(summary) < 150:
        return False
    return True


def summarize_lol(title, body, url):
    if not _api_key():
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_lol_prompt(title, body, url)
    try:
        result, model_used = _summarize_with_fallback(prompt)
        print(f"LoL 摘要使用模型：{model_used}")

        if _validate_lol_summary(result):
            return result

        print("LoL 摘要格式不完整，重新整理一次...")
        repair_prompt = prompt + f"""

上一版輸出格式不完整（缺少必要區塊或內容過短），請重新完整輸出，
務必包含「📌 本次重點」「⚔️ 英雄改動」「🧪 道具與系統改動」「🎮 其他模式」「🔗 完整公告」這 5 個區塊。
上一版輸出僅供參考，不要引用其中的錯誤格式：
{(result or "")[:4000]}
"""
        repaired, _repair_model = _summarize_with_fallback(repair_prompt)
        if _validate_lol_summary(repaired):
            return repaired

        print("LoL 摘要二次整理仍未完全通過格式檢查，使用二次結果送出。")
        return repaired or result
    except Exception as e:
        print(f"LoL 摘要失敗：{e}")
        return None

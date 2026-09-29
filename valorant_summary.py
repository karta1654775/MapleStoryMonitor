"""VALORANT 官方版本更新公告的 Discord 懶人包摘要模組。"""

import re

from ai_summary import _api_key, _summarize_with_fallback


REQUIRED_SECTIONS = [
    "📌 本次重點",
    "🖥️ 介面／系統",
    "🏆 競技／生涯",
    "🎮 模式／地圖",
    "⚔️ 特務",
    "🔫 武器",
    "🛠️ 其他更新",
]


def build_valorant_prompt(title, body, url):
    return f"""你是《特戰英豪》台灣繁體中文官方版本更新公告的 Discord 懶人包整理助手。

這是一篇 Riot Games 官方《特戰英豪》版本更新公告。你的任務不是逐段翻譯，而是把「玩家真的需要知道」的內容整理成容易掃讀、但不能漏掉重大資訊的懶人包。

【最重要的原則】
1. 只根據下面提供的官方公告原文；不推測、不補充外部資料、不自行判斷強弱或推薦。
2. 原文是台灣繁體中文頁面時，角色、技能、武器、地圖、模式、系統等名稱必須沿用原文用詞，不要自行改寫成其他中文譯名。
3. 先完整讀取全文，再在心中建立「內容覆蓋清單」；這個清單不要輸出。確認所有玩家有實質影響的章節都有被處理後，再輸出懶人包。
4. 不要因為內容很多就只挑幾個大項。新增系統、競技規則、全新模式、新武器、特務改動、地圖輪替、玩家行為規則、主機版變動、重要錯誤修正等，若原文有提到，都必須出現在懶人包。
5. 對「數值」採取分級：重大新增內容與會直接影響玩法的數字要保留；大量細碎錯誤修正不必逐字重抄，但不得漏掉受影響的主要系統／特務／模式。
6. 如果某個章節沒有內容，請寫「• 本次沒有相關更新。」；不要自行省略區塊，也不要捏造內容。
7. 不要把 Riot 網站的導覽、頁尾、作者資訊、分享元件當成公告內容。
8. 不要把 TL;DR 原句整段複製到 Discord；要重新整理成條列。

【公告資訊】
標題：{title}
網址：{url}

【官方公告原文】
{body[:100000]}

【輸出格式固定，只能輸出以下 7 個區塊，不要輸出其他開場白或結語】

📌 本次重點
- 5～9 點。
- 這一區要像真正的「懶人包首頁」：把本版本最重要的新內容、重大系統改動、主要玩法改動先講清楚。
- 不要把錯誤修正或枝微末節塞在這裡。

🖥️ 介面／系統
- 整理 Home／Lobby、導覽、收藏、結算頁面、進度系統、用戶端等玩家會直接看到的系統變更。
- 新增或重做的系統要交代「做了什麼」以及「玩家會怎麼受到影響」。

🏆 競技／生涯
- 整理競技模式、牌階、Performance Score／ACS、MVP、Accolades、Rank Legacy、Career、排隊中進入靶場等內容。
- 原文有明確數字、適用模式、限制條件時務必保留。

🎮 模式／地圖
- 列出新模式、限時模式、模式下線、地圖輪替、地圖相關改動。
- 新模式若有玩家需要知道的核心規則，請用 2～4 點說清楚，不要只寫「推出新模式」。

⚔️ 特務
- 列出所有有「玩法／技能／數值」改動的特務名稱。
- 每位特務用 1 行說明主要改動方向；若有關鍵數值或會明顯改變玩法的內容，保留重要數字。
- 如果只有錯誤修正，放到「🛠️ 其他更新」，不要假裝是平衡調整。

🔫 武器
- 列出所有新增或調整的武器。
- 新武器必須保留價格、倍率、彈匣、傷害、射速、備彈等原文明確提供且對玩家有用的核心規格。
- 若只有少量武器調整，直接條列重點，不必長篇重抄。

🛠️ 其他更新
- 整理玩家行為／防作弊、語音系統、錯誤修正、主機版限定更新、已知問題，以及其他不適合上述分類但玩家應知道的內容。
- 大量 Bug Fix 可以合併整理，但若涉及競技結果、遊戲體驗、特務技能、武器、模式、商店或重大功能，請保留影響對象。

【完整度要求】
- 目標長度約 1800～4500 個中文字；內容很多時可以更長，但以「完整且可快速閱讀」為優先。
- 第一層條列不要全部只有一句模糊的「進行優化／調整」。
- 對玩家真正有影響的內容，至少說清楚「改了什麼」。
- 不要自行加入「這版本很大」「非常強」「值得玩」等評價。
- 不要加入任何官方公告沒有的日期、數值、規則或背景。
- 不要使用 Markdown 的 # 標題。
- 不要在最後加「以上」「希望有幫助」等聊天式結語。
- 輸出前自行檢查：是否漏掉新系統、新模式、新武器、競技改動、重要特務／武器變更、玩家行為規則、主機版內容或重大錯誤修正？若有，先補齊。
"""


def _section_bullets(summary, heading):
    if heading not in summary:
        return []
    part = summary.split(heading, 1)[1]
    next_headings = [x for x in REQUIRED_SECTIONS if x != heading and x in part]
    if next_headings:
        positions = [part.index(x) for x in next_headings]
        part = part[:min(positions)]
    return [
        line.strip()
        for line in part.splitlines()
        if line.strip().startswith("-")
    ]


def _validate_valorant_summary(summary):
    if not summary:
        return False
    if not all(x in summary for x in REQUIRED_SECTIONS):
        return False
    if len(summary) < 1000:
        return False

    # 檢查每個區塊都有內容，避免模型只吐出標題。
    for heading in REQUIRED_SECTIONS:
        bullets = _section_bullets(summary, heading)
        if not bullets:
            return False

    # 擋掉常見工作筆記。
    forbidden = [
        "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
        "上一版輸出", "工作筆記", "格式檢查結果", "覆蓋清單"
    ]
    if any(x in summary for x in forbidden):
        return False

    return True


def summarize_valorant(title, body, url):
    if not _api_key():
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_valorant_prompt(title, body, url)
    try:
        result, model_used = _summarize_with_fallback(prompt, max_output_tokens=4500)
        print(f"VALORANT 摘要使用模型：{model_used}")

        if _validate_valorant_summary(result):
            return result

        print("VALORANT 摘要格式／完整度不足，啟動一次完整重整...")
        repair_prompt = prompt + f"""

上一版輸出未通過完整度檢查。請重新完整閱讀【官方公告原文】，重新產生 7 個區塊。
特別確認：不要漏掉新系統、新模式、新武器、競技改動、重要特務／武器變更、玩家行為規則、主機版內容與重大錯誤修正。
上一版輸出只作為錯誤定位參考，不要複製其格式說明：
{(result or '')[:12000]}
"""
        repaired, repair_model = _summarize_with_fallback(repair_prompt, max_output_tokens=4500)
        print(f"VALORANT 重整摘要使用模型：{repair_model}")
        if _validate_valorant_summary(repaired):
            return repaired

        # 即使部分格式驗證不通過，只要有實際摘要，也交給 Discord；避免整篇公告因小格式差異直接丟掉。
        return repaired or result
    except Exception as e:
        print(f"VALORANT 摘要失敗：{e}")
        return None

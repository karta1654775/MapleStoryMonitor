"""VALORANT 官方版本更新公告的 Discord 懶人包摘要模組。"""

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

VALORANT_OUTPUT_TOKENS = 6500
MAX_SOURCE_CHARS = 100000


def build_valorant_prompt(title, body, url, english_weapon_reference=""):
    return f"""你是《特戰英豪》台灣繁體中文官方版本更新公告的 Discord 懶人包整理助手。

這是一篇 Riot Games 官方版本更新公告。你的任務是把超長 Patch Notes 整理成「完整、可快速掃讀、重要資訊不遺漏」的 Discord 懶人包。

【核心原則】
1. 只根據官方公告原文，不推測、不補充外部資料、不自行評價強弱或推薦。
2. 這是台灣繁中官方頁面：角色、技能、武器、地圖、模式、系統、數值與專有名詞，優先沿用原文。
3. 先完整讀取全文與原文的 TL;DR，再建立內部「內容覆蓋清單」。不要輸出覆蓋清單本身。
4. 不能因為懶人包而只留下 3～5 個大標題。凡是會實際影響玩家的新增、移除、規則變更、數值變更、競技規則、模式、特務、武器、玩家行為／防作弊、主機版、重大錯誤修正，都至少要整理一次。
5. 大量細小 Bug Fix 可以合併，但要保留「影響哪個系統／功能／特務／武器／模式」；不要寫成空泛的「修正多項問題」。
6. 重大數值務必保留，例如價格、傷害、倍率、射速、冷卻、回合數、隊伍人數、排名／分數規則、適用平台與限制條件。
7. 如果某個區塊真的沒有相關內容，就寫「- 本次沒有相關更新。」；不要捏造。
8. 不要把 Riot 網站導覽、分享按鈕、頁尾、作者資訊、固定 UI 文案當成公告內容。
9. 不要大段複製原文；以重新整理為主，但保留玩家需要的具體規則與數字。
10. 「懶人包」的意思是去掉冗長背景與逐條 Bug 列表，不是刪掉重要功能與規則。

【本篇公告】
標題：{title}
網址：{url}

【台灣繁中官方公告原文】
{body[:MAX_SOURCE_CHARS]}

【英文官方武器名稱對照（僅供專有名詞核對）】
{english_weapon_reference[:20000] if english_weapon_reference else "（未取得英文武器段落；仍以繁中官方公告為主要依據。）"}

【專有名詞格式要求】
- 如果「🔫 武器」區塊出現本版本「新增武器」，第一次提到時請使用「繁中官方名稱（Official English Name）」格式。
- 例如本版本的「守望者」第一次出現應寫成「守望者（Warden）」；之後同一則摘要可直接使用「守望者」。
- 英文名稱必須以英文官方武器段落為準；不要自行翻譯英文名稱。
- 既有武器只是數值調整時，不必每次都附英文名稱，除非原文有歧義。

【固定輸出格式】
只能輸出以下 7 個區塊，第一行必須是「📌 本次重點」，不要輸出其他開場或結語。

📌 本次重點
- 5～9 點。
- 只放本版本最值得先知道的重大內容：新系統、重大競技改動、新模式、新武器、主要特務變更、重大玩家行為／平台變更等。
- 每點要說清楚「新增／移除／怎麼改／玩家有什麼直接影響」，不能只寫「推出新功能」。

🖥️ 介面／系統
- 整理 Home／Lobby、用戶端、結算、收藏、進度、裝備、通知、設定等直接影響使用體驗的系統更新。
- 新增或重做的系統至少說明「做了什麼」與「玩家怎麼使用／受到什麼影響」。

🏆 競技／生涯
- 整理競技模式、牌階、Performance Score／ACS、MVP／Accolades、Rank Legacy、Career、排隊時進入靶場，以及其他競技規則。
- 所有會改變評分、牌階、排隊或生涯資料的規則，必須保留適用條件與重要數字。

🎮 模式／地圖
- 列出新模式、限時模式、模式下線、地圖輪替及地圖規則改動。
- 新模式至少交代：人數／隊伍、勝負或核心玩法、特殊規則、是否限時；原文有的才寫。

⚔️ 特務
- 列出所有真正有玩法、技能、數值或使用方式改動的特務。
- 每名特務至少 1 行；關鍵技能／數值要保留。
- 只有 Bug Fix 的特務不要冒充平衡改動，放到「🛠️ 其他更新」。

🔫 武器
- 列出所有新增或調整的武器。
- 新武器至少保留玩家最需要知道的價格、射擊模式、倍率、傷害、彈匣、射速、備彈等原文核心規格。
- 武器調整要說清楚是改了哪個數值或機制，不要只寫「武器平衡調整」。

🛠️ 其他更新
- 整理玩家行為／防作弊、語音系統、社交功能、主機版／平台限定、商店、已知問題，以及重大錯誤修正。
- 大量 Bug Fix 可以按系統分類合併，但與競技結果、遊戲體驗、特務、武器、模式、商店或重要功能有關的修正必須保留影響對象。

【完整度與長度】
- 目標 2500～5500 個中文字；大型版本可以超過，但不要為了湊字數重複。
- 每個區塊通常 2～8 個第一層條列；內容少的區塊可更少，但不能漏掉原文真正存在的重要事項。
- 不要把同一資訊在「本次重點」與其他區塊整段重複；本次重點只做總覽，其他區塊提供具體細節。
- 不要寫「大量優化」「多項調整」這種沒有資訊量的空話。

【輸出前自我檢查】
請先在心中確認以下項目都有處理，再輸出：
- 新系統／UI
- 競技／生涯規則
- 新模式／模式調整／地圖輪替
- 所有有實質改動的特務
- 所有新增／調整武器
- 玩家行為／防作弊／社交
- 主機版或平台限定變更
- 重大錯誤修正
- 重要日期、數字、限制條件
如果原文有上述項目而摘要沒有，先補上再輸出。
"""


def _section_bullets(summary, heading):
    if heading not in summary:
        return []
    part = summary.split(heading, 1)[1]
    later = [h for h in REQUIRED_SECTIONS if h != heading and h in part]
    if later:
        part = part[:min(part.index(h) for h in later)]
    return [line.strip() for line in part.splitlines() if line.strip().startswith("-")]


def _validate_valorant_summary(summary):
    if not summary:
        return False
    if not all(h in summary for h in REQUIRED_SECTIONS):
        return False
    if len(summary) < 1600:
        return False
    forbidden = [
        "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
        "上一版輸出", "工作筆記", "格式檢查結果", "覆蓋清單"
    ]
    if any(x in summary for x in forbidden):
        return False
    for heading in REQUIRED_SECTIONS:
        if not _section_bullets(summary, heading):
            return False
    # 本次重點至少 5 點，其餘區塊至少 1 點（可用「本次沒有相關更新」）
    if len(_section_bullets(summary, "📌 本次重點")) < 5:
        return False
    return True


def _repair_prompt(title, body, url, previous, english_weapon_reference=""):
    return f"""你是《特戰英豪》台灣繁中官方版本更新公告整理助手。
上一版摘要不完整或被截斷。請重新完整讀取官方原文，直接產生可貼到 Discord 的完整懶人包。

【公告】
標題：{title}
網址：{url}

【台灣繁中官方原文】
{body[:MAX_SOURCE_CHARS]}

【英文官方武器名稱對照】
{english_weapon_reference[:20000] if english_weapon_reference else "（未取得英文武器段落。）"}

【武器名稱格式】
- 本版本新增武器第一次出現時，用「繁中官方名稱（Official English Name）」格式，例如「守望者（Warden）」。
- 英文名稱只能依英文官方武器段落，不能自行翻譯。

【只輸出這 7 區】
📌 本次重點
- 5～9 點，只列重大內容與真正會影響玩家的改動。

🖥️ 介面／系統
- 有就具體整理；沒有就寫「- 本次沒有相關更新。」

🏆 競技／生涯
- 有就具體整理規則、數字與適用條件；沒有就寫「- 本次沒有相關更新。」

🎮 模式／地圖
- 新模式、模式下線、地圖輪替與重要規則都要保留；沒有就寫「- 本次沒有相關更新。」

⚔️ 特務
- 所有實質技能／數值／玩法改動都要保留；只有 Bug Fix 放到其他更新；沒有就寫「- 本次沒有相關更新。」

🔫 武器
- 所有新增／調整武器與重要規格都要保留；沒有就寫「- 本次沒有相關更新。」

🛠️ 其他更新
- 防作弊／玩家行為、語音／社交、主機版、重大錯誤修正等都要保留。

【硬性要求】
- 不可只輸出幾個重點後提前結束。
- 目標 2500～5500 個中文字，資訊很多時可以更長。
- 所有有實質影響的項目至少出現一次。
- 不要輸出分析過程、工作筆記、區塊編號或結語。
- 不要把上一版當成資料來源；上一版只用來判斷哪些地方可能被截斷。

上一版摘要（僅供找出遺漏）：
{previous[:12000]}
"""


def summarize_valorant(title, body, url, english_weapon_reference=""):
    if not _api_key():
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_valorant_prompt(title, body, url, english_weapon_reference)
    try:
        # VALORANT Patch Notes 通常遠長於其他公告；提高輸出上限，避免只完成前幾個重點就截斷。
        result, model_used = _summarize_with_fallback(prompt, max_output_tokens=VALORANT_OUTPUT_TOKENS)
        print(f"VALORANT 摘要使用模型：{model_used}")
        if _validate_valorant_summary(result):
            return result

        print("VALORANT 摘要不完整／格式不足，進行完整重整...")
        repaired, repair_model = _summarize_with_fallback(
            _repair_prompt(title, body, url, result or "", english_weapon_reference),
            max_output_tokens=VALORANT_OUTPUT_TOKENS,
        )
        print(f"VALORANT 重整摘要使用模型：{repair_model}")
        if _validate_valorant_summary(repaired):
            return repaired

        # 第二次重整仍不完整就再試一次，但不把明顯截斷的結果發到 Discord。
        print("VALORANT 第二次摘要仍未完整，進行最後一次完整生成...")
        final, final_model = _summarize_with_fallback(
            _repair_prompt(title, body, url, repaired or result or "", english_weapon_reference),
            max_output_tokens=VALORANT_OUTPUT_TOKENS,
        )
        print(f"VALORANT 最後摘要使用模型：{final_model}")
        if _validate_valorant_summary(final):
            return final

        print("VALORANT 無法產生完整懶人包，暫不發送，避免把截斷內容送到 Discord。")
        return None
    except Exception as e:
        print(f"VALORANT 摘要失敗：{e}")
        return None

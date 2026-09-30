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

# 這版刻意把目標縮到「完整但精簡」，避免模型把整篇 Patch Notes 寫得過長，
# 反而在最後幾個區塊提前停止。
VALORANT_OUTPUT_TOKENS = 4800
MAX_SOURCE_CHARS = 100000
MAX_ENGLISH_WEAPON_REFERENCE = 6000
MIN_SUMMARY_CHARS = 1100


def _english_ref(text):
    return (text or "")[:MAX_ENGLISH_WEAPON_REFERENCE]


def build_valorant_prompt(title, body, url, english_weapon_reference=""):
    return f"""你是《特戰英豪》台灣繁體中文官方版本更新公告的 Discord 懶人包整理助手。

請把下面這篇 Riot 官方 Patch Notes 整理成「完整但精簡」的 Discord 懶人包。
最重要的要求不是湊字數，而是：**七個區塊都一定要輸出，且所有真正會影響玩家的重要更新至少出現一次。**

【資料規則】
1. 只根據台灣繁中官方公告原文整理，不推測、不補充外部資料、不評論強弱。
2. 台灣繁中官方公告是主要來源；英文資料只用來核對「新增武器」的英文名稱。
3. 不要把網站導覽、分享按鈕、頁尾、作者資訊或固定 UI 文案當成公告內容。
4. 大量小型 Bug Fix 可以合併，但重大功能、系統、競技規則、模式、特務、武器、玩家行為、防作弊、主機版及重要修正不能省略。
5. 有價格、傷害、倍率、射速、冷卻、回合數、人數、分數、牌階、限制條件等重要數字時保留。
6. 「懶人包」代表刪掉冗長背景與重複敘述，不代表刪掉重要資訊。

【公告】
標題：{title}
網址：{url}

【台灣繁中官方公告原文】
{body[:MAX_SOURCE_CHARS]}

【英文官方武器名稱對照】
{_english_ref(english_weapon_reference) if english_weapon_reference else "（未取得；新增武器仍以繁中官方公告為準。）"}

【武器英文名稱】
如果「🔫 武器」有本版本新增武器，第一次出現時使用「繁中官方名稱（英文官方名稱）」。
例如：「守望者（Warden）」；英文名稱只能取自上面的英文官方資料，不要自行翻譯。
既有武器只有數值調整時，不必一直附英文名稱。

【固定輸出格式】
**只能輸出以下 7 個區塊，不能少任何一個；第一行必須是「📌 本次重點」。**

📌 本次重點
- 5～7 點，只列本版本最值得先知道的重大內容。

🖥️ 介面／系統
- 整理 UI、Home/Lobby、結算、進度、收藏、設定、通知及其他系統變更。
- 沒有相關更新就寫「- 本次沒有相關更新。」

🏆 競技／生涯
- 整理競技、牌階、評分、ACS／Performance Score、MVP／Accolades、Career、生涯資料、排隊規則等。
- 沒有相關更新就寫「- 本次沒有相關更新。」

🎮 模式／地圖
- 整理新模式、模式下線、地圖輪替及核心規則。
- 新模式只保留玩家需要知道的人數／隊伍、核心玩法、特殊規則、限時資訊。
- 沒有相關更新就寫「- 本次沒有相關更新。」

⚔️ 特務
- 列出所有真正有技能、玩法或數值改動的特務；關鍵數值要保留。
- 只有 Bug Fix 的特務放到「🛠️ 其他更新」。
- 沒有相關更新就寫「- 本次沒有相關更新。」

🔫 武器
- 列出所有新增／調整武器與玩家最需要知道的規格或改動。
- 新武器第一次出現附英文名稱。
- 沒有相關更新就寫「- 本次沒有相關更新。」

🛠️ 其他更新
- 整理玩家行為／防作弊、語音／社交、主機版／平台限定、商店及重大錯誤修正。
- 小型 Bug Fix 可依系統分類合併，但不能把重大修正寫成空泛一句。
- 沒有相關更新就寫「- 本次沒有相關更新。」

【長度與完整度】
- 目標約 1800～3500 個中文字；資訊很多時可以超過，但不要重複。
- 每區通常 1～6 個第一層條列；不要為了湊數新增無意義句子。
- 「📌 本次重點」是總覽，其他六區提供具體內容，不要整段重複。
- 不要只輸出前 3 個重點就結束。**七個標題與內容全部寫完才能結束。**
- 不要輸出分析過程、工作筆記、檢查結果或結語。
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
    # 標題允許少量格式差異，只要七個區塊都存在即可。
    if not all(h in summary for h in REQUIRED_SECTIONS):
        return False
    if len(summary) < MIN_SUMMARY_CHARS:
        return False
    forbidden = [
        "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
        "上一版輸出", "工作筆記", "格式檢查結果", "覆蓋清單"
    ]
    if any(x in summary for x in forbidden):
        return False

    # 每區至少有一個第一層條列；「本次沒有相關更新」也算有效。
    for heading in REQUIRED_SECTIONS:
        if not _section_bullets(summary, heading):
            return False

    # 本次重點至少 5 點；這仍能擋住「只產生前三項就結束」的半成品。
    if len(_section_bullets(summary, "📌 本次重點")) < 5:
        return False
    return True


def _repair_prompt(title, body, url, previous, english_weapon_reference=""):
    return f"""你是《特戰英豪》台灣繁中官方版本更新公告整理助手。

上一份摘要不完整。請**重新整理一次完整版本**，但這次要「精簡、一次寫完七個區塊」，不要寫很長的說明。

【公告】
標題：{title}
網址：{url}

【台灣繁中官方公告原文】
{body[:MAX_SOURCE_CHARS]}

【英文官方武器名稱對照】
{_english_ref(english_weapon_reference) if english_weapon_reference else "（未取得。）"}

【你必須輸出的七個區塊】
📌 本次重點
- 5～7 點重大內容。

🖥️ 介面／系統
- 有內容就整理；沒有就寫「- 本次沒有相關更新。」

🏆 競技／生涯
- 有內容就整理；沒有就寫「- 本次沒有相關更新。」

🎮 模式／地圖
- 有內容就整理；沒有就寫「- 本次沒有相關更新。」

⚔️ 特務
- 所有實質技能／玩法／數值改動都整理；只有 Bug Fix 放其他更新；沒有就寫「- 本次沒有相關更新。」

🔫 武器
- 新增／調整武器與重要規格都整理；新武器第一次出現附「繁中名稱（英文名稱）」；沒有就寫「- 本次沒有相關更新。」

🛠️ 其他更新
- 防作弊／玩家行為、語音／社交、主機版、重大錯誤修正等；沒有就寫「- 本次沒有相關更新。」

【硬性要求】
- 七個區塊一個都不能少。
- 不要只寫前三個重點。
- 不要輸出分析、工作筆記或結語。
- 目標約 1800～3500 個中文字，完整比冗長重要。
- 只根據官方公告原文，不新增原文沒有的資料。

上一版摘要（只用來判斷遺漏，不可當作資料來源）：
{previous[:9000]}
"""


def summarize_valorant(title, body, url, english_weapon_reference=""):
    if not _api_key():
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_valorant_prompt(title, body, url, english_weapon_reference)
    try:
        result, model_used = _summarize_with_fallback(
            prompt, max_output_tokens=VALORANT_OUTPUT_TOKENS
        )
        print(f"VALORANT 摘要使用模型：{model_used}")
        if _validate_valorant_summary(result):
            return result

        print("VALORANT 摘要不完整，改用較精簡的完整重整...")
        repaired, repair_model = _summarize_with_fallback(
            _repair_prompt(title, body, url, result or "", english_weapon_reference),
            max_output_tokens=VALORANT_OUTPUT_TOKENS,
        )
        print(f"VALORANT 重整摘要使用模型：{repair_model}")
        if _validate_valorant_summary(repaired):
            return repaired

        # 最後一次不再要求超長輸出，改成只保證七區 + 重要資訊，降低再次半截輸出的機率。
        print("VALORANT 重整後仍不完整，進行最後一次精簡完整生成...")
        compact_prompt = _repair_prompt(
            title, body, url,
            "請忽略上一版的格式，只需要重新輸出完整七區；每區控制在必要資訊即可。",
            english_weapon_reference,
        )
        final, final_model = _summarize_with_fallback(
            compact_prompt,
            max_output_tokens=4000,
        )
        print(f"VALORANT 最後摘要使用模型：{final_model}")
        if _validate_valorant_summary(final):
            return final

        print("VALORANT 無法產生完整懶人包，暫不發送，避免把截斷內容送到 Discord。")
        return None
    except Exception as e:
        print(f"VALORANT 摘要失敗：{e}")
        return None

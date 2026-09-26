import os
import requests
import time

DEFAULT_MODEL = "gemini-3.6-flash"
# 依序嘗試；主要模型忙碌/暫時不可用時自動切換。
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]


def _api_key():
    return os.getenv("GEMINI_API_KEY", "").strip()


def _model():
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _models():
    """主要模型 + fallback；可用 GEMINI_FALLBACK_MODELS 覆蓋預設值。"""
    primary = _model()
    raw = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
    fallback = [x.strip() for x in raw.split(",") if x.strip()] if raw else DEFAULT_FALLBACK_MODELS
    result = []
    for model in [primary, *fallback]:
        if model and model not in result:
            result.append(model)
    return result


def _request(model, prompt):
    key = _api_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2200},
    }

    last_error = None
    for attempt, wait_seconds in enumerate((0, 4), start=1):
        if wait_seconds:
            print(f"Gemini 暫時不可用，{wait_seconds} 秒後重試（第 {attempt}/2 次）...")
            time.sleep(wait_seconds)
        try:
            r = requests.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if r.ok:
                data = r.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception:
                    raise RuntimeError(f"Gemini 回傳格式異常：{str(data)[:1200]}")

            detail = r.text[:1200]
            last_error = RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
            # 服務忙碌/暫時不可用時重試；其他 HTTP 錯誤直接返回，讓上層決定是否換模型。
            if r.status_code not in (429, 500, 502, 503, 504):
                raise last_error
        except requests.RequestException as e:
            last_error = e

    raise last_error or RuntimeError("Gemini 請求失敗")


def _summarize_with_fallback(prompt):
    errors = []
    models = _models()
    for index, model in enumerate(models, start=1):
        if index > 1:
            print(f"Gemini 模型 {models[index-2]} 暫時不可用，切換到 {model}（{index}/{len(models)}）...")
        try:
            result = _request(model, prompt)
            if result:
                print(f"Gemini 使用模型：{model}")
                return result, model
        except Exception as e:
            errors.append(f"{model}: {e}")
            print(f"Gemini {model} 失敗：{e}")
    raise RuntimeError("；".join(errors))

def build_prompt(title, body, url, category="general"):
    category_name = {
        "general": "一般／活動公告",
        "shop": "商城公告",
        "maintenance": "維護／更新公告",
    }.get(category, "一般公告")

    category_rules = {
        "general": """【一般／活動公告特別要求】
- 活動名稱、活動期間、參加條件、任務方式、獎勵與限制，只要原文有就要保留。
- 如果是職業／系統相關公告，要列出實際調整內容，不要只寫「進行平衡調整」。
- 如果是合作活動，要列出合作角色、商品或活動內容中原文明確提到的重要項目。
- 不要建立「⚠️ 注意事項」區塊；重要限制、條件等內容直接放在相關的「重點整理」或「活動／獎勵／商品」條列中。""",
        "shop": """【商城公告特別要求】
- 必須盡量列出實際商品名稱、分類、價格／點數、販售期間、購買限制與機率規則。
- 不要把多個商品濃縮成「推出多項商品」；原文有列出的重要商品要分別整理。
- 若為機會中獎商品，必須保留「購買不代表必得特定商品」及原文提到的機率／規則。
- 不要建立「⚠️ 注意事項」區塊；重要購買限制與機率規則直接放在「重點整理」或「活動／獎勵／商品」中。""",
        "maintenance": """【維護／更新公告特別要求】
- 這類公告不可以只整理「幾點開機」。必須把維護後的主要更新內容完整列出。
- 「重點整理」至少 6 點；若原文只有較少的重大事項，則完整列出所有事項，不得為了湊數捏造內容。
- 原文若同時包含商城新品、活動、優惠、錯誤／異常處理、補償、系統／職業調整、道具調整、注意事項，都要分別整理。
- 維護公告中的商城、活動、優惠即使不是維護本身，也屬於玩家需要知道的本次更新內容，不能省略。
- 若有「原優惠異常 → 重新舉辦／補發」之類的處理，必須把原因、日期與官方處理方式寫清楚。""",
    }.get(category, "")

    return f"""你是「新楓之谷台灣官方公告」的 Discord 懶人包整理助手。
你的任務不是寫一段簡短摘要，而是把官方公告中「玩家實際需要知道的資訊」完整整理出來。
只根據官方公告原文整理，不推測、不補充外部資訊。

【公告資訊】
頻道類型：{category_name}
標題：{title}
網址：{url}

【官方公告原文】
{body[:40000]}

{category_rules}

【非常重要：輸出格式固定】
依公告類型輸出格式：

【一般／活動、商城公告】只輸出以下 3 個區塊，絕對不要輸出「⚠️ 注意事項」：

📌 重點整理
- 正常情況至少 5～10 點。
- 每點都必須是不同且具體的資訊。
- 這裡要先讓玩家快速掌握整篇公告的主要內容，不是只挑 2～3 個最醒目的事項。

🗓️ 時間／期限
- 列出原文中的所有重要日期、開始／結束時間、販售期間、領取期限、活動期間等。
- 如果原文有公告發布日期，也要列出。
- 如果原文沒有明確時間資訊，寫「• 原文未提供明確的時間／期限資訊。」

🎁 活動／獎勵／商品
- 把原文中所有實際的活動、任務、獎勵、掉落、商品、折扣、購買條件等整理出來。
- 保留重要道具名稱、數量、價格、次數、條件、期限與機率。
- 不要把多個商品或獎勵濃縮成「推出多項商品」。

【維護／更新公告】輸出以下 4 個區塊：

📌 重點整理
- 至少 6 點。
- 第一點優先交代「什麼時候完成維護／開機、目前是否全伺服器開放」。日期與時間只能使用原文實際出現的資訊；絕對不要自行產生或猜測日期。
- 接著依玩家最需要知道的更新內容整理：商城更新了什麼、活動／抽獎型活動有哪些、主要新增或調整了什麼、異常／優惠如何處理等。
- 黃金蘋果、閃亮彗星等抽獎型活動，不要只寫活動名稱；要列出原文明確提到的重要角色、機器人、圖騰、勳章、稱號、椅子、寵物或其他主要獎勵。
- 不要把整篇商城內容全部濃縮成一句；應依不同活動／商品類別分開整理。

🗓️ 時間／期限
- 列出維護時間、開機時間、活動／販售期間、重新舉辦日期及其他重要日期。

🎁 活動／獎勵／商品
- 具體列出原文中的商城、活動、抽獎型活動、獎勵與商品。
- 有價格、數量、次數、條件、機率等資訊必須保留。

⚠️ 注意事項
- 列出原文明確提到的限制、資格、機率、異常處理、道具回收、遊戲內為準及其他重要注意事項。

【完整度與一致性要求】
1. 「完整」比「極短」重要。不要因為公告類型而自動縮成只有 2～3 點。
2. 先完整讀取原文，再整理；絕對不要只根據標題猜內容。
3. 原文有多個商品／活動／獎勵／更新事項時，請分別列出，不要全部濃縮成一句。
4. 有數字、日期、時間、等級、次數、期限、道具名稱、商品名稱、價格、條件、機率時務必保留。
5. 同一資訊可以在不同區塊各自出現，但不要大量重複；「重點整理」負責總覽，「活動／獎勵／商品」負責具體細節。
6. 不要自行推測活動規則、價值、強弱、是否值得買或玩家應該怎麼選。
7. 不要加入官方公告沒有的資訊。
8. 不要大段複製原文，要重新整理成玩家容易掃讀的句子。
9. 目標總長約 700～1400 個中文字；資訊較少時可以較短，資訊很多時可以更長，但不要犧牲重要資訊。
10. 每個條列盡量 1～2 句；必要時可以使用第二層條列來列商品名稱或獎勵。
11. 不要輸出 Markdown 標題「#」，第一行必須是「📌 重點整理」。
12. 不要把「官方公告」「新楓之谷 maplestory 中文官方網站」「新楓之谷 maplestory 最團結的冒險！」等網站導覽／頁尾文字當成公告內容。
13. 日期、時間、商品名稱與活動內容只能引用你收到的官方公告原文；原文沒有的資訊一律不要補。
14. 不要在最後加「以上」「希望有幫助」等聊天式結語。
15. 輸出前自行檢查：是否有 4 個區塊？「重點整理」是否至少 5 點（維護／更新至少 6 點）？是否漏掉原文中的日期、時間、商品、活動、獎勵或重要注意事項？如果有，先補齊再輸出。

請嚴格按照上述固定格式輸出。"""


def _validate_summary(summary, category):
    """檢查 Gemini 是否真的產生完整的固定格式；不合格時交由上層重試。"""
    if not summary:
        return False
    required = ["📌 重點整理", "🗓️ 時間／期限", "🎁 活動／獎勵／商品"]
    if not all(x in summary for x in required):
        return False
    if category == "maintenance" and "⚠️ 注意事項" not in summary:
        return False
    if category in ("general", "shop") and "⚠️ 注意事項" in summary:
        return False

    # 只計算「重點整理」區塊的第一層條列，避免第二層商品清單把數量灌高。
    first = summary.split("📌 重點整理", 1)[1]
    first = first.split("🗓️ 時間／期限", 1)[0]
    bullets = [line for line in first.splitlines() if line.lstrip().startswith("- ")]
    minimum = 6 if category == "maintenance" else 5
    if len(bullets) < minimum:
        return False

    # 避免模型只回一小段就結束。
    if len(summary) < 500:
        return False

    # 只有例行維護／更新公告額外檢查：避免 Gemini 把內部工作筆記吐到 Discord。
    # 維護公告的內容量本來就可能很大，因此不要用過度嚴格的字數／條列數
    # 把正常摘要擋掉；只要四個區塊存在、重點有足夠條列，且沒有明顯的
    # 模型工作筆記，就視為可送出。
    if category == "maintenance":
        forbidden = ["二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
                     "上一版輸出", "重新整理整篇", "符合完整度要求",
                     "工作筆記", "格式檢查結果"]
        if any(x in summary for x in forbidden):
            return False
        # 維護公告允許較短的內容，但至少要有 4 個重點條列。
        if len(bullets) < 4 or len(summary) < 350:
            return False
    return True


def _repair_prompt(title, body, url, category, previous):
    # 維護公告重新整理時完全重新讀原文，不把上一版的工作筆記帶進提示。
    if category == "maintenance":
        return f"""你是新楓之谷台灣官方公告的 Discord 懶人包整理助手。

請重新閱讀下面的官方公告原文，直接產生一份可貼到 Discord 的完整懶人包。
只根據官方公告原文，不要輸出分析過程，也不要評論任何先前輸出。

【公告標題】
{title}

【官方公告原文】
{body[:40000]}

請嚴格使用以下格式，且只輸出這 4 個區塊：

📌 重點整理
- 至少 6 個第一層條列。
- 逐項整理本次例行維護後玩家需要知道的重要更新。
- 原文有商城新品、活動、優惠、異常處理、重新舉辦、修正改善、系統／職業／道具調整、已知事項等，必須分別整理；沒有的不要捏造。

🗓️ 時間／期限
- 列出所有重要日期、時間、開始／結束時間、販售期間、重新舉辦日期等。

🎁 活動／獎勵／商品
- 具體列出原文中的商城、活動、獎勵、商品與道具名稱。
- 有價格、數量、次數、條件、機率等資訊必須保留。

⚠️ 注意事項
- 列出原文明確提到的限制、資格、機率、異常處理、道具回收、遊戲內為準及其他重要注意事項。

重要：不要輸出 # 標題、區塊編號、二次檢查、格式檢查、無結語、上一版、工作筆記或任何開場／結語。不要把指令內容當成公告內容。不要把「官方公告」「新楓之谷 maplestory 中文官方網站」等網站 UI 當成公告內容。日期與時間只能引用原文。完整度優先，不要把多項更新濃縮成一兩句。
"""
    return build_prompt(title, body, url, category) + f"""

請重新閱讀完整官方公告後，直接輸出符合指定格式的完整懶人包。
上一版僅供判斷可能遺漏的內容，不要引用其中的工作筆記或格式說明。
上一版：
{previous[:8000]}
"""

def summarize(title, body, url, category="general"):
    key = _api_key()
    if not key:
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_prompt(title, body, url, category)
    try:
        result, _model_used = _summarize_with_fallback(prompt)

        # 維護／更新公告：不要因模型輸出的條列數、字數或小幅格式差異
        # 把實際摘要直接丟掉。先擋掉明顯的內部工作筆記，再正常送出。
        if category == "maintenance":
            if result and not any(x in result for x in [
                "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
                "上一版輸出", "重新整理整篇", "符合完整度要求",
                "工作筆記", "格式檢查結果"
            ]):
                if _validate_summary(result, category):
                    return result
                print("維護公告摘要格式略有差異，改用乾淨重整；不因格式檢查直接丟棄。")

            repair = _repair_prompt(title, body, url, category, "")
            repaired, _repair_model = _summarize_with_fallback(repair)
            if repaired and not any(x in repaired for x in [
                "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
                "上一版輸出", "重新整理整篇", "符合完整度要求",
                "工作筆記", "格式檢查結果"
            ]):
                if _validate_summary(repaired, category):
                    return repaired
                print("維護公告重整後格式略有差異，採用重整結果送出。")
                return repaired

            # 最後一次只有在真的沒有可用內容時才放棄。
            print("維護公告第一次／第二次整理含有內部格式文字，進行最後一次乾淨重寫...")
            final_result, _final_model = _summarize_with_fallback(_repair_prompt(title, body, url, category, ""))
            if final_result and not any(x in final_result for x in [
                "二次檢查", "區塊 1", "區塊 2", "區塊 3", "區塊 4",
                "上一版輸出", "重新整理整篇", "符合完整度要求",
                "工作筆記", "格式檢查結果"
            ]):
                print("維護公告採用最後一次乾淨摘要送出。")
                return final_result

            print("維護公告無法產生可用摘要，暫不送出。")
            return None

        # 一般／活動／商城公告維持原本的驗證與重整邏輯，不做變更。
        if _validate_summary(result, category):
            return result

        print("Gemini 摘要格式／完整度不足，啟動一次完整重整...")
        repair = _repair_prompt(title, body, url, category, result)
        repaired, _repair_model = _summarize_with_fallback(repair)
        if _validate_summary(repaired, category):
            return repaired

        print("Gemini 二次整理仍未完全通過格式檢查，使用二次結果送出。")
        return repaired or result
    except Exception as e:
        print(f"Gemini 摘要失敗：{e}")
        return None

def test_gemini():
    if not _api_key():
        print("Gemini：未設定 GEMINI_API_KEY")
        return False
    try:
        result, model_used = _summarize_with_fallback("請只回答：Gemini OK")
        print(f"Gemini 模型 {model_used} 測試回覆：{result}")
        return bool(result)
    except Exception as e:
        print(f"Gemini 測試失敗：{e}")
        return False

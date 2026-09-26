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
    for attempt, wait_seconds in enumerate((0, 4, 10), start=1):
        if wait_seconds:
            print(f"Gemini 暫時不可用，{wait_seconds} 秒後重試（第 {attempt}/3 次）...")
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
- 如果是合作活動，要列出合作角色、商品或活動內容中原文明確提到的重要項目。""",
        "shop": """【商城公告特別要求】
- 必須盡量列出實際商品名稱、分類、價格／點數、販售期間、購買限制與機率規則。
- 不要把多個商品濃縮成「推出多項商品」；原文有列出的重要商品要分別整理。
- 若為機會中獎商品，必須保留「購買不代表必得特定商品」及原文提到的機率／注意事項。""",
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
你必須固定輸出以下 4 個區塊，順序完全固定，不可以因為內容看起來簡單就省略區塊：

📌 重點整理
- 正常情況至少 5～10 點；維護／更新公告至少 6 點。
- 每點都必須是不同且具體的資訊。
- 這裡要先讓玩家快速掌握整篇公告的主要內容，不是只挑 2～3 個最醒目的事項。
- 如果原文有很多不同事項，應全部涵蓋，不要過度濃縮。

🗓️ 時間／期限
- 列出原文中的所有重要日期、開始／結束時間、維護時間、販售期間、領取期限、活動期間等。
- 如果原文有公告發布日期，也要列出。
- 如果原文沒有明確時間資訊，寫「• 原文未提供明確的時間／期限資訊。」

🎁 活動／獎勵／商品
- 把原文中所有實際的活動、任務、獎勵、掉落、商品、折扣、購買條件等整理出來。
- 保留重要道具名稱、數量、價格、次數、條件、期限。
- 商品公告要盡量列出具體商品名稱與分類；不要只說「推出多項商品」。
- 維護公告若包含商城／活動更新，也要在此列出。
- 如果原文沒有活動／獎勵／商品內容，寫「• 本公告未提供活動、獎勵或商品資訊。」

⚠️ 注意事項
- 列出原文明確提到的限制、資格、機率、購買規則、例外情況、道具回收、遊戲內為準等重要注意事項。
- 如果原文沒有特別注意事項，寫「• 原文未提供額外注意事項。」

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
12. 不要在最後加「以上」「希望有幫助」等聊天式結語。
13. 輸出前自行檢查：是否有 4 個區塊？「重點整理」是否至少 5 點（維護／更新至少 6 點）？是否漏掉原文中的日期、時間、商品、活動、獎勵或重要注意事項？如果有，先補齊再輸出。

請嚴格按照上述固定格式輸出。"""


def _validate_summary(summary, category):
    """檢查 Gemini 是否真的產生完整的固定格式；不合格時交由上層重試。"""
    if not summary:
        return False
    required = ["📌 重點整理", "🗓️ 時間／期限", "🎁 活動／獎勵／商品", "⚠️ 注意事項"]
    if not all(x in summary for x in required):
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
    return True


def _repair_prompt(title, body, url, category, previous):
    return build_prompt(title, body, url, category) + f"""

【二次檢查】
你上一版輸出沒有達到完整度要求。請重新整理整篇官方公告，不要只補一句話。
上一版如下：
{previous[:8000]}

請重新輸出完整的 4 個區塊，並特別確認「📌 重點整理」至少 {6 if category == 'maintenance' else 5} 個第一層條列；維護／更新公告尤其要把本次更新、商城、活動、優惠、異常處理等原文事項全部納入。
"""


def summarize(title, body, url, category="general"):
    key = _api_key()
    if not key:
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_prompt(title, body, url, category)
    try:
        result, _model_used = _summarize_with_fallback(prompt)
        if _validate_summary(result, category):
            return result

        print("Gemini 摘要格式／完整度不足，啟動一次完整重整...")
        repair = _repair_prompt(title, body, url, category, result)
        repaired, _repair_model = _summarize_with_fallback(repair)
        if _validate_summary(repaired, category):
            return repaired

        # 即使模型第二次仍不完全符合格式，也保留第二次較完整的結果，避免整篇公告因驗證失敗而不發送。
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

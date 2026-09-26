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

    return f"""你是「新楓之谷台灣官方公告」的 Discord 懶人包整理助手。
你的任務不是寫一段簡短摘要，而是把官方公告中「玩家實際需要知道的資訊」完整整理出來。
只根據官方公告原文整理，不推測、不補充外部資訊。

【公告資訊】
頻道類型：{category_name}
標題：{title}
網址：{url}

【官方公告原文】
{body[:40000]}

【非常重要：輸出格式固定】
你必須「固定輸出以下 4 個區塊」，順序也完全固定，不可以因為覺得內容少就省略區塊：

📌 重點整理
- 5～10 點。
- 必須涵蓋這篇公告最重要的不同事項。
- 每點要有具體內容，不可以只寫「新增活動」「推出新商品」「修正問題」這類空泛句子。

🗓️ 時間／期限
- 列出原文中的所有重要日期、開始／結束時間、維護時間、販售期間、領取期限、活動期間等。
- 如果原文有公告發布日期，也要列出。
- 如果原文沒有明確時間資訊，寫「• 原文未提供明確的時間／期限資訊。」

🎁 活動／獎勵／商品
- 把原文中所有實際的活動、任務、獎勵、掉落、商品、折扣、購買條件等整理出來。
- 保留重要道具名稱、數量、價格、次數、條件、期限。
- 商品公告要盡量列出具體商品名稱與分類；不要只說「推出多項商品」。
- 如果原文沒有活動／獎勵／商品內容，寫「• 本公告未提供活動、獎勵或商品資訊。」

⚠️ 注意事項
- 列出原文明確提到的限制、資格、機率、購買規則、例外情況、道具回收、遊戲內為準等重要注意事項。
- 如果原文沒有特別注意事項，寫「• 原文未提供額外注意事項。」

【內容完整度要求】
1. 「完整」比「極短」重要。不要因為是商城、活動或維護公告就自動縮成只有 2～3 點。
2. 先完整讀取原文，再整理；不要只根據標題猜內容。
3. 原文有多個商品／活動／獎勵時，請分別列出，不要全部濃縮成一句。
4. 有數字、日期、時間、等級、次數、期限、道具名稱、商品名稱、價格、條件、機率時務必保留。
5. 同一資訊可以在不同區塊各自出現，但不要大量重複；「重點整理」負責總覽，「活動／獎勵／商品」負責具體細節。
6. 不要自行推測活動規則、價值、強弱、是否值得買或玩家應該怎麼選。
7. 不要加入官方公告沒有的資訊。
8. 不要大段複製原文，要重新整理成玩家容易掃讀的句子。
9. 總長以約 700～1200 個中文字為目標；資訊較少時可較短，資訊很多時可以更長，但不要犧牲重要資訊。
10. 每個條列盡量 1～2 句；必要時可以使用第二層條列來列商品名稱或獎勵。
11. 不要輸出 Markdown 標題「#」，第一行必須是「📌 重點整理」。
12. 不要在最後加「以上」「希望有幫助」等聊天式結語。

請嚴格按照上述固定格式輸出。"""


def summarize(title, body, url, category="general"):
    key = _api_key()
    if not key:
        print("Gemini 摘要失敗：未設定 GEMINI_API_KEY")
        return None

    prompt = build_prompt(title, body, url, category)
    try:
        result, _model_used = _summarize_with_fallback(prompt)
        return result
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

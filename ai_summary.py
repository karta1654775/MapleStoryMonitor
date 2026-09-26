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
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1800},
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
        "maintenance": "維護公告",
    }.get(category, "一般公告")

    return f"""你是「新楓之谷台灣官方公告」的 Discord 懶人包整理助手。
只根據官方公告原文整理，不推測、不補充外部資訊。

公告頻道類型：{category_name}
標題：{title}
網址：{url}

原文：
{body[:40000]}

請整理成「資訊完整，但短而好讀」的繁體中文 Discord 懶人包。
目標是讓玩家不用讀完整公告，也能快速知道這篇公告的所有重要事項。
不要只挑 3～6 個大方向；請把原文中「實際會影響玩家」的不同事項都整理出來，但合併重複內容，避免流水帳。

請依內容需要使用以下區塊；沒有相關內容就整個省略：

📌 重點整理
- 約 5～10 點。
- 每點說清楚「做了什麼／發生什麼／玩家需要知道什麼」。
- 不要只寫「新增活動」「修正問題」這種空泛句子，要補上原文中的具體名稱或內容。

🗓️ 時間／期限
- 整理所有重要日期、開始／結束時間、維護時間、領取期限、活動期間等。
- 同一事項的時間不要重複寫。

🎁 活動／獎勵／商品
- 有活動、任務、獎勵、掉落、商品、折扣、購買條件等就整理。
- 保留重要道具名稱、數量、價格、次數、條件與期限。

⚠️ 注意事項
- 整理原文明確提到的限制、資格、注意事項、例外情況。

規則：
- 「完整」比「極短」重要，但不要把原文改寫成長篇文章。
- 總長控制在約 600～1000 個中文字；資訊少的公告可以更短，資訊多的公告可以接近上限。
- 每個重點盡量 1～2 句，避免超長段落。
- 有數字、日期、時間、等級、次數、期限、道具名稱、商品名稱、價格、條件時務必保留。
- 不要大段複製原文，要重新整理成玩家容易掃讀的句子。
- 不要自行推測活動規則、價值、強弱、是否值得買或玩家應該怎麼選。
- 不要加入官方公告沒有的資訊。
- 不要輸出 Markdown 標題「#」，直接從 📌 開始。
"""


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

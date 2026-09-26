import os
import requests

def get_webhook(category):
    names = {
        "general": "DISCORD_GENERAL_WEBHOOK",
        "shop": "DISCORD_SHOP_WEBHOOK",
        "maintenance": "DISCORD_MAINTENANCE_WEBHOOK",
        "warframe": "DISCORD_WARFRAME_WEBHOOK",
    }
    return os.getenv(names.get(category, ""), "").strip()



DISCORD_CONTENT_LIMIT = 2000


def _split_text(text, limit):
    """把長文字依換行切成多塊，每塊長度不超過 limit。
    盡量在整行的邊界切開，避免把一個條列項目從中間切斷。
    """
    if len(text) <= limit:
        return [text]

    parts = []
    current = ""
    for line in text.split("\n"):
        # 單一行本身就超過 limit 的極端狀況，直接強制切割該行。
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]

        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate

    if current:
        parts.append(current)
    return parts


def _post_to_discord(webhook, content):
    try:
        r = requests.post(webhook, json={"content": content}, timeout=30)
        if r.status_code not in (200, 204):
            print(f"Discord 發送失敗：HTTP {r.status_code} {r.text[:500]}")
            return False
        return True
    except Exception as e:
        print(f"Discord 發送失敗：{e}")
        return False


def send_discord(category, title, summary, url):
    webhook = get_webhook(category)
    if not webhook:
        print(f"未設定 {category} Discord Webhook")
        return False

    labels = {
        "general": "📢 一般公告",
        "shop": "🛒 商城公告",
        "maintenance": "🔧 維護公告",
        "warframe": "🎮 Warframe 更新日誌",
    }
    label = labels.get(category, "📢 新公告")

    header = f"{label}\n\n**{title}**\n\n"
    footer = f"\n\n🔗 [官方公告]({url})"

    # 保留給 header／footer／分段標示的空間，避免切完之後單則又超過 Discord 上限。
    reserve = len(header) + len(footer) + 20
    body_limit = max(DISCORD_CONTENT_LIMIT - reserve, 500)

    body_parts = _split_text(summary, body_limit)

    # 內容夠短：維持原本單則訊息的行為。
    if len(body_parts) == 1:
        content = header + body_parts[0] + footer
        ok = _post_to_discord(webhook, content)
        if ok:
            print(f"Discord 發送成功：{category}")
        return ok

    # 內容過長：分成多則依序發送，而不是截斷內容。
    total = len(body_parts)
    all_ok = True
    for i, part in enumerate(body_parts, start=1):
        if i == 1:
            content = header + f"（{i}/{total}）\n" + part
        elif i == total:
            content = f"（{i}/{total}）\n" + part + footer
        else:
            content = f"（{i}/{total}）\n" + part

        ok = _post_to_discord(webhook, content)
        if not ok:
            print(f"Discord 發送失敗（第 {i}/{total} 則）")
            all_ok = False

    if all_ok:
        print(f"Discord 發送成功：{category}（共 {total} 則訊息）")
    return all_ok


def test_webhooks():
    results = {}
    for category in ("general", "shop", "maintenance"):
        webhook = get_webhook(category)
        if not webhook:
            results[category] = False
            continue
        try:
            r = requests.get(webhook, timeout=15)
            results[category] = r.status_code == 200
            if r.status_code != 200:
                print(f"{category} Webhook 測試 HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"{category} Webhook 測試失敗：{e}")
            results[category] = False
    return results

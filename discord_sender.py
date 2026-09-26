import os
import requests

def get_webhook(category):
    names = {
        "general": "DISCORD_GENERAL_WEBHOOK",
        "shop": "DISCORD_SHOP_WEBHOOK",
        "maintenance": "DISCORD_MAINTENANCE_WEBHOOK",
    }
    return os.getenv(names.get(category, ""), "").strip()



def send_discord(category, title, summary, url):
    webhook = get_webhook(category)
    if not webhook:
        print(f"未設定 {category} Discord Webhook")
        return False

    labels = {
        "general": "📢 一般公告",
        "shop": "🛒 商城公告",
        "maintenance": "🔧 維護公告",
    }
    label = labels.get(category, "📢 新楓之谷公告")
    content = f"{label}\n\n**{title}**\n\n{summary}\n\n🔗 [官方公告]({url})"
    if len(content) > 1950:
        content = content[:1940] + "\n\n…（內容過長已截斷）"

    try:
        r = requests.post(webhook, json={"content": content}, timeout=30)
        if r.status_code not in (200, 204):
            print(f"Discord 發送失敗：HTTP {r.status_code} {r.text[:500]}")
            return False
        print(f"Discord 發送成功：{category}")
        return True
    except Exception as e:
        print(f"Discord 發送失敗：{e}")
        return False


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


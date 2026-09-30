import os
import re
import requests


def get_webhook(category):
    names = {
        "general": "DISCORD_GENERAL_WEBHOOK",
        "shop": "DISCORD_SHOP_WEBHOOK",
        "maintenance": "DISCORD_MAINTENANCE_WEBHOOK",
        "warframe": "DISCORD_WARFRAME_WEBHOOK",
        "lol": "DISCORD_LOL_WEBHOOK",
        "valorant": "DISCORD_VALORANT_WEBHOOK",
    }
    return os.getenv(names.get(category, ""), "").strip()


DISCORD_CONTENT_LIMIT = 2000


def _hard_split(line, limit):
    """單行過長時盡量在中文標點切開，避免 Discord 訊息從一句話中間硬斷。"""
    parts = []
    while len(line) > limit:
        cut = limit
        # 優先在標點後切，最多回看 120 字。
        punct = "。！？；，、：)]}〉》」』）】"
        lower = max(0, limit - 120)
        for i in range(limit, lower, -1):
            if line[i - 1] in punct:
                cut = i
                break
        parts.append(line[:cut])
        line = line[cut:]
    if line:
        parts.append(line)
    return parts


def _split_text(text, limit):
    if len(text) <= limit:
        return [text]

    parts = []
    current = ""
    for line in text.splitlines():
        if len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.extend(_hard_split(line, limit))
            continue

        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            parts.append(current)
        current = line

    if current:
        parts.append(current)
    return parts


def _post_to_discord(webhook, content, embeds=None):
    payload = {"content": content}
    if embeds:
        payload["embeds"] = embeds
    try:
        r = requests.post(webhook, json=payload, timeout=30)
        if r.status_code not in (200, 204):
            print(f"Discord 發送失敗：HTTP {r.status_code} {r.text[:500]}")
            return False
        return True
    except Exception as e:
        print(f"Discord 發送失敗：{e}")
        return False


def send_discord(category, title, summary, url, image_url=None):
    webhook = get_webhook(category)
    if not webhook:
        print(f"未設定 {category} Discord Webhook")
        return False

    labels = {
        "general": "📢 一般公告",
        "shop": "🛒 商城公告",
        "maintenance": "🔧 維護公告",
        "warframe": "🎮 Warframe 更新日誌",
        "lol": "⚔️ 英雄聯盟版更公告",
        "valorant": "🎯 特戰英豪版本更新",
    }
    label = labels.get(category, "📢 新公告")

    header = f"{label}\n\n**{title}**\n\n"
    footer = f"\n\n🔗 [官方公告]({url})"
    reserve = len(header) + len(footer) + 40
    body_limit = max(DISCORD_CONTENT_LIMIT - reserve, 500)

    body_parts = _split_text(summary, body_limit)
    first_embeds = [{"image": {"url": image_url}}] if image_url else None

    if len(body_parts) == 1:
        return _post_to_discord(
            webhook,
            header + body_parts[0] + footer,
            embeds=first_embeds,
        )

    total = len(body_parts)
    all_ok = True
    for i, part in enumerate(body_parts, start=1):
        if i == 1:
            content = header + f"（{i}/{total}）\n" + part
        elif i == total:
            content = f"（{i}/{total}）\n" + part + footer
        else:
            content = f"（{i}/{total}）\n" + part

        ok = _post_to_discord(
            webhook,
            content,
            embeds=first_embeds if i == 1 else None,
        )
        if not ok:
            print(f"Discord 發送失敗（第 {i}/{total} 則）")
            all_ok = False

    return all_ok


def test_webhooks():
    results = {}
    for category in ("general", "shop", "maintenance", "warframe", "lol", "valorant"):
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

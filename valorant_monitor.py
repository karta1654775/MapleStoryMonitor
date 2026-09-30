import os
import sys
import json
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from valorant_summary import summarize_valorant
from discord_sender import send_discord

BASE_URL = "https://playvalorant.com"
LISTING_URL = os.getenv("VALORANT_LISTING_URL") or "https://playvalorant.com/zh-tw/news/tags/patch-notes/"
SEEN_FILE = "valorant_seen.json"
MAX_NEW_PER_RUN = int(os.getenv("VALORANT_MAX_NEW_PER_RUN", "1"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

ARTICLE_CONTENT_SELECTOR = '[data-testid="rich-text-html"]'


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def _normalize_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href.split("?")[0].rstrip("/")
    return (BASE_URL + href).split("?")[0].rstrip("/")


def get_patch_list():
    """抓 Riot 台灣繁中「更新公告」列表，只處理 patch notes。"""
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_urls = set()

    for a in soup.select('a[data-testid$="card-component"][href]'):
        href = a.get("href", "")
        if "/news/game-updates/" not in href or "patch-notes" not in href:
            continue
        url = _normalize_url(href)
        if not url or url in seen_urls:
            continue
        title = (a.get("aria-label") or a.get_text(" ", strip=True) or "").strip()
        if not title:
            continue
        seen_urls.add(url)
        items.append({"title": title, "url": url})

    if not items:
        print("主要抓法沒有抓到版本公告，改用備援連結比對。")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/game-updates/" not in href or "patch-notes" not in href:
                continue
            url = _normalize_url(href)
            if not url or url in seen_urls:
                continue
            title = (a.get("aria-label") or a.get_text(" ", strip=True) or "").strip()
            if not title:
                continue
            seen_urls.add(url)
            items.append({"title": title, "url": url})

    print(f"版本更新列表抓到 {len(items)} 篇。")
    return items


def extract_patch_body(url, label="官方版本更新"):
    """抓 Riot 官方版本更新全文。"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    candidates = soup.select(ARTICLE_CONTENT_SELECTOR)
    if not candidates:
        print(f"  找不到 {label} rich-text-html 正文容器。")
        return ""

    # Riot 頁面可能在相關文章也出現相同 data-testid；取文字量最大的正文容器。
    best = max(candidates, key=lambda el: len(el.get_text("\n", strip=True)))

    # 移除可能混入正文的腳本／樣式／分享元件文字。
    for tag in best.select("script, style, noscript"):
        tag.decompose()

    text = best.get_text("\n", strip=True)
    print(f"  抓到{label}正文：{len(text)} 字元。")
    return text


def _english_url(url):
    """將 Riot 台灣繁中公告 URL 轉成英文官方同篇公告 URL。"""
    return url.replace("/zh-tw/", "/en-us/", 1)


def _extract_weapon_reference(english_body):
    """只保留英文公告中的武器段落，供 AI 核對新增武器英文名稱。"""
    if not english_body:
        return ""
    lines = english_body.splitlines()
    start = None
    for i, line in enumerate(lines):
        normalized = " ".join(line.strip().upper().split())
        if normalized in {"WEAPONS UPDATES", "WEAPON UPDATES"} or normalized.endswith("WEAPONS UPDATES"):
            start = i
            break
    if start is None:
        return ""

    end = len(lines)
    for i in range(start + 1, len(lines)):
        normalized = " ".join(lines[i].strip().upper().split())
        if normalized.startswith("# ") and normalized not in {"# WEAPONS UPDATES", "# WEAPON UPDATES"}:
            end = i
            break
        if normalized in {"AGENT UPDATES", "MAP UPDATES", "COMPETITIVE UPDATES", "BUG FIXES", "GENERAL UPDATES", "PLAYER BEHAVIOR UPDATES", "PROGRESSION UPDATES", "SOCIAL UPDATES", "PERFORMANCE UPDATES", "ESPORTS FEATURES"}:
            end = i
            break
    return "\n".join(lines[start:end]).strip()[:20000]


def process_one(title, url, mark_seen=True, seen=None):
    print(f"  開啟：{url}")
    body = extract_patch_body(url, label="繁中官方")
    if not body:
        print("  正文抓取為空，跳過，不標記已讀。")
        return False

    english_weapon_reference = ""
    en_url = _english_url(url)
    try:
        english_body = extract_patch_body(en_url, label="英文官方")
        english_weapon_reference = _extract_weapon_reference(english_body)
        if english_weapon_reference:
            print(f"  已取得英文武器名稱對照：{len(english_weapon_reference)} 字元。")
        else:
            print("  英文官方頁未找到武器段落，改以繁中公告處理。")
    except Exception as e:
        print(f"  英文官方頁讀取失敗，仍使用繁中公告：{e}")

    print("  呼叫 Gemini 產生 VALORANT 懶人包...")
    summary = summarize_valorant(title, body, url, english_weapon_reference=english_weapon_reference)
    if not summary:
        print("  Gemini 沒有產生摘要，跳過，不標記已讀。")
        return False

    if not send_discord("valorant", title, summary, url):
        print("  Discord 發送失敗，跳過，不標記已讀。")
        return False

    if mark_seen and seen is not None:
        seen.add(url)

    print(f"  已發送：{title}")
    return True


def run_once():
    seen = load_seen()
    items = get_patch_list()
    new_items = [item for item in items if item["url"] not in seen]

    if not new_items:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 沒有新的 VALORANT 版本公告。")
        return

    # 新到舊列表反轉後依舊版→新版處理，避免漏掉連續發布的版本。
    new_items = list(reversed(new_items))
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 發現 {len(new_items)} 篇新版本公告。")

    processed = 0
    for item in new_items:
        if processed >= MAX_NEW_PER_RUN:
            print(f"達到單輪上限 {MAX_NEW_PER_RUN} 篇，本輪結束。")
            break
        try:
            if process_one(item["title"], item["url"], mark_seen=True, seen=seen):
                processed += 1
                save_seen(seen)
        except Exception as e:
            print(f"  處理失敗：{item['url']}\n  原因：{e}")

    print(f"本輪成功發送 {processed} 篇；seen 共 {len(seen)} 筆。")


def run_test_latest():
    """強制測試目前最新一篇，不修改 seen。"""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] === VALORANT 最新一篇測試（不修改 seen）===")
    items = get_patch_list()
    if not items:
        print("列表頁沒有抓到公告，流程中止。")
        return
    item = items[0]
    print(f"標題：{item['title']}\n網址：{item['url']}")
    process_one(item["title"], item["url"], mark_seen=False, seen=None)


def run_force_url(url):
    """強制測試指定官方公告 URL，不修改 seen。"""
    url = _normalize_url(url)
    title = url.rstrip("/").split("/")[-1]
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] === VALORANT 指定 URL 測試 ===")
    print(f"網址：{url}")

    # 優先從頁面 title 抓正式標題，抓不到則使用 URL 最後一段。
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        if h1 and h1.get_text(" ", strip=True):
            title = h1.get_text(" ", strip=True)
    except Exception as e:
        print(f"指定頁面標題讀取失敗：{e}")

    process_one(title, url, mark_seen=False, seen=None)


def main():
    if "--test-latest" in sys.argv:
        run_test_latest()
        return

    if "--force-url" in sys.argv:
        try:
            url = sys.argv[sys.argv.index("--force-url") + 1]
        except (ValueError, IndexError):
            print("用法：python valorant_monitor.py --force-url <官方公告URL>")
            return
        run_force_url(url)
        return

    if "--scan-once" in sys.argv:
        run_once()
        return

    print("請使用：")
    print("  python valorant_monitor.py --scan-once")
    print("  python valorant_monitor.py --test-latest")
    print("  python valorant_monitor.py --force-url <官方公告URL>")


if __name__ == "__main__":
    main()

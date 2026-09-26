import os
import sys
import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import feedparser
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from warframe_summary import summarize_warframe
from discord_sender import send_discord

# 你原本在用的 RSS 網址；如果跟這裡的預設值不一樣，請用環境變數 WARFRAME_RSS_URL 覆蓋，
# 不要直接改這個預設值，避免之後又要在程式碼裡找。
RSS_URL = os.getenv(
    "WARFRAME_RSS_URL",
    "https://forums.warframe.com/forum/1563-%E6%9B%B4%E6%96%B0%E6%97%A5%E8%AA%8C%EF%BC%88pc%EF%BC%89/.xml",
)

SEEN_FILE = "warframe_seen.json"
MAX_NEW_PER_RUN = int(os.getenv("WARFRAME_MAX_NEW_PER_RUN", "5"))

# 確認過的貼文內容容器（Invision Community 論壇標準結構）。
POST_CONTENT_SELECTOR = '[data-role="commentContent"]'


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def get_new_topics(seen):
    """讀 RSS，回傳還沒處理過的新主題（標題＋連結）。

    以連結（entry.link）當作去重的 key，跟 RSS 服務本身的判斷邏輯無關，
    所以就算你原本那個 RSS-to-Discord 服務也在跑，兩邊不會互相干擾。
    """
    feed = feedparser.parse(RSS_URL)
    if getattr(feed, "bozo", False):
        print(f"RSS 解析警告：{feed.bozo_exception}")

    items = []
    for entry in feed.entries:
        link = str(entry.get("link", "")).strip()
        title = str(entry.get("title", "")).strip()
        if link and link not in seen:
            items.append({"title": title, "url": link})

    # RSS 通常是新到舊排序；這裡反轉成舊到新，讓比較早的更新先發送。
    return list(reversed(items))


def launch_browser(playwright):
    return playwright.chromium.launch(headless=True)


def extract_post_body(page, url):
    """開啟主題頁面，抓「第一則貼文」的純文字內容。"""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(800)

    try:
        locator = page.locator(POST_CONTENT_SELECTOR).first
        text = locator.inner_text(timeout=5000).strip()
        return text
    except Exception as e:
        print(f"  抓取內文失敗：{e}")
        return ""


def run_once():
    seen = load_seen()
    new_items = get_new_topics(seen)

    if not new_items:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 沒有新的更新日誌。")
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 發現 {len(new_items)} 篇新更新日誌。")

    processed = 0
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        try:
            for item in new_items:
                title, url = item["title"], item["url"]
                print(f"處理：{title}")

                try:
                    body = extract_post_body(page, url)
                    if not body:
                        print("  內文抓取為空，跳過，不標記已讀（下次會重試）。")
                        continue

                    summary = summarize_warframe(title, body, url)
                    if not summary:
                        print("  Gemini 沒有產生摘要，跳過，不標記已讀。")
                        continue

                    if not send_discord("warframe", title, summary, url):
                        print("  Discord 發送失敗，跳過，不標記已讀。")
                        continue

                    seen.add(url)
                    processed += 1
                    print(f"  已發送：{title}")

                    if processed >= MAX_NEW_PER_RUN:
                        print(f"已達單輪上限 {MAX_NEW_PER_RUN} 篇，本輪提前結束。")
                        break

                except Exception as e:
                    print(f"  處理失敗：{url}\n  原因：{e}")
        finally:
            browser.close()

    save_seen(seen)
    print(f"本輪成功發送 {processed} 篇。目前 seen：約 {len(seen)} 篇。")


def main():
    if "--scan-once" in sys.argv:
        run_once()
        return

    print("請使用 --scan-once 執行單輪掃描（本程式不支援常駐迴圈模式）。")
    print("例如：python warframe_monitor.py --scan-once")


if __name__ == "__main__":
    main()

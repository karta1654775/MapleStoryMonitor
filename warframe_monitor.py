import os
import sys
import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import feedparser
from bs4 import BeautifulSoup

from warframe_summary import summarize_warframe
from discord_sender import send_discord

# 你原本在用的 RSS 網址；如果跟這裡的預設值不一樣，請用環境變數 WARFRAME_RSS_URL 覆蓋。
# 注意：GitHub Actions 的 vars.WARFRAME_RSS_URL 若未設定會是空字串，
# os.getenv 在空字串時不會回傳預設值，所以用 .strip() or 預設值來處理。
RSS_URL = os.getenv("WARFRAME_RSS_URL", "").strip() or (
    "https://forums.warframe.com/forum/1563-"
    "%E6%9B%B4%E6%96%B0%E6%97%A5%E8%AA%8C%EF%BC%88pc%EF%BC%89/.xml"
)

SEEN_FILE = "warframe_seen.json"
MAX_NEW_PER_RUN = int(os.getenv("WARFRAME_MAX_NEW_PER_RUN", "5"))


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def clean_html(html_text):
    """將 RSS description 中的 HTML 轉為純文字，保留段落與條列結構。"""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")

    # 移除 style、script、meta 等非內容標籤
    for tag in soup(["style", "script", "meta"]):
        tag.decompose()

    # 將 <br> 轉為換行
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # 保留超連結的 URL（Warframe 更新日誌常包含回饋論壇連結）
    for a in soup.find_all("a", href=True):
        text = a.get_text().strip()
        if text:
            a.replace_with(f"{text} ({a['href']})")
        else:
            a.decompose()

    # 條列項目前面加上 "- "
    for li in soup.find_all("li"):
        li.insert_before("\n- ")

    # 段落標題前後加換行
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    text = soup.get_text()

    # 清理多餘的空行
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


def get_new_topics(seen):
    """讀 RSS，回傳還沒處理過的新主題（標題＋連結＋內容）。

    RSS description 欄位已包含完整貼文 HTML 內容，
    直接從 RSS 抓取，不需要再用 Playwright 開啟論壇頁面
    （Warframe 論壇有 Cloudflare 保護，headless browser 會被擋）。
    """
    feed = feedparser.parse(RSS_URL)
    if getattr(feed, "bozo", False):
        print(f"RSS 解析警告：{feed.bozo_exception}")

    items = []
    for entry in feed.entries:
        link = str(entry.get("link", "")).strip()
        title = str(entry.get("title", "")).strip()
        if link and link not in seen:
            raw_content = str(entry.get("description", "") or entry.get("summary", "") or "")
            content = clean_html(raw_content)
            items.append({"title": title, "url": link, "content": content})

    # RSS 通常是新到舊排序；這裡反轉成舊到新，讓比較早的更新先發送。
    return list(reversed(items))


def get_latest_topic():
    """取得 RSS 中最新的一篇主題（用於 simulate 模式）。"""
    feed = feedparser.parse(RSS_URL)
    if getattr(feed, "bozo", False):
        print(f"RSS 解析警告：{feed.bozo_exception}")

    if not feed.entries:
        return None

    entry = feed.entries[0]  # RSS 新到舊，第一筆就是最新
    link = str(entry.get("link", "")).strip()
    title = str(entry.get("title", "")).strip()
    raw_content = str(entry.get("description", "") or entry.get("summary", "") or "")
    content = clean_html(raw_content)

    return {"title": title, "url": link, "content": content}


def run_once():
    seen = load_seen()
    new_items = get_new_topics(seen)

    if not new_items:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 沒有新的更新日誌。")
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 發現 {len(new_items)} 篇新更新日誌。")

    processed = 0
    for item in new_items:
        title, url = item["title"], item["url"]
        body = item.get("content", "")
        print(f"處理：{title}")

        try:
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

    save_seen(seen)
    print(f"本輪成功發送 {processed} 篇。目前 seen：約 {len(seen)} 篇。")


def run_simulate():
    """抓 RSS 中最新的一篇更新日誌，整理後發送到 Discord。

    不讀取 seen，不修改 seen.json。
    適合第一次測試 Discord、Gemini 與 Secrets 是否正常。
    """
    print("\n=== 模擬模式：抓取最新一篇更新日誌（不修改 seen.json） ===")

    item = get_latest_topic()
    if not item:
        print("找不到任何更新日誌。")
        return

    title, url, body = item["title"], item["url"], item["content"]
    print(f"[SIMULATE] {title}")
    print(f"  網址：{url}")

    if not body:
        print("  內文抓取為空，無法測試。")
        return

    try:
        summary = summarize_warframe(title, body, url)
        if not summary:
            print("  Gemini 沒有產生摘要。")
            return

        if send_discord("warframe", title, summary, url):
            print("  模擬發送成功。")
        else:
            print("  模擬發送失敗。")
    except Exception as e:
        print(f"  模擬發送失敗：{e}")

    print("seen.json：未修改。")


def main():
    if "--scan-once" in sys.argv:
        run_once()
        return

    if "--simulate" in sys.argv:
        run_simulate()
        return

    print("請使用 --scan-once 執行單輪掃描，或 --simulate 測試最新一篇。")
    print("例如：python warframe_monitor.py --scan-once")
    print("例如：python warframe_monitor.py --simulate")


if __name__ == "__main__":
    main()

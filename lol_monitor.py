import os
import re
import sys
import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import requests
from bs4 import BeautifulSoup

from lol_summary import summarize_lol
from discord_sender import send_discord

BASE_URL = "https://www.leagueoflegends.com"
LISTING_URL = os.getenv("LOL_LISTING_URL") or "https://www.leagueoflegends.com/zh-tw/news/tags/patch-notes/"

SEEN_FILE = "lol_seen.json"
MAX_NEW_PER_RUN = int(os.getenv("LOL_MAX_NEW_PER_RUN", "3"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}

# 確認過的內文容器（見 2026-09-26 對話中使用者貼的原始碼）。
ARTICLE_CONTENT_SELECTOR = '[data-testid="rich-text-html"]'

# 版本重點圖（「版本概要」小節那張大圖）用檔名裡的寬度篩選，
# 排除作者頭像等小圖示；1920 寬的圖片一定會過這個門檻，
# 頭像類的圖目前看到的最大也才 300 寬，兩者差距夠大，用寬度篩選足夠可靠。
PATCH_IMAGE_MIN_WIDTH = 1200


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
    """抓列表頁，回傳目前頁面上所有版更公告的標題＋連結。

    列表頁本身已經用 /tags/patch-notes/ 篩過，所以不用另外判斷分類。
    卡片元件可能有兩種樣式（最新一篇是 featured 卡，其餘可能是一般卡），
    這裡用寬鬆的 data-testid 結尾比對 + 連結路徑當雙重保險，避免漏抓。
    """
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_urls = set()

    # 主要抓法：data-testid 以 "card-component" 結尾的卡片連結。
    for a in soup.select('a[data-testid$="card-component"][href]'):
        href = a.get("href", "")
        if "/news/game-updates/" not in href:
            continue
        url = _normalize_url(href)
        if not url or url in seen_urls:
            continue
        title = (a.get("aria-label") or a.get_text(strip=True) or "").strip()
        if not title:
            continue
        seen_urls.add(url)
        items.append({"title": title, "url": url})

    # 備援抓法：如果上面完全沒抓到（代表網站改版、testid 變了），
    # 退而求其次，抓所有指向 /news/game-updates/ 且路徑含 patch 的連結。
    if not items:
        print("主要抓法沒抓到任何卡片，改用備援連結比對邏輯。")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/game-updates/" not in href or "patch" not in href:
                continue
            url = _normalize_url(href)
            if not url or url in seen_urls:
                continue
            title = (a.get("aria-label") or a.get_text(strip=True) or "").strip()
            if not title:
                continue
            seen_urls.add(url)
            items.append({"title": title, "url": url})

    print(f"列表頁共抓到 {len(items)} 篇版更公告。")
    return items


def get_new_patches(seen):
    items = get_patch_list()
    new_items = [item for item in items if item["url"] not in seen]
    # 列表頁通常新到舊排序；反轉成舊到新，讓比較早的版本先發送。
    return list(reversed(new_items))


def find_patch_chart_image(content_element, min_width=PATCH_IMAGE_MIN_WIDTH):
    """在內文區塊裡找出版本重點圖（「版本概要」小節那張大圖）。

    用檔名裡的寬度篩選：這類 CMS 圖檔名固定是 xxx-寬x高.副檔名，
    作者頭像等小圖示目前看到最大只有 300 寬，版本重點圖是 1920 寬，
    取內文中第一張過門檻的大圖，準確落在版本重點圖上，
    不會被後面「新增造型」小節同樣是大圖的展示圖搶走（因為那些排在更後面）。
    找不到就回傳 None，不當作錯誤處理。
    """
    for img in content_element.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        m = re.search(r"-(\d+)x(\d+)\.\w+", src)
        if not m:
            continue
        width = int(m.group(1))
        if width >= min_width:
            return src
    return None


def extract_patch_body(url):
    """開啟版更公告頁面，回傳 (正文純文字, 版本重點圖網址或 None)。

    同一個 data-testid="rich-text-html" 也會出現在頁面下方「相關文章」
    卡片的簡短描述裡，所以這裡不是直接抓第一個符合的元素，
    而是抓「文字量最長」的那一個，實務上正文一定遠比相關文章的摘要長。
    """
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    candidates = soup.select(ARTICLE_CONTENT_SELECTOR)
    if not candidates:
        print("  找不到任何符合 rich-text-html 的區塊。")
        return "", None

    best = max(candidates, key=lambda el: len(el.get_text(strip=True)))
    text = best.get_text("\n", strip=True)
    image_url = find_patch_chart_image(best)

    print(f"  抓到內文長度：{len(text)} 字元（共比對 {len(candidates)} 個候選區塊）")
    if text:
        preview = text[:200].replace("\n", " ")
        print(f"  內文預覽：{preview}...")
    print(f"  版本重點圖：{image_url if image_url else '（沒找到，將只發文字）'}")
    return text, image_url


def process_one(title, url):
    print(f"  正在開啟：{url}")
    body, image_url = extract_patch_body(url)
    if not body:
        print("  內文抓取為空，跳過，不標記已讀（下次會重試）。")
        return False

    print("  正在呼叫 Gemini 產生摘要...")
    summary = summarize_lol(title, body, url)
    if not summary:
        print("  Gemini 沒有產生摘要，跳過，不標記已讀。")
        return False

    print(f"  摘要產生成功，長度：{len(summary)} 字元")
    if not send_discord("lol", title, summary, url, image_url=image_url):
        print("  Discord 發送失敗，跳過，不標記已讀。")
        return False

    print(f"  已發送：{title}")
    return True


def run_once():
    seen = load_seen()
    new_items = get_new_patches(seen)

    if not new_items:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 沒有新的版更公告。")
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 發現 {len(new_items)} 篇新版更公告。")

    processed = 0
    for item in new_items:
        title, url = item["title"], item["url"]
        print(f"處理：{title}")
        try:
            if process_one(title, url):
                seen.add(url)
                processed += 1
                if processed >= MAX_NEW_PER_RUN:
                    print(f"已達單輪上限 {MAX_NEW_PER_RUN} 篇，本輪提前結束。")
                    break
        except Exception as e:
            print(f"  處理失敗：{url}\n  原因：{e}")

    save_seen(seen)
    print(f"本輪成功發送 {processed} 篇。目前 seen：約 {len(seen)} 篇。")


def run_force_latest():
    """強制處理列表頁最新一篇，忽略 seen 狀態，方便測試。不會修改 lol_seen.json。"""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] === 強制處理最新一篇（測試模式，不修改 seen）===")

    items = get_patch_list()
    if not items:
        print("列表頁沒有抓到任何公告，流程中止。")
        return

    title, url = items[0]["title"], items[0]["url"]
    print(f"標題：{title}")
    print(f"網址：{url}")

    process_one(title, url)
    print("=== 強制處理完成（lol_seen.json 未被修改） ===")


def main():
    if "--force-latest" in sys.argv:
        run_force_latest()
        return

    if "--scan-once" in sys.argv:
        run_once()
        return

    print("請使用以下其中一種模式執行：")
    print("  python lol_monitor.py --scan-once     正常模式，只處理尚未通知的新公告")
    print("  python lol_monitor.py --force-latest   強制處理最新一篇，用於測試，不修改 seen")


if __name__ == "__main__":
    main()

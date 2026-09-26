import os
import sys
import json
import time
import re
from datetime import datetime

from dotenv import load_dotenv

# 必須先載入 .env，再載入其他模組。
load_dotenv()

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from ai_summary import summarize, test_gemini
from discord_sender import send_discord, test_webhooks

MAPLE_URL = os.getenv("MAPLE_URL", "https://maplestory.beanfun.com/Main")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
MAX_NEW_PER_RUN = int(os.getenv("MAX_NEW_PER_RUN", "10"))
API_SCAN_PAGES = int(os.getenv("API_SCAN_PAGES", "2"))

def env_keywords(name, default):
    raw = os.getenv(name)
    # .env 若存在空白/空值，不要把內建關鍵字整組覆蓋掉。
    values = [x.strip() for x in (raw if raw is not None else default).split(",") if x.strip()]
    return values or [x.strip() for x in default.split(",") if x.strip()]

GENERAL_KEYWORDS = env_keywords("GENERAL_KEYWORDS", "職業,活動,燃燒")
SHOP_KEYWORDS = env_keywords("SHOP_KEYWORDS", "商城")
MAINT_KEYWORDS = env_keywords("MAINT_KEYWORDS", "維護,更新")

SEEN_FILE = "seen.json"
DEBUG_FILE = "network_debug.log"
BASE_URL = "https://maplestory.beanfun.com"


def log_debug(s):
    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def launch_browser(playwright):
    """GitHub Actions 用 Chromium；Windows 本機沿用已安裝的 Microsoft Edge。"""
    browser_mode = os.getenv("MAPLE_BROWSER", "auto").strip().lower()
    if browser_mode == "chromium" or os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        return playwright.chromium.launch(headless=True)
    return playwright.chromium.launch(channel="msedge", headless=True)


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(str(x) for x in data if x)
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def classify(title, category_id=""):
    """將官方公告分成一般／商城／維護。

    規則：
    - 官方分類 67 = 維護
    - 標題含「維護」或「更新」 = 維護
    - 官方分類 72 = 活動／商城類：含商城關鍵字進商城，其餘全部進一般
    - 其他分類再依標題關鍵字補判斷
    """
    title = (title or "").strip()
    category_id = str(category_id or "").strip()

    # 維護與更新公告優先處理。
    if category_id == "67":
        return "maintenance"
    if any(k in title for k in MAINT_KEYWORDS):
        return "maintenance"

    # 官方 72 類包含活動與商城：商城獨立，其餘所有活動公告全部歸一般。
    if category_id == "72":
        if any(k in title for k in SHOP_KEYWORDS):
            return "shop"
        return "general"

    # 非 72 類公告仍可依標題關鍵字補判斷。
    if any(k in title for k in SHOP_KEYWORDS):
        return "shop"
    if any(k in title for k in GENERAL_KEYWORDS):
        return "general"
    return None


def add_candidate(found, item):
    if not isinstance(item, dict):
        return

    bid = str(item.get("bullentinId") or item.get("bulletinId") or item.get("bid") or "").strip()
    if not bid.isdigit():
        return

    url_link = str(item.get("urlLink") or "").strip()
    url = url_link if url_link else f"{BASE_URL}/bulletin?bid={bid}"
    title = str(item.get("title") or "").strip()
    start_date = str(item.get("startDate") or "").strip()
    cat = str(item.get("bullentinCatId") or "").strip()

    found[url] = {
        "url": url,
        "bid": bid,
        "title": title,
        "startDate": start_date,
        "categoryId": cat,
    }


def parse_bulletin_response(data, found):
    try:
        table = data["data"]["myDataSet"]["table"] or []
        total_page = int(data["data"]["myDataSet"]["systemTable"].get("totalPage", 1))
    except Exception as e:
        log_debug("PARSE_API_ERROR " + repr(e))
        return 1

    for item in table:
        add_candidate(found, item)
    return total_page


def api_post(page, payload):
    script = """
    async ({payload}) => {
        const token = document.querySelector('input[name="__RequestVerificationToken"]')?.value || "";
        const body = new URLSearchParams();
        for (const [k, v] of Object.entries(payload)) body.append(k, String(v));

        const r = await fetch('main?handler=BulletinProxy', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'X-CSRF-TOKEN': token,
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            },
            body
        });

        const text = await r.text();
        return {status: r.status, text};
    }
    """
    result = page.evaluate(script, {"payload": payload})
    log_debug(f"API_CALL status={result.get('status')} payload={payload}")
    log_debug("API_BODY " + result.get("text", "")[:20000])

    if result.get("status") != 200:
        raise RuntimeError(f"BulletinProxy HTTP {result.get('status')}: {result.get('text', '')[:500]}")

    return json.loads(result.get("text", ""))


def extract_bulletins(page):
    found = {}

    log_debug("\n" + "=" * 70)
    log_debug("RUN " + datetime.now().isoformat())

    def on_request(req):
        if req.resource_type in ("xhr", "fetch"):
            line = f"REQUEST {req.method} {req.url}"
            print("  " + line)
            log_debug(line)
            try:
                if req.post_data:
                    log_debug("POST_DATA " + req.post_data[:4000])
            except Exception:
                pass

    def on_response(resp):
        if resp.request.resource_type not in ("xhr", "fetch"):
            return
        try:
            line = f"RESPONSE {resp.status} {resp.url}"
            print("  " + line)
            log_debug(line)
            log_debug("CONTENT_TYPE " + resp.headers.get("content-type", ""))
        except Exception:
            pass

    page.on("request", on_request)
    page.on("response", on_response)

    print("正在開啟官方首頁...")
    page.goto(MAPLE_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)

    requests_to_scan = [
        {"Kind": "0", "method": "0"},
        {"Kind": "72", "method": "3", "toAll": "0"},
        {"Kind": "67", "method": "3", "toAll": "0"},
        {"Kind": "68", "method": "3", "toAll": "0"},
    ]

    for base in requests_to_scan:
        for page_no in range(1, API_SCAN_PAGES + 1):
            payload = dict(base)
            payload.update({"Page": str(page_no), "PageSize": "10"})
            try:
                data = api_post(page, payload)
                total_page = parse_bulletin_response(data, found)
                if page_no >= total_page:
                    break
            except Exception as e:
                print(f"公告 API 讀取失敗：{payload} / {e}")
                log_debug("API_ERROR " + repr(e))
                break

    # 額外從目前頁面補抓 bulletin?bid=xxxx 連結。
    try:
        links = page.locator("a")
        count = links.count()
        for i in range(min(count, 5000)):
            try:
                a = links.nth(i)
                href = a.get_attribute("href") or ""
                txt = a.inner_text(timeout=800).strip()
                m = re.search(r"/bulletin\?bid=(\d+)", href, re.I)
                if m:
                    bid = m.group(1)
                    found.setdefault(
                        f"{BASE_URL}/bulletin?bid={bid}",
                        {"url": f"{BASE_URL}/bulletin?bid={bid}", "bid": bid,
                         "title": txt, "startDate": "", "categoryId": ""}
                    )
            except Exception:
                pass
    except Exception:
        pass

    items = list(found.values())

    def sort_key(x):
        date = x.get("startDate", "")
        bid = int(x.get("bid", "0")) if str(x.get("bid", "")).isdigit() else 0
        return (date, bid)

    items.sort(key=sort_key, reverse=True)
    return items


def is_supported_url(url):
    """API 回傳的 urlLink 只要是 HTTP/HTTPS 就允許處理。
    公告本身是從官方 BulletinProxy 取得，因此不再用固定網域白名單
    阻擋 urlLink；真正的公告正文一律優先從 bid 對應的官方 bulletin 頁抓取。
    """
    return bool(re.match(r"^https?://[^\s]+$", (url or "").strip(), re.I))


def canonical_bulletin_url(bid, fallback_url=""):
    if str(bid or "").isdigit():
        return f"{BASE_URL}/bulletin?bid={bid}"
    return fallback_url


def seen_keys(item):
    bid = str(item.get("bid") or "").strip()
    url = str(item.get("url") or "").strip()
    keys = []
    if bid.isdigit():
        keys.append(f"bid:{bid}")
    if url:
        keys.append(url)
    return keys

def is_seen(item, seen):
    return any(k in seen for k in seen_keys(item))

def mark_seen(item, seen):
    for k in seen_keys(item):
        seen.add(k)


def unsee_bid(bid, seen):
    target = str(bid).strip()
    removed = []
    bid_key = f"bid:{target}"
    if bid_key in seen:
        seen.remove(bid_key)
        removed.append(bid_key)

    url = canonical_bulletin_url(target)
    if url in seen:
        seen.remove(url)
        removed.append(url)
    return removed


def seen_item_count(seen):
    # v10+ 會同時保存 bid:key 與 URL；以 bid:key 數量作為實際公告數。
    bid_count = sum(1 for x in seen if str(x).startswith("bid:") and str(x)[4:].isdigit())
    if bid_count:
        return bid_count
    return len(seen)


def extract_article(page, url, fallback_title=""):
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(800)

    title = ""
    for selector in [
        "h1", "h2", ".board-view h1", ".board-view h2",
        ".bulletin h1", ".bulletin h2", ".board-title",
        ".bulletin-title", "title"
    ]:
        try:
            txt = page.locator(selector).first.inner_text(timeout=1500).strip()
            if txt and len(txt) > 2:
                title = txt
                break
        except Exception:
            pass

    candidates = []
    for selector in [
        "main", ".board-view", ".bulletin", ".content",
        "#content", "article", ".mBulletin-detail", "body"
    ]:
        try:
            txt = page.locator(selector).first.inner_text(timeout=2000).strip()
            if len(txt) > 100:
                candidates.append(txt)
        except Exception:
            pass

    body = max(candidates, key=len) if candidates else ""

    if not title or title.lower() in {"beanfun", "maplestory"}:
        title = fallback_title or title or url

    if not body:
        try:
            body = page.locator("body").inner_text(timeout=3000).strip()
        except Exception:
            body = ""

    return title, body

def initialize_seen(items):
    seen = set()
    for item in items:
        url = item.get("url", "")
        if is_supported_url(url):
            seen.add(url)
    save_seen(seen)
    print(f"\n首次初始化完成：已將目前 {len(seen)} 篇官方公告寫入 {SEEN_FILE}")
    print("本次不發送 Discord。之後只會通知新出現且符合關鍵字的公告。")
    return seen



def find_api_item_by_bid(page, bid):
    """從官方 BulletinProxy 找指定 bid，避免公告頁 <title> 被首頁標題取代。"""
    target = str(bid).strip()
    payloads = [
        {"Kind": "0", "method": "0"},
        {"Kind": "67", "method": "3", "toAll": "0"},
        {"Kind": "72", "method": "3", "toAll": "0"},
        {"Kind": "68", "method": "3", "toAll": "0"},
    ]
    for base in payloads:
        for page_no in range(1, API_SCAN_PAGES + 1):
            payload = dict(base)
            payload.update({"Page": str(page_no), "PageSize": "10"})
            try:
                data = api_post(page, payload)
                table = data.get("data", {}).get("myDataSet", {}).get("table") or []
                for raw in table:
                    raw_bid = str(raw.get("bullentinId") or raw.get("bulletinId") or raw.get("bid") or "").strip()
                    if raw_bid == target:
                        item = {}
                        add_candidate({"_tmp": None}, raw)
                        item["bid"] = raw_bid
                        item["title"] = str(raw.get("title") or "").strip()
                        item["categoryId"] = str(raw.get("bullentinCatId") or "").strip()
                        item["url"] = str(raw.get("urlLink") or "").strip() or canonical_bulletin_url(raw_bid)
                        return item
                total_page = int(data.get("data", {}).get("myDataSet", {}).get("systemTable", {}).get("totalPage", 1))
                if page_no >= total_page:
                    break
            except Exception as e:
                log_debug("FORCE_API_ERROR " + repr(e))
                break
    return None

def run_force_bid(bid):
    """手動測試指定公告：忽略 seen，只發送一次，不改動既有 seen。"""
    target = str(bid).strip()
    if not target.isdigit():
        print("bid 必須是數字，例如 --force-bid 83778")
        return
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        try:
            # 先從官方 API 取得真正的公告標題與分類，避免 bulletin 頁的 <title> 變成首頁名稱。
            page.goto(MAPLE_URL, wait_until="domcontentloaded", timeout=30000)
            item = find_api_item_by_bid(page, target)

            if item:
                api_title = item.get("title", "").strip()
                category = classify(api_title, item.get("categoryId"))
                url = item.get("url", "").strip() or canonical_bulletin_url(target)
            else:
                api_title = ""
                category = None
                url = canonical_bulletin_url(target)

            title, body = extract_article(page, url, api_title)
            title = api_title or title

            # 已知維護公告的最後保底分類。
            if not category and target in {"83778", "83771"}:
                category = "maintenance"

            print(f"[FORCE] bid={target} category={category} title={title}")
            if not body:
                print("公告正文抓取為空")
                return
            if not category:
                print("無法判斷公告分類，停止發送。")
                return

            summary = summarize(title, body, url, category)
            if not summary:
                return
            send_discord(category, title, summary, url)
        finally:
            browser.close()

def run_simulate():
    """抓取目前掃描範圍內各分流最新的一篇實際公告並發送到 Discord。

    這是「真實公告回放」而非假訊息測試：會抓官方公告正文、交給 Gemini 摘要，
    再送到對應 Webhook；不讀取 seen 來阻擋，也不修改 seen.json。
    """
    print("\n=== 實際公告回放模式（不修改 seen.json） ===")
    print("將從目前官方 API 掃描結果中，各分流選最新 1 篇實際公告。")

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        try:
            items = extract_bulletins(page)
            print(f"找到 {len(items)} 篇公告候選")

            latest = {}
            for item in items:
                url = item.get("url", "")
                if not is_supported_url(url):
                    continue
                category = classify(item.get("title", ""), item.get("categoryId"))
                if not category:
                    continue
                # extract_bulletins 已按日期/bid 由新到舊排序，因此第一次遇到的就是最新。
                latest.setdefault(category, item)

            order = ("general", "shop", "maintenance")
            found_count = 0
            success_count = 0

            for category in order:
                item = latest.get(category)
                if not item:
                    print(f"\n[{category}] 找不到目前掃描範圍內符合條件的公告。")
                    continue

                found_count += 1
                bid = item.get("bid", "")
                url = item.get("url", "")
                api_title = item.get("title", "").strip()
                detail_url = url if url != canonical_bulletin_url(bid) else canonical_bulletin_url(bid, url)

                print(f"\n[SIMULATE] bid={bid} [{category}] {api_title}")
                print(f"  抓取：{detail_url}")
                log_debug(f"SIMULATE bid={bid} category={category} title={api_title!r} detail={detail_url}")

                try:
                    title, body = extract_article(page, detail_url, api_title)
                    if api_title:
                        title = api_title
                    if not body:
                        print("  公告正文抓取為空，跳過，不會修改 seen.json。")
                        continue

                    summary = summarize(title, body, url, category)
                    if not summary:
                        print("  Gemini 沒有產生摘要，跳過。")
                        continue

                    if send_discord(category, title, summary, url):
                        success_count += 1
                except Exception as e:
                    print(f"  模擬發送失敗：{e}")
                    log_debug("SIMULATE_ERROR " + repr(e))

            print(f"\n實際公告回放完成：找到 {found_count} 篇，成功發送 {success_count} 篇。")
            print("seen.json：未修改。")
        finally:
            browser.close()


def run_once(force_initialize=False):
    seen = load_seen()

    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 檢查官方網站...")

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        try:
            items = extract_bulletins(page)
            print(f"找到 {len(items)} 篇公告候選")

            if force_initialize:
                initialize_seen(items)
                return

            new_count = 0
            processed_count = 0
            skipped_unsupported = 0
            unseen_matches = []

            for item in items:
                if not is_seen(item, seen):
                    preview_category = classify(item.get("title", ""), item.get("categoryId"))
                    if preview_category:
                        unseen_matches.append((item.get("bid", ""), preview_category, item.get("title", "")))

            print(f"目前未讀且符合分流條件：{len(unseen_matches)} 篇")
            for bid, cat, title in unseen_matches[:20]:
                print(f"  [待處理] bid={bid} [{cat}] {title}")

            for item in items:
                url = item["url"]

                if is_seen(item, seen):
                    print(f"[SEEN] bid={item.get('bid')} {item.get('title', '')}")
                    continue

                if not is_supported_url(url):
                    skipped_unsupported += 1
                    log_debug(f"SKIP_INVALID_URL bid={item.get('bid')} title={item.get('title')} url={url}")
                    continue

                # urlLink 若是官方活動頁（例如 maplestory-event.beanfun.com），
                # 必須直接抓活動頁正文；沒有 urlLink 時才使用 bulletin?bid=。
                # 否則像「變身燃燒：露希妲」這類活動會只抓到外層公告殼，導致正文為空。
                detail_url = url if item.get("url") and item.get("url") != canonical_bulletin_url(item.get("bid")) else canonical_bulletin_url(item.get("bid"), url)
                log_debug(f"DETAIL_URL bid={item.get('bid')} detail={detail_url} link={url}")

                # 先用 API 回傳的標題分類，不等 detail 頁的 <title>。
                api_title = item.get("title", "").strip()
                category = classify(api_title, item.get("categoryId"))
                log_debug(f"CLASSIFY bid={item.get('bid')} catId={item.get('categoryId')} title={api_title!r} => {category}")
                if not category:
                    # 若 API 標題沒有關鍵字，再用實際頁面標題補判斷。
                    try:
                        detail_title, _ = extract_article(page, detail_url, api_title)
                        category = classify(detail_title, item.get("categoryId"))
                    except Exception as e:
                        log_debug("CLASSIFY_DETAIL_ERROR " + repr(e))
                        category = None

                if not category:
                    mark_seen(item, seen)
                    processed_count += 1
                    continue

                try:
                    print(f"符合關鍵字：[{category}] {api_title or url}")
                    title, body = extract_article(page, detail_url, api_title)
                    # API 標題通常比頁面 <title> 更乾淨，優先使用 API 標題。
                    if api_title:
                        title = api_title

                    if not body:
                        print("公告正文抓取為空，本篇不標記 seen。")
                        log_debug(f"EMPTY_BODY bid={item.get('bid')} url={url}")
                        continue

                    summary = summarize(title, body, url, category)
                    if not summary:
                        print("Gemini 沒有產生摘要，本篇不標記 seen。")
                        continue

                    if not send_discord(category, title, summary, url):
                        print("Discord 發送失敗，本篇不標記 seen。")
                        continue

                    mark_seen(item, seen)
                    processed_count += 1
                    new_count += 1

                    if new_count >= MAX_NEW_PER_RUN:
                        break

                except Exception as e:
                    print(f"處理公告失敗：{url}\n原因：{e}")
                    log_debug("PROCESS_ERROR " + repr(e))

            save_seen(seen)
            print(f"本輪成功完成 {new_count} 篇新公告。")
            print(f"本輪處理並記錄：{processed_count} 篇。")
            if skipped_unsupported:
                print(f"本輪跳過不支援網址：{skipped_unsupported} 篇。")
            print(f"目前 seen.json：約 {seen_item_count(seen)} 篇公告。")
            print(f"診斷紀錄：{DEBUG_FILE}")
        finally:
            browser.close()


def run_unsee_bids(raw_bids):
    seen = load_seen()
    bids = [x.strip() for x in str(raw_bids).split(",") if x.strip()]
    changed = 0
    for bid in bids:
        removed = unsee_bid(bid, seen)
        if removed:
            changed += 1
            print(f"[UNSEEN] bid={bid} 已移除 seen：{len(removed)} 個索引")
        else:
            print(f"[UNSEEN] bid={bid} 找不到 seen 紀錄")
    save_seen(seen)
    print(f"完成：{changed} 篇公告已可重新處理。")


def setup_test():
    print("\n=== v8 設定檢查 ===")
    print("Gemini：", "OK" if test_gemini() else "失敗")
    print("Discord：")
    results = test_webhooks()
    for category, ok in results.items():
        print(f"  {category}: {'OK' if ok else '未設定/失敗'}")


def main():
    if "--test" in sys.argv:
        setup_test()
        return

    if "--force-bid" in sys.argv:
        i = sys.argv.index("--force-bid")
        if i + 1 >= len(sys.argv):
            print("請指定 bid，例如：python monitor.py --force-bid 83778")
            return
        run_force_bid(sys.argv[i + 1])
        return

    if "--unsee-bid" in sys.argv:
        i = sys.argv.index("--unsee-bid")
        if i + 1 >= len(sys.argv):
            print("請指定 bid，例如：python monitor.py --unsee-bid 83778,83728")
            return
        run_unsee_bids(sys.argv[i + 1])
        return

    if "--simulate" in sys.argv:
        run_simulate()
        return

    if "--scan-once" in sys.argv:
        run_once()
        return

    if "--initialize-seen" in sys.argv:
        print("=== 初始化 seen.json ===")
        run_once(force_initialize=True)
        return

    print("=" * 50)
    print(" MapleStory 官方公告監控器 v19")
    print(f" 每 {POLL_SECONDS} 秒檢查一次")
    print(" Windows 本機使用 Microsoft Edge；GitHub Actions 使用 Playwright Chromium")
    print(" 官方 BulletinProxy API")
    print(" 關鍵字只判斷公告標題")
    print(" urlLink 有官方活動頁時直接抓活動頁正文，無 urlLink 才使用 bid 公告頁")
    print(" 支援 --scan-once：只執行一輪後結束")
    print(" 支援 --simulate：回放目前各分流最新實際公告，不修改 seen.json")
    print(" 支援 --unsee-bid：移除指定公告的 seen，可重新測試")
    print(" Gemini / Discord 失敗時不會誤標記 seen")
    print("=" * 50)

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            print("\n已停止監控。")
            break
        except Exception as e:
            print(f"\n本輪執行發生錯誤：{e}")
            log_debug("MAIN_ERROR " + repr(e))

        print(f"\n等待 {POLL_SECONDS} 秒後再次檢查...")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

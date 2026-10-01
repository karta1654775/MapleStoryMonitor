# MapleStoryMonitor — 多遊戲公告監控機器人

自動監控多款遊戲的官方公告／版更訊息，用 Gemini AI 整理成 Discord 懶人包，依排程推播到對應頻道。全部跑在 GitHub Actions 上，不需要自己開機器。

目前監控中：

| 遊戲 | 程式 | 抓取方式 | 排程 |
|---|---|---|---|
| 🍁 新楓之谷 | `monitor.py` | Playwright + 官方 BulletinProxy API，分一般／商城／維護三個分流 | 每 10 分鐘 |
| 🎮 Warframe | `warframe_monitor.py` | 直接讀官方論壇 RSS 的 `description` 欄位（純文字請求，不開瀏覽器） | 每 15 分鐘 |
| ⚔️ 英雄聯盟 | `lol_monitor.py` | requests + BeautifulSoup 抓官方繁中版更頁面，含版本重點圖 | 每 15 分鐘 |
| 🎯 特戰英豪 VALORANT | `valorant_monitor.py` | requests + BeautifulSoup 抓官方繁中版更頁面，另外交叉比對英文版抓武器英文名稱 | 每 15 分鐘 |

四支監控抓取邏輯各自獨立，但共用同一套 Gemini 摘要底層與 Discord 發送邏輯。

---

## 整體架構

```
GitHub Actions 排程
   ↓
抓公告列表（API／RSS／網頁）
   ↓
比對 seen 狀態，篩出尚未通知的新公告
   ↓
抓公告正文（VALORANT 另外交叉比對英文版武器名稱）
   ↓
Gemini 依各遊戲專屬 prompt 整理成固定格式懶人包
   ↓
送到對應 Discord Webhook（超過 2000 字自動分段，不截斷）
   ↓
更新 seen 檔案，GitHub Actions 自動 commit 回 repository
```

四支監控共用 `ai_summary.py` 的底層邏輯（Gemini 呼叫 + 模型 fallback）和 `discord_sender.py`（Discord 發送邏輯），各自的抓取、分類與摘要 prompt 則獨立成對應檔案。

---

## 檔案結構

```
MapleStoryMonitor/
├─ .github/workflows/
│  ├─ monitor.yml              ← 楓之谷排程
│  ├─ warframe_monitor.yml     ← Warframe 排程
│  ├─ lol_monitor.yml          ← LoL 排程
│  └─ valorant_monitor.yml     ← VALORANT 排程
├─ monitor.py                     ← 楓之谷主程式
├─ warframe_monitor.py            ← Warframe 主程式
├─ lol_monitor.py                  ← LoL 主程式
├─ valorant_monitor.py              ← VALORANT 主程式
├─ ai_summary.py                     ← 共用：Gemini 摘要底層（楓之谷直接使用）
├─ warframe_summary.py               ← Warframe 專用摘要 prompt
├─ lol_summary.py                    ← LoL 專用摘要 prompt
├─ valorant_summary.py               ← VALORANT 專用摘要 prompt
├─ discord_sender.py                 ← 共用：Discord 發送（含分段、圖片 embed）
├─ seen.json / warframe_seen.json / lol_seen.json / valorant_seen.json  ← 各自的去重狀態
├─ requirements.txt
├─ .env.example                      ← 本機測試用環境變數範本
├─ .gitignore
└─ run_monitor.bat                   ← 本機一鍵啟動（楓之谷）
```

---

## 需要設定的 GitHub Secrets

`Settings → Secrets and variables → Actions → Secrets`

| Secret | 用途 |
|---|---|
| `GEMINI_API_KEY` | 四支監控共用 |
| `DISCORD_GENERAL_WEBHOOK` | 楓之谷－一般／活動 |
| `DISCORD_SHOP_WEBHOOK` | 楓之谷－商城 |
| `DISCORD_MAINTENANCE_WEBHOOK` | 楓之谷－維護 |
| `DISCORD_WARFRAME_WEBHOOK` | Warframe |
| `DISCORD_LOL_WEBHOOK` | 英雄聯盟 |
| `DISCORD_VALORANT_WEBHOOK` | 特戰英豪 |

不要把任何 Webhook 或 API Key 寫進程式碼、README 或 commit 紀錄裡，一律用 Secrets。

另外在 `Settings → Actions → General → Workflow permissions` 確認已選 **Read and write permissions**，四支監控更新 seen 檔案後都需要自動 commit 回 repository。

---

## GitHub Actions 手動測試模式

### 楓之谷（`monitor.yml`）
| 模式 | 說明 |
|---|---|
| `normal` | 正常模式，只處理尚未通知的新公告 |
| `simulate` | 回放三個分流各最新 1 篇，不修改 `seen.json` |
| `simulate-general` | 只回放「一般／活動」分流最新 1 篇 |
| `simulate-shop` | 只回放「商城」分流最新 1 篇 |
| `simulate-maintenance` | 只回放「維護／更新」分流最新 1 篇 |

### Warframe（`warframe_monitor.yml`）
| 模式 | 說明 |
|---|---|
| `normal` | 正常模式 |
| `simulate` | 強制處理 RSS 最新一篇，不修改 `warframe_seen.json` |

### 英雄聯盟（`lol_monitor.yml`）
| 模式 | 說明 |
|---|---|
| `normal` | 正常模式 |
| `force-latest` | 強制處理列表頁最新一篇，不修改 `lol_seen.json` |
| `test-latest-3` | 測試最新 3 篇（含版本重點圖抓取），不修改 `lol_seen.json` |

### 特戰英豪（`valorant_monitor.yml`）
| 模式 | 說明 |
|---|---|
| `normal` | 正常模式，只處理尚未通知的新版本公告（單輪上限 1 篇，`VALORANT_MAX_NEW_PER_RUN`） |
| `test-latest` | 強制測試列表頁最新一篇，不修改 `valorant_seen.json` |
| `test-13-06` | 強制測試固定寫死的 13.06 版公告網址，不修改 `valorant_seen.json`（偵錯用的特定版本測試，不是通用參數） |

> `workflow_dispatch` 另外還有一個 `test_url` 輸入欄位（預設值就是 13.06 那篇網址），但目前 3 個模式選項裡沒有任何一個會真的去讀這個欄位──`test-13-06` 是把網址寫死在 run 指令裡，`test_url` 這個輸入目前形同虛設。如果想要「手動貼網址測試任一篇」的彈性，要嘛把 `test-13-06` 改成讀 `$TEST_URL` 而不是寫死字串，要嘛乾脆比照 `lol_monitor.py --force-url` 的模式把這個輸入接起來。

所有「模擬／測試」類模式都**不會**修改對應的 seen 檔案，可以重複執行測試，不用擔心弄亂正式的已讀紀錄。

---

## 本機手動執行

```bat
:: 楓之谷
python monitor.py --scan-once
python monitor.py --simulate

:: Warframe
python warframe_monitor.py --scan-once
python warframe_monitor.py --simulate

:: 英雄聯盟
python lol_monitor.py --scan-once
python lol_monitor.py --force-latest
python lol_monitor.py --test-latest-3

:: 特戰英豪
python valorant_monitor.py --scan-once
python valorant_monitor.py --test-latest
python valorant_monitor.py --force-url https://playvalorant.com/zh-tw/news/game-updates/...
```

本機測試請先複製 `.env.example` 為 `.env` 並填入對應的 API Key 和 Webhook 網址。

---

## VALORANT 的特殊設計：中英對照抓武器名稱

`valorant_monitor.py` 抓到繁中官方公告正文之後，會額外把同一篇網址的 `/zh-tw/` 換成 `/en-us/`，抓**英文官方版**，只截取其中「WEAPONS UPDATES」那個段落，交給 Gemini 當作「新增武器英文名稱」的對照參考（`english_weapon_reference` 參數）。這是因為武器新增/調整這類內容，繁中公告有時候翻譯用詞會跟官方正式譯名有落差，用英文原文反查可以降低這類用詞誤差。

英文版讀取失敗時不會中斷整個流程，會自動改用純繁中公告處理，只是少了這層英文對照。

---

## Gemini 模型與容錯機制

- 預設模型與 fallback 清單由 `GEMINI_MODEL` / `GEMINI_FALLBACK_MODELS` 環境變數控制，主模型忙碌時會自動依序切換到下一個
- 單次輸出上限為 8192 tokens；若 Gemini 回傳的 `finishReason` 是 `MAX_TOKENS`（代表輸出被腰斬、內容不完整），會自動判定該次嘗試失敗並換下一個模型重試，避免把殘缺內容送到 Discord
- 各遊戲的摘要格式驗證失敗時，會自動帶著錯誤說明重新整理一次（維護類公告最多到第三次重試）

---

## Discord 發送規則

- 懶人包超過 Discord 單則訊息 2000 字上限時，會依換行邊界自動切成多則訊息依序發送（標示 `(1/N)`），不會直接截斷內容
- 若該篇公告有對應的圖片（目前只有 LoL 的「版本重點圖」），會用 Discord embed 附在第一則訊息上
- 發送失敗（Gemini 沒有產出摘要、Discord API 回傳錯誤等）時，不會把該篇標記為已讀，下次執行會重新嘗試

---

## 已知限制

- Warframe 論壇原本用 Playwright 開瀏覽器抓內文，但 GitHub Actions 的 IP 會被 Cloudflare 擋下，後來改成直接解析 RSS 的 `description` 欄位，不再需要瀏覽器
- VALORANT 的英文對照目前只處理「WEAPONS UPDATES」段落，其他段落（幹員調整、地圖異動等）沒有做中英對照
- `valorant_monitor.yml` 的 `test_url` 輸入欄位目前沒有實際被任何模式讀取，`test-13-06` 是寫死網址的暫時測試選項

📜 License

本專案主要為個人／私人 Discord 公告自動化工具。

遊戲名稱、官方網站、Logo、角色與其他相關素材之權利均屬各遊戲／發行商所有。本專案不代表 MapleStory、Digital Extremes、Riot Games 或 Discord 官方。

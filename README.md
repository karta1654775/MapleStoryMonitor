# MapleStory 官方公告監控器 — GitHub Actions 版

這一版是給 GitHub Actions 長期自動執行使用。電腦不需要開機，GitHub 會依排程啟動 Python，抓新楓之谷台灣官方公告、用 Gemini 整理，再送到 3 個 Discord Webhook。

## 目前分流規則

- 📢 一般：官方分類 `72` 的所有活動公告；但標題含「商城」者改送商城。另有標題含 `職業`、`活動`、`燃燒` 的非 72 公告也會送一般。
- 🛒 商城：標題含 `商城`。
- 🔧 維護：官方分類 `67`，或標題含 `維護`、`更新`。
- 其他分類且不符合以上規則：不發送。

## GitHub Actions 執行方式

`.github/workflows/monitor.yml` 已設定：

- `workflow_dispatch`：可以在 GitHub 網頁手動執行。
- 每 10 分鐘自動執行一次。
- 使用台北時區 `Asia/Taipei`。
- 每次只跑一輪 `python monitor.py --scan-once`，跑完就結束。
- GitHub Actions 使用 Playwright Chromium，不需要你的電腦安裝 Edge。
- 成功發送後更新 `seen.json`，再由 GitHub Actions 自動 commit 回 repository，避免下次重複通知。
- 使用 concurrency 避免前一次執行還沒結束時又同時處理同一批公告。

GitHub 的 scheduled workflow 最短排程間隔為 5 分鐘；排程以預設分支最新 commit 執行，而且高負載時可能延遲。這個專案使用 10 分鐘間隔。 

## 需要設定的 GitHub Secrets

Repository → Settings → Secrets and variables → Actions → Secrets → New repository secret

建立以下 4 個：

1. `GEMINI_API_KEY`
2. `DISCORD_GENERAL_WEBHOOK`
3. `DISCORD_SHOP_WEBHOOK`
4. `DISCORD_MAINTENANCE_WEBHOOK`

不要把真正的 API Key 或 Discord Webhook 寫進 GitHub repository 的程式碼、README 或 `.env`。本專案的 `.gitignore` 已忽略 `.env`。

## GitHub 新手設定步驟

### 1. 建立 Repository

GitHub → 右上角 `+` → `New repository`

建議：
- Repository name：`MapleStoryMonitor`
- 可選 `Private`，不需要公開程式碼。
- 不要勾選自動建立 README，因為這個 ZIP 已經有 README。
- 按 `Create repository`。

### 2. 上傳 v19 檔案

解壓 `MapleStoryMonitor_v19.zip`。

進入解壓後的 `v19` 資料夾，把裡面的檔案與資料夾全部上傳到 Repository 最外層。

Repository 根目錄應該直接看到：

```text
MapleStoryMonitor/
├─ .github/
│  └─ workflows/
│     └─ monitor.yml
├─ monitor.py
├─ ai_summary.py
├─ discord_sender.py
├─ requirements.txt
├─ seen.json
├─ .env.example
├─ .gitignore
└─ README.md
```

不要把整個 `v19` 資料夾再包一層上傳；`monitor.py` 應該直接在 Repository 根目錄。

### 3. 設定 Secrets

進入 Repository → `Settings` → 左側 `Secrets and variables` → `Actions` → `Secrets` → `New repository secret`。

依序建立：

```text
GEMINI_API_KEY
DISCORD_GENERAL_WEBHOOK
DISCORD_SHOP_WEBHOOK
DISCORD_MAINTENANCE_WEBHOOK
```

Value 分別貼入你現在使用的 Gemini API Key，以及 3 個 Discord Webhook 完整網址。

建立後 GitHub 只會顯示 Secret 名稱，不會讓你重新看到完整值；這是正常的。

### 4. 確認 Actions 有寫入權限

這個專案需要 GitHub Actions 把更新後的 `seen.json` commit 回 Repository。

到：

`Settings` → `Actions` → `General`

找到 `Workflow permissions`。

如果看到可以選：

`Read and write permissions`

請選它並按 `Save`。

Workflow 本身也已經寫入：

```yaml
permissions:
  contents: write
```

所以只有 repository contents 的寫入權限，不需要額外建立 GitHub Personal Access Token。

### 5. 第一次手動測試

進入 Repository → 上方 `Actions`。

左側找到：

`MapleStory 公告監控`

第一次可能會看到 GitHub 要求啟用 workflow，依畫面按啟用即可。

右側按 `Run workflow` → 選預設分支 → `Run workflow`。

等待幾秒後，下面會出現一筆執行紀錄。

點進去後看到：

```text
取得程式碼
設定 Python
安裝 Python 套件
安裝 Playwright Chromium
執行一次公告檢查
儲存 seen.json
```

全部出現綠色勾勾，就代表 GitHub Actions 本身成功執行。

### 6. 確認 Discord

如果剛好有新的、尚未記錄在 `seen.json` 的符合條件公告，會直接送到對應 Discord。

如果目前沒有新公告，Actions 仍然會成功，只是 Discord 不會收到訊息。

這是正常的。

### 7. 確認 seen.json 是否自動保存

如果本輪真的發送了新公告，Actions 最後一步會 commit：

```text
chore: update MapleStory seen state
```

回 Repository 的 `seen.json` 查看，就會看到新的 `bid:xxxxx`。

如果沒有新公告，沒有 commit 也是正常的。

## 正常運作後

你不需要再開電腦，也不需要讓 CMD 一直開著。

GitHub Actions 會：

```text
每 10 分鐘
   ↓
GitHub Runner 啟動
   ↓
抓官方公告 API
   ↓
找尚未通知的公告
   ↓
抓官方正文
   ↓
Gemini 整理懶人包
   ↓
送到對應 Discord
   ↓
更新 seen.json
   ↓
commit 回 GitHub
   ↓
Runner 結束
```

## 手動模式

### 只跑一次

本機：

```bat
python monitor.py --scan-once
```

### 實際公告回放

```bat
python monitor.py --simulate
```

這會抓目前實際公告並送到 Discord，但不修改 `seen.json`。

### 測試設定

```bat
python monitor.py --test
```

### 指定公告

```bat
python monitor.py --force-bid 83778
```

## GitHub Actions 上不要使用的模式

不要在 GitHub Actions 執行：

```bat
python monitor.py
```

因為這是本機長時間 while-loop 模式。

GitHub Actions 應該使用：

```bat
python monitor.py --scan-once
```

由 GitHub 的 `schedule` 每 10 分鐘重新啟動一次。

## 如果 Actions 顯示失敗

先點進失敗的 workflow run，再點紅色失敗的 step。

常見情況：

### `GEMINI_API_KEY` 相關錯誤

檢查：
`Settings → Secrets and variables → Actions`

確認 Secret 名稱完全是：

`GEMINI_API_KEY`

### Discord HTTP 失敗

確認 3 個 Discord Webhook Secret 是否貼完整，尤其不要多貼空白或引號。

### `seen.json` push 被拒絕

確認：
`Settings → Actions → General → Workflow permissions`

已設定 `Read and write permissions`。

### Actions 完全沒有自動執行

先手動 `Run workflow` 測試。

另外，scheduled workflow 只會從 repository 的預設分支執行，而且 GitHub 說明指出排程在高負載時可能延遲；公開 repository 若 60 天沒有 repository activity，scheduled workflow 也可能被自動停用。

## 安全注意事項

- `.env` 已被 `.gitignore` 排除。
- 真正的 Gemini API Key 與 Discord Webhook 必須放 GitHub Secrets。
- 不要把 Secret 貼到 Issue、README、程式碼或公開 commit。
- 不要把你現在本機的 `.env` 上傳到 GitHub。

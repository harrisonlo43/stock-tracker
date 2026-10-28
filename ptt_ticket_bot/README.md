# PTT 售票通知機器人

每 5 分鐘掃描 PTT [KoreaDrama 版](https://www.ptt.cc/bbs/KoreaDrama/index.html)，
發現 **標題有「售票」**、且內容提到 **金智媛 / KIM JI WON** 和 **11/08** 的新文章，就用 WhatsApp 通知你。

- 同一篇文章只通知一次（記錄在 `seen.json`）
- 日期支援 `11/08`、`11/8`、`11.8`、`11-8`、`11月8日`、`1108` 等寫法
- 藝人名稱不分大小寫、空格，`Kim Ji Won`、`KIMJIWON`、`김지원` 都算
- 推文裡的 11/08（推文時間）不會造成誤判

## 設定步驟（第一次，約 5 分鐘）

### 1. 取得 WhatsApp 通知用的 apikey（CallMeBot，免費）

1. 把 **+34 694 29 84 96** 加進手機聯絡人（名字隨意，例如 CallMeBot）。
2. 用 WhatsApp 傳這句話給它：`I allow callmebot to send me messages`
3. 稍等一下，它會回你一組 **apikey**（一串數字）。

> 若 CallMeBot 的號碼有變動，請以 <https://www.callmebot.com/blog/free-api-whatsapp-messages/> 公告為準。

### 2. 把資料存進 GitHub Secrets

到 GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**，新增兩個：

| 名稱 | 內容 |
|------|------|
| `CALLMEBOT_PHONE` | 你的手機號碼，國際格式，例如 `+886912345678` |
| `CALLMEBOT_APIKEY` | 上一步拿到的 apikey |

（若想改用 Twilio，改設 `TWILIO_ACCOUNT_SID`、`TWILIO_AUTH_TOKEN`、`TWILIO_FROM`、`TWILIO_TO`。）

### 3. 啟動

GitHub 的排程只會在**預設分支（main）**上執行，所以這些檔案要在 main 上。
到 **Actions → PTT 售票通知 → Run workflow** 可以立刻手動跑一次測試。

### 4. 活動結束後關閉

到 **Actions → PTT 售票通知 → ⋯ → Disable workflow**，避免一直執行。

## 調整搜尋條件

在 `.github/workflows/ptt-ticket-bot.yml` 的 `env:` 加上下列設定即可（多個值用逗號分隔）：

| 變數 | 預設 | 說明 |
|------|------|------|
| `TITLE_KEYWORDS` | `售票` | 標題要包含其一，例如 `售票,讓票` |
| `ARTIST_KEYWORDS` | `金智媛,KIM JI WON,KIMJIWON,김지원` | 標題或內文要包含其一 |
| `DATE_PATTERNS` | 11/08 的各種寫法 | 正規表示式；設 `none` 代表不限日期 |
| `PAGES` | `3` | 每次往回掃幾頁（一頁約 20 篇） |

## 在自己電腦上跑

```bash
pip install -r ptt_ticket_bot/requirements.txt
```

```bash
python ptt_ticket_bot/bot.py --dry-run
```

```bash
CALLMEBOT_PHONE=+886912345678 CALLMEBOT_APIKEY=你的apikey python ptt_ticket_bot/bot.py --loop 120
```

`--dry-run` 只印出找到的文章不發通知；`--loop 120` 會每 2 分鐘掃一次、持續執行（比 GitHub 排程更即時）。

# stock-tracker

台股產業趨勢觀察 — 由排程雲端 agent 每營業日晚上自動更新。

## 結構

- `watchlist.txt` — 股票 / ETF 觀察清單（逗號分隔代號）
- `reports/` — 每次執行產出的產業趨勢報告（Markdown），檔名格式 `YYYY-MM-DD-sector-trend.md`
- `reports/latest.md` — 最新一份報告的複本，方便快速查看

## 觀察清單

```
2330, 00685L, 00981A, 00663L, 00631L
```

報告內容：搜尋各產業整體表現，指出本週最強／最弱產業，並用幾句話說明原因。

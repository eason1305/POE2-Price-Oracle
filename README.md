# POE2-Price-Oracle

## PoE2 通貨價格 → Discord 看板

A tiny, serverless price board: fetches selected Path of Exile 2 currency prices from poe.ninja every hour and **edits a single Discord message in place** via webhook — no bot, no spam, no monthly cost.

每小時從 poe.ninja 抓取指定通貨價格,**重複編輯 Discord 頻道裡同一則訊息**(不洗頻、不發通知)。零伺服器、零月費,全靠 GitHub Actions 免費額度。想自己架一份,照下面步驟約 5 分鐘完成。

## 架構

```
GitHub Actions (每小時 cron)
  → update_prices.py
      → GET poe.ninja/poe2/api/economy/leagues        (取得目前聯盟 id)
      → GET .../exchange/current/overview?type=Currency (取得價格)
      → PATCH Discord 訊息 (Webhook 或 Bot REST API)     (編輯同一則訊息)
```

支援兩種發言身份,腳本自動偵測(設定了 bot token 就走 Bot 模式,否則走 Webhook 模式):

| | Webhook 模式 | Bot 模式 |
|---|---|---|
| 設定難度 | 低(頻道內建功能) | 中(需建立 Discord Application) |
| 發言身份 | 頻道的 webhook(可自訂名稱頭像) | 真正的 bot 帳號,出現在成員清單、可給身分組 |
| 憑證洩漏影響 | 只能對該頻道發訊息 | 可以 bot 身份在其所有 server 行動 |
| 成員清單顯示 | 不出現 | 出現,但恆為離線(灰色,因為沒有常駐連線) |

兩種模式都不需要常駐程式——編輯訊息只用 REST API,bot 不必「上線」。

## 設定步驟(一次性,約 5~15 分鐘)

### 1. 擇一建立發言身份

**Webhook 模式**:在目標頻道:頻道設定 → 整合 → Webhook → 新增 Webhook → 複製 Webhook URL。這個 URL 等同密碼,**不要**貼進程式碼或公開場合。

**Bot 模式**:

1. 到 [Discord Developer Portal](https://discord.com/developers/applications) → New Application,取好名字(這就是顯示在成員清單的名稱)。
2. 左側 Bot 頁 → Reset Token → 複製 token(等同密碼,妥善保存)。
3. 左側 OAuth2 → URL Generator:勾 `bot` scope,權限勾 `View Channels`、`Send Messages`、`Embed Links`;用產生的網址把 bot 邀進你的 server。
4. 在 Discord 開啟開發者模式(設定 → 進階),對目標頻道右鍵 → 複製頻道 ID。

### 2. 建立 GitHub repo 並上傳檔案

建一個 repo(public 或 private 皆可),放入:

```
update_prices.py
.github/workflows/update.yml
README.md
```

### 3. 設定 Secrets

Repo → Settings → Secrets and variables → Actions → New repository secret,依模式擇一組:

- Webhook 模式:`DISCORD_WEBHOOK_URL` = Webhook URL
- Bot 模式:`DISCORD_BOT_TOKEN` = bot token,`DISCORD_CHANNEL_ID` = 頻道 ID

(兩組都設時以 Bot 模式優先。中途換模式也沒關係,腳本編輯不了另一個身份發的舊訊息時,會自動改發一則新的並記住它。)

### 4. 首次執行

Repo → Actions 分頁 → 啟用 workflows → 選「Update PoE2 prices」→ Run workflow。

第一次執行會在頻道發出一則新訊息,並自動把訊息 id commit 回 repo(`message_id.txt`)。之後每小時就只編輯這則訊息。建議把這則訊息**釘選**,成員更好找。

## 日常調整

- **改追蹤的通貨**:編輯 `.github/workflows/update.yml` 裡的 `CURRENCIES`(逗號分隔,用 poe.ninja 上顯示的英文名,如 `Divine Orb,Chaos Orb,Orb of Annulment`)。
- **換聯盟**(新賽季):改 `LEAGUE_MATCH`(聯盟名的一小段即可,如 `aldur`);找不到符合的會自動退回目前的挑戰聯盟,所以通常不改也能用。
- **改頻率**:改 cron 表達式。poe.ninja PoE2 資料約每小時才更新,抓更快沒有意義,也請尊重對方的公益 API。
- **價格單位**:PoE2 匯率以聯盟的主要參考通貨計價(通常是 Exalted Orb),訊息會自動標示單位。

## 費用與注意事項

- **Public repo**:Actions 免費且不限分鐘數。
- **Private repo**:免費額度 2,000 分鐘/月;本工作每次不到 1 分鐘、每小時一次,約 750 分鐘/月,額度內。
- **排程延遲**:GitHub 的 cron 常延遲 3~15 分鐘,對每小時更新的價格看板無傷大雅。若要求準時可改用 Cloudflare Workers Cron(也免費)。
- **60 天閒置停用**:repo 若 60 天沒有任何 commit,GitHub 會自動停用排程 workflow(會先寄信通知,到 Actions 頁按一下 Enable 即可恢復)。偶爾改一下通貨清單自然就會重置計時。
- poe.ninja 要求合理使用:每小時一次、附帶識別用 User-Agent,本腳本皆已遵守。請把 `update_prices.py` 裡 User-Agent 的聯絡信箱改成你自己的。

## 授權 License

本專案程式碼以 [MIT License](LICENSE) 釋出。價格資料來自 [poe.ninja](https://poe.ninja),其資料不在本授權範圍內;本專案與 poe.ninja 及 Grinding Gear Games 無關。

Code is released under the [MIT License](LICENSE). Price data is provided by [poe.ninja](https://poe.ninja) and is not covered by this license. Not affiliated with poe.ninja or Grinding Gear Games.

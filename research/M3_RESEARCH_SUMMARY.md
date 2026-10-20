# M3 — 新聞發現可靠性研究快照

**BOUNDED_RESEARCH_OBSERVATION_NOT_24_7**  
**NOT_LIVE_TRADING_SIGNAL**  
**GLOBAL_FIRST_SEEN_NOT_PROVEN**

本輪改善獨立研究工具，沒有啟用正式Collector、網站自動新聞更新、Writer或交易。
M1七篇快照與M2 CPI案例保持不變；這份報告不是新的即時新聞牆。

## 實際觀測

- UTC：2026-10-20T02:31:39.526626Z → 2026-10-20T03:02:03.850298Z
- 健康來源：3/6；已解析不同文章：45。
- 來源GET：9；官方原文GET：1。
- 已讀payload：657027 bytes；含無ACK請求保留額度上界：2754179 bytes。Wire bytes沒有封包量測。
- 48小時相關候選：0；7日研究脈絡候選：1。
- 凍結的小樣本benchmark：1/3；不是全世界事件recall。

|Cycle|GET|Success|New to experiment|Updates|Duplicates|
|---|---:|---:|---:|---:|---:|
|cycle_001|6|3|45|0|0|
|cycle_002|3|3|0|0|45|

第一輪new是本實驗首次記錄，不代表新聞剛發生。第二輪即使沒有新稿，也不能把重複資料算成新事件。

## 真正修復與未證明的事

1. 新工具不依賴私有response.fp.raw._sock欄位，三筆真實200回應在EOF關閉fp後仍完成解析。HTTP ACK先保存，解析失敗與來源拒絕分開。
2. 研究規則補上Fed指定會議紀錄標題；同一份45筆快照的article-set候選由11增至18。七篇都是歷史政策脈絡，只有一篇在7日內，48h仍0。這是樣本內修正，不是前瞻recall增幅。
3. M2六筆AttributeError沒有當時版本SHA或stack；目前保存版本已修正且離線測試通過。EOF私有欄位失敗模式已重現，但不能聲稱逐筆證明原根因。

## 官方證據交接

候選原標題：Minutes of the Board's discount rate meetings on August 17, September 9, and September 16, 2026
原文：https://www.federalreserve.gov/newsevents/pressreleases/monetary20261013a.htm
狀態：**OFFICIAL_VERIFICATION_PENDING**。已取得相應Fed原文供具體命題審查；貼現率會議不等於FOMC新利率決定。
原文取得UTC：2026-10-20T02:40:21.422372Z
原文response SHA256：73e63d8fd1f07b67d346b5dbba048ae0507bac1816c060d7a840cca90f51b777

## 仍缺什麼

BLS目前403；360info本次逾時無ACK；EIA先前406原因未知而未重試。沒有新的合格突發事件、持久全球first-seen、正式as-of API、正式Frozen或24/7驗收。
source-to-observation數字最多是來源自報時間到本輪取得的間隔；不是生產偵測SLA。CPI已知時鐘衝突保持UNKNOWN，不夾成0。

## 使用與來源界線

這份公開安全摘要只含自產統計、機構標題與官方連結，不含新聞全文、圖片、logo、個人資料、原始Feed、內部日誌或本機路徑。
原始研究收據與完整metadata只留在隔離本機RUN，未納入production manifest。來源權利參照既有研究範圍：ECB標題／連結；GlobalVoices作者署名CCBY；Fed機構文字與連結。未建立新的正式來源權限。

## 程式用途

獨立分支：m3-reliable-news-discovery-20261020；來源基準：abc01cd39ff7470bcb6e8c47f50dee9b79543ce0。
只新增研究工具與聚焦測試，不修改既有Collector、owner、claim、watchdog、Frozen或H2。
程式預設沒有網路；只有明確 --cycle 與 --enable-network 才觀測，每次依序、有界並退出。
保留拒絕／無ACK狀態，不重新初始化舊RUN，不重試拒絕來源。


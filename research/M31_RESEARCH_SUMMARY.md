# M3.1 — 經濟來源恢復研究

**BOUNDED_RESEARCH_OBSERVATION_NOT_24_7**  
**NOT_LIVE_TRADING_SIGNAL**  
**GLOBAL_FIRST_SEEN_NOT_PROVEN**

狀態：**PARTIAL**。恢復可直接讀取的BLS CPI／非農就業期間值，並取得BEA PCE發布metadata。沒有恢復BLS RSS、沒有證明突發偵測，也沒有啟用正式採集。

## 實際能力

- 兩個來源家族、三個選定端點：BLS API v1兩個序列 + BEA current releases。
- 本輪不同來源記錄69筆：68個統計期間記錄（67個數值、1個明示缺值）及1個PCE公告。**不是69篇新聞或69個事件**。
- 選定端點觀測窗口UTC：2026-10-20T03:14:48.963889Z → 2026-10-20T03:46:09.518027Z。
- 重複存取：PASS。
- 直接來源GET 8次，已讀payload 220366 bytes。另有官方文件搜尋/瀏覽，後端GET數及wire bytes未量測。

|Round|GET selected|Parsed|New to experiment|Updated|Duplicates|
|---|---:|---:|---:|---:|---:|
|round_1_selection_probes|3|3|69|0|0|
|cycle_002|3|3|0|0|69|

第一輪是來源選擇probe；保存原始取得/ACK時間，解析時間另外記錄。之後才凍結M3.1計畫，第二輪依該計畫執行。這不是事先凍結的前瞻recall比較。

## 不能混淆

- BLS API只有參考期間、數值、註腳；沒有發布時間。月期間不能當成發布日，偵測延遲UNKNOWN。每筆值不是發布公告，也未自動變成OFFICIAL_CONFIRMED。
- BLS明示`-`保留null與原始註腳，不變成0；初估註腳保留。
- BEA八月Personal Income and Outlays在官方清單存在，但同輪RSS缺失。HTML精確時間是來源自報時間，不是當時HTTP可得性的證明。**PCE不是CPI**。
- 原三案例benchmark維持M3 1/3；合併仍1/3。BLS統計值不是原CPI/Employment發布URL的替代命中，PCE也不能偷換CPI案例。不是全球recall百分比。
- DOL週申請報告403，不重試；週失業保險申請也不是月度非農就業。FRED需key未測；Census未選用、未直接測試。
- 原M3收據、計畫、benchmark與repo保持；新程式只新增獨立研究模組。沒有Production/Writer/D1/Owner/Claim/H2/Frozen/交易變更。
- 只有短期有界存取證據。兩個BLS GET每30分鐘若持續24小時會超過未註冊25/day，不是正式排程方案。

## 重現

使用研究模組`research.m31_economic`不加cycle/network旗標，可離線從同一個已驗證M3.1根目錄重建投影。不要重新初始化、不要修改歷史收據。

所有公開摘要僅自產統計與官方來源連結。完整原始回應和本機診斷不納入Git發布。原始資料依BLS/BEA官方政策署名；無新聞全文、圖片或logo。

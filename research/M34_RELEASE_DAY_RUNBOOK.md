# 10/29 BEA：人工操作研究驗證 Runbook

**本文件沒有執行或預約任何未來任務。須由使用者在發布日重新明確核准一次有界觀測後，才執行標示網路的段落。** 不啟用正式 Capture、不部署、不交易。

已核對時程：2026-10-29 08:30 America/New_York（EDT）＝12:30 UTC＝台灣20:30。事件分開：Q3 GDP advance、September Personal Income and Outlays/PCE。當日時程若變更，停止，重新審查計畫，不改舊計畫硬跑。

## 0. 離線準備與停損

使用已驗證的 Windows 原生路徑；不要依賴 Codex 的 LOCALAPPDATA，該值可能指向隔離容器。先在本機核對本分支最終 SHA、白名單與交付 SHA manifest。以下初始化段只設定本機變數、顯示時鐘及執行離線檢查：

```powershell
$basePath = Join-Path $env:USERPROFILE '.codex\visualizations\2026\10\12\01a12e6d-4354-7581-a70c-69ded06240a3'
$repoPath = Join-Path $basePath 'm34_bea_release_readiness_20261020'
$studyPath = Join-Path $basePath 'm34_release_day_20261029'
$pythonPath = Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python313\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Canonical Python missing; stop' }
Set-Location -LiteralPath $repoPath
git status --porcelain=v1
if ($LASTEXITCODE -ne 0) { throw 'Git check failed' }
git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Git check failed' }
[DateTimeOffset]::UtcNow.ToString('o')
Get-Date
function Invoke-M34 {
    & $pythonPath -X utf8 -m research.m34_bea --root $studyPath @args
    if ($LASTEXITCODE -ne 0) { throw 'M34 stopped. Preserve receipts; do not retry or reset root.' }
}
Invoke-M34
& $pythonPath -X utf8 -m unittest tests.test_m34_bea -q
if ($LASTEXITCODE -ne 0) { throw 'Offline tests failed; stop' }
```

確認 Git 沒有未核准差異；核對 Windows 時鐘已同步，不能僅因輸出 UTC 就聲稱時鐘準確。確認研究目錄不是 reparse point，空間足夠、沒有其他 runner。已有 studyPath 時先讀原收據，**不得刪除或換 root 繞過 SPENT／預算**。第一次開始使用全新目錄；本輪預備證據 m34_evidence_20261020 保持原樣。

## 1. 使用者新授權後：時程／條款核對（3 GET）

```powershell
if (Test-Path -LiteralPath $studyPath) { throw 'Existing study: inspect offline; do not recreate' }
Invoke-M34 --probe terms --request-id day_terms --enable-network
Invoke-M34 --probe schedule --request-id day_schedule --enable-network
Invoke-M34 --probe rss_doc --request-id day_rss_doc --enable-network
Invoke-M34 --pin day_schedule day_terms day_rss_doc
Invoke-M34 --project
```

核對實際條款、兩項時程、RSS 文件、M34_PLAN.json 與其 SHA256。此時只能看到 PLANNED_NOT_OBSERVED；不是新聞發布成功。任何拒絕、redirect、rate limit、timeout、無法解析、未知 ACK、收據不符或條款不明都立即停止，保留完整目錄，不重試、不改 URL、不移除 reservation。

## 2. 人工發布前基準（2 GET）

建議台灣20:00左右／12:00 UTC 手動執行。不要自動排程或在本機留等待程序。

```powershell
Invoke-M34 --cycle cycle_001 --enable-network
Invoke-M34 --project --snapshot baseline_before_release
```

快照採 exclusive-write，不覆蓋。同時保留 current 與 RSS 的文章與時鐘；預期目標尚未出現，若意外已出現需停下核實。真正的 pre-release baseline 必須在12:30 UTC前完成，否則標記「未取得發布前基準」，不可補造。

## 3. 人工發布後比較（2 GET）

建議台灣20:31以後／12:31 UTC，而且同資源距前次 reservation **至少1800秒**。1800秒是本實驗保守限制，不是 BEA 公告的允許頻率／服務保證；若當日條款或 Retry-After 更嚴，停止並重新評估。

```powershell
Invoke-M34 --cycle cycle_002 --enable-network
Invoke-M34 --project --snapshot post_release
```

檢查兩個 family 分別是否 OBSERVED_ANNOUNCEMENT。RSS 缺項不能證明未發布；current list 與 RSS 均無目標時，記錄 MISS／NOT_OBSERVED，不猜 slug。新到本研究不等於全世界首次發布。metadata UPDATED 不等於統計值已更正。

## 4. 只取真實清單已列出的原始文件（最多2 GET）

以下從剛才的本機快照選 URL；不猜測10月29日尚不存在的網址。最多一個目標 family 對應一份文件；缺一就只取存在者。異常多個 URL／重複 family 要停止檢查，不以來源數量投票決定事實。

```powershell
$snapshot = Get-Content -LiteralPath (Join-Path $studyPath 'SNAPSHOTS\post_release.json') -Raw | ConvertFrom-Json
$targets = @('GDP_Q3_2026_ADVANCE', 'PIO_SEPTEMBER_2026')
foreach ($familyId in $targets) {
    $rows = @($snapshot.projection.observations | Where-Object { $_.release_family -eq $familyId })
    $urls = @($rows.source_url | Select-Object -Unique)
    if ($urls.Count -gt 1) { throw 'Ambiguous family URLs; stop' }
    if ($urls.Count -eq 1) {
        $item = $rows | Sort-Object recorded_at | Select-Object -Last 1
        $requestId = 'original_' + $familyId
        Invoke-M34 --original-url $item.source_url --list-id $item.source_list_receipt_id --request-id $requestId --enable-network
    }
}
Invoke-M34 --project --snapshot final_with_originals
Invoke-M34 --handoff
```

一般流程共9 GET（3核對＋2基準＋2發布後＋2原文），上限15 GET／5,000,000實際讀取bytes。未知 ACK按最大2MiB保守保留。每次最多2MiB；下一請求的最大回應容積必須仍放得下，可能提早停止。所有分支／namespace共享同一總預算。不要為了用完15次增加輪詢。第二次 post observation 若確有研究必要，須在同一授權範圍且再次相隔1800秒、還有預算，否則另行核准；本runbook不自動執行。

## 5. 官方命題與研究交接（離線）

以實際原文檢查 GDP 期間、advance／second／third vintage、annualized等單位；PIO要分清所得、名目支出、實質支出、PCE價格與核心價格、月比／年比。`--handoff`只自動抽取嚴格匹配的名目個人所得增加命題；GDP或不匹配敘述維持待人工核實，不代表失敗或可猜數值。歷史演練已核實8月所得666億美元／0.2%，**不是10月29日結果**。

每項核實附原文、URL、發布精度、取得時間、durable recorded時間、body/content/ACK hash、命題範圍。沒有已取得的官方文件就維持UNKNOWN。讀 `--project --as-of <實際UTC>` 時不能看到晚於as-of才記錄的修訂；沒有當時收據不能宣稱正式PIT已完成。

MacroView只能研究PREVIEW，不是Frozen；沒有具時間戳的預期資料則surprise UNKNOWN；Polymarket UNAVAILABLE；市場反應NOT_MEASURED、因果NOT_ESTABLISHED，不能推導價格方向或交易。公開摘要需另經rights／隱私發布gate，本研究branch push不是網站公開資料授權。

## 6. 結束與故障處置

每個CLI是一次性前景程序，完成即退出；沒有collector、排程或雲端服務要關閉。保留全部reservation、ACK、terminal、body、parsed、binding、plan與snapshots及各自hash。用交付方式建立manifest副本備存，金鑰／帳號資料不應出現在此研究。遇到不確定ACK或中斷，先只讀project與檔案狀態；不重新發送寫入、不重跑GET、不重建根目錄。確認仍無production capture／trading啟用。

本程序成功只證明這一次人工研究窗口；不證明24/7、全球first-seen、確切線上發布時刻、正式Frozen PIT或任何交易SLA。

# SQLite 冷啟動 Prefetch 研究 — 報告摘要

> 完整推導與每一維實驗見
> [overall_results.md](overall_results.md)、[overall_strategies.md](overall_strategies.md)、
> [overall_workloads.md](overall_workloads.md)、[README.md](README.md)。

---

## 1. 背景與問題

- SQLite 把整個資料庫存成一個 **4 KB page 的陣列**，用 B+tree 組織。
- 每筆 query 都要**從 root 走到 leaf**，沿路的 **interior page（interior node）全部都要在 memory 裡**。
- **Cold start**（剛開機、cache 是空的）時，這些 page 都得從 disk 讀，每讀一個就是一次慢速的 random I/O。

**核心問題：能不能在 first query 之前，先把這些關鍵 page 載進 memory？**

---

## 2. 實驗設定

### 測試資料庫（固定一個，所有實驗共用）

| 項目 | 數值 |
|---|---|
| Page 大小 | 4 KB |
| 總筆數 | 600,000 rows |
| 總 page 數 | 26,331 |
| 整個 DB | ~102 MB |
| **Interior page（瓶頸）** | **92 個 → 368 KB（占 0.35%）** |
| Leaf page（資料本體） | 26,239 個 → ~102 MB（占 99.65%） |

**重點：interior 只占 0.35%（368 KB），但每筆 query 都得用到。只要先載這 368 KB，就能避開 cold start 的 random I/O。**

![三種 layout 下 92 個 interior page 在檔案裡的位置](figures/out/01_page_distribution.png)

*圖 1：interior page（紅色）在檔案裡怎麼擺。**1a 原始**：散落整個 102 MB；**1b VACUUM**：略集中但仍散；**1c type-aware**：全部塞到檔頭前 400 KB，讓 prefetch 可以一口氣抓完。*

### 四種查詢情境（workload）

| 名稱 | 特性 | 像什麼 |
|---|---|---|
| **A** | 集中查少數熱門資料（Zipfian） | App 首頁、常開的聯絡人 |
| **B** | 平均亂查（uniform） | 隨機抽樣、爬蟲 |
| **C** | 只查最新加入的資料（檔尾） | 剛收到的訊息、剛拍的照片 |
| **D** | Write workload 產生器 | 模擬 DB 被持續 write |

### 怎麼量

Cold start → 清空 OS page cache → 執行 prefetch → 量 first query 花多久。

---

## 3. 嘗試的做法

分三類，可以互相搭配：

| 類別 | 策略 | 做法簡述 |
|---|---|---|
| **改 layout** | 1a 原始 / 1b VACUUM / **1c 整理過** | 改變 page 在檔案裡的物理排列 |
| **Prefetch** | 2a–2c（看結構）/ 2d–2e（看歷史）/ 2f（抄 cache） | First query 之前先載哪些 page |
| **Memory 共用** | 多 process 共用同一份 cache | 一個 process prefetch，全部受惠 |

---

## 4. 主要結果

### 4.1 各情境最佳方法一覽

同一套量測基準（7 種方法 × 3 種 layout，A/B/C 同條件）下，每個情境表現最好的方法：

| 情境 | 特性 | 最佳方法 | First query | 改善 |
|---|---|---|---:|---:|
| **A** | 熱門集中 | 抄上次 cache（記住上次熱了哪些 page，下次全載） | 305 → **16 µs** | **−95%** |
| **B** | 平均亂查 | 抄上次 cache | 464 → **17 µs** | **−96%** |
| **C** | 查檔尾新資料 | 抄上次 cache | 671 → **17 µs** | **−97%** |
| **D** | 持續 write 後（churn） | 看歷史 + 最熱 10 個 leaf node | 281 → **21 µs** | **−92%** |

> **「抄上次 cache」在沒有 memory pressure 時在各情境表現最佳**，但它要記住最多 page（約 500 個）。
> 想省 memory 時，就需要用更輕量化的策略：**A 用「prefetch 前 5 個 interior」(−54%)、
> C 用「看歷史只載用過的」(−48 ~ −83%)**，下面分項說明。

![7 種策略 × 3 種 layout 跨 A/B/C 的 first query latency 比較](figures/out/05_strategy_comparison.png)

*圖 5：每個 workload × layout 下 7 種方法的 first query latency（越短越好）。**沒有萬用解**——A 上「整理 layout + prefetch 前 5 個」就贏；C 上「看歷史」(2d/2e) 拿下；「抄上次 cache」(2f) 三 workload 通殺，但要先 dump 一份 hot set。*

### 4.2 最佳組合（Workload A）

| 做法 | First query | 改善 |
|---|---:|---:|
| 什麼都不做（baseline） | 318 µs | — |
| 只 prefetch 前 5 個 interior | 224 µs | **−30%** |
| **整理 layout + prefetch 前 5 個** | **127 µs** | **−69%** ← 結構式方法的最佳 |

![Workload A 上 layout × strategy 的效果](figures/out/02_layout_effect.png)

*圖 2：Workload A 上，**1c type-aware + layers_5** 的組合把 first query 從 404 µs 壓到 127 µs（−69%）。**單獨 VACUUM（1b）幾乎沒幫助**——要 layout + prefetch 一起做。*

### 4.3 不同情境差很多

| 情境 | 最好能改善多少 | 為什麼 |
|---|---:|---|
| **A**（熱門集中） | **−69 ~ −91%** | Leaves 自然在 cache，只剩 interior 要救 |
| **B**（平均亂查） | −49% | 每筆都打到 cold leaf，救不掉 |
| **C**（查檔尾新資料） | −54 ~ −83% | 同上，但用「看歷史」的方法可突破 |

![A/B/C 三 workload 在 clean / churned DB 上的 N-sweep plateau](figures/out/04_nsweep_plateau.png)

*圖 4：N（prefetch 多少個 interior page）對 first query 的影響。**A 在 N=5 就到 plateau**（leaves 自然熱、只剩 interior 要救）；**B/C 要到 N≈92 才壓住**（每筆都打到 cold leaf）。Churn 不改變 plateau 形狀。*

### 4.4 「看歷史」的方法最聰明（Workload C）

不是盲目載前 N 個，而是**先觀察哪些 page 真的被用到**，再只載那些：

| 做法 | 改善 | 載入次數 |
|---|---:|---:|
| 載全部 92 個 interior | −54% | 92 次 |
| **只載真正用過的 interior** | **−48%** | **4 次** ← 一樣效果，省 23 倍 |
| 再加最熱的 10 個 leaf node | **−83%** | 14 次 |

---

## 5. 關鍵發現

1. **少即是多**：載前 5 個 interior（−54%）比載全部 92 個（−31%）還好——載太多反而來不及。
2. **沒有通用 best strategy**：最適合載幾個 page，跟「資料怎麼排」「query 什麼樣」強烈相關。
3. **整理 layout 對 A 是大勝（−69%），但對 B 反而變慢**——不能無腦套用。
4. **看歷史 > 看結構**：只載真正用過的 page，4 次 load 就追平盲載 92 次的效果。
5. **動態環境下依然有效**：DB 被持續 write（5 萬筆 write ops）後，效益完全沒衰退（A 仍 −91%、C 仍 −54%）。

   ![10 個 checkpoint × 50k churn ops 下 C/A/B 三 workload 的 first query 演化](figures/out/07_churn_evolution.png)

   *圖 7：DB 被持續 write 5 萬筆 ops 後，static t=0 hot pages 在 C/A/B 三種 workload 上都不衰退。B 上 access-pattern 跟盲載前 N 個沒差別（沒 hot leaf 可挑），但也不失效。*

6. **Memory 吃緊也撐得住**：**DB ~102 MB、RAM 用 cgroup `MemoryMax=20M` 砍到 20 MB**（約 working set 的 1/5、強制 trigger page reclaim ~80%），first query 的改善幾乎不受影響——但 avg latency 跟 majflt 在某些配置會被打。
   - **First query**：63 個 cell 的「20M / 不限」比值**全部落在 0.90–1.19**，因為 first query 只摸到少數 page、不在 reclaim 路徑上。
   - **後續 query**：2f SLRU 在 1a/1c 上的 preload **被 reclaim 完整清掉**（majflt 從 0 → 180，avg 從 1.50 µs 退回 1.78 µs）。
   - **唯一全保留組合：1b VACUUM + 2f SLRU** ——VACUUM 把 DB 壓緊到 ~100 MB，working set 剛好塞進 20M cgroup、preload 不被 evict（majflt 維持 0、avg 1.50 µs）。

   ![RAM-pressure heatmap (20 MB cgroup vs unlimited)](figures/out/06_ram_pressure_heatmap.png)

   *圖 6：把可用 RAM 砍到 20 MB（A/B/C × 3 layout × 7 策略 = 63 個 cell）。每 cell 的「20M / 不限」比值**全部落在 0.90–1.19**——memory pressure 下 first query 仍保住，但 avg/majflt 視 layout 與策略而定。*

7. **多 process 共用免費加倍**：一個 process 做 prefetch，所有共用同一份 cache 的 process 都受惠。

   ![Multi-process prefetch cadence 對 first query latency 的影響](figures/out/08_cadence_comparison.png)

   *圖 8：writer + prefetcher + probe 三個 thread 的實驗。Prefetcher 每 1 秒掃一次能把 first query 從 295 µs 壓到 19 µs（−94%）；每 30 秒幾乎等於沒跑。**經驗法則：cadence ≤ query 間隔 才可靠 warm**。*
---

## 6. 實務建議

| 情境 | 建議做法 | 預期改善 |
|---|---|---|
| 熱門資料集中（最常見） | Prefetch 前 5 個 interior | −54% |
| 想追求極致 | 先整理 layout，再 prefetch 前 5 個 | −69% |
| 平均亂查 / 查檔尾新資料 | 看歷史，只載用過的 + 最熱 10 個 leaf node | −83% |
| 多 process 共用 DB | 開 shared memory，背景定時 prefetch | 成本固定、效益乘以 process 數 |

---

## 7. 詳細資料位置

| 想看什麼 | 去哪 |
|---|---|
| 每一維實驗的完整數字（18 維） | [overall_results.md](overall_results.md) |
| 每個策略的原理與狀態 | [overall_strategies.md](overall_strategies.md) |
| 四種 workload 的定義 | [overall_workloads.md](overall_workloads.md) |
| 完整研究故事（按週） | [README.md](README.md) |
| Figures | [figures/out/](figures/out/) |

## 總結

SQLite cold start 後 first query 很慢，因為要先從 disk 讀進那 **92 個關鍵的 interior page**。
我們用 **prefetch（提前 load）** 把它們先放進 memory，最高可把 first query
**從 318 µs 降到 127 µs（−69%）**，而且這個方法在 DB 持續被 write、memory 吃緊、
多 process 共用的情況下都站得住。

---

## 附錄 — 補充圖表

![前 50 筆 query 的累計 latency（cold→warm 過渡區）](figures/out/03_latency_cdf.png)

*圖 3：前 50 筆 query 的累計時間。Prefetch 把「cold→warm」的過渡時間整段壓掉；第 50 筆之後所有方法都收斂到 ~1.5 µs/query。*

![Workload Z：低 id hotspot 的 Zipfian 變體](figures/out/09_zlowkey_nsweep.png)

*圖 9：把 hotspot 從 [8, 99997] 移到 [1, 1000]（低 id 區段）的 robustness check。N-sweep 形狀跟 Workload A 同形（差 ≤ 5pp）——「hotspot 落在哪個 key 區段」不是 prefetch 效益的主要變因。*

![Interior:leaf 比例掃描（3a/3b ratio variants）](figures/out/10_ratio_sweep.png)

*圖 10：Load interior 跟 hot leaf 的比例（K=10/40/50/92/100/500）。**K 才是主要變因，ratio 不是**——A 上 K=500 才追平、C 上 K=10 就 saturate。*

---

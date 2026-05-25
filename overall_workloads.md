# Overall Results — Workload 説明

這個檔案說明 repo 裡**現階段實際使用**的 workload，以及每個 workload 對應到哪個實驗、想模擬什麼情境。

所有 workload 都跑在同一個 reference DB 上 (`testdb_builder.py` 產生的
`items(id PK, k1, k2, payload BLOB(100))`，**600,000 rows**，~102 MiB，26,331 ×
4 KB pages，其中 92 個 interior pages)，這樣不同 workload 的結果可以橫向比較。

Workload 格式（`benchmark_harness` 讀的）每行一個 op：
```
read <id>
update <id>
insert <id>
scan <id> <len>
readmodifywrite <id>
```

---

## Workload A — Zipfian Point Read（YCSB-C 風格）

**檔案：** [benchmark_harness/workloads/workloadc.txt](benchmark_harness/workloads/workloadc.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [8, 99997]（只打 DB 前 1/6 的 id 區段）
**分佈：** 強 Zipfian skew
- 100,000 次查詢只觸及 **23,253 個 unique key**（76% 是 repeat query）
- **Top 100 個熱 key 吃掉 42.3% 的流量**
- 最熱的單一 key (`id=74406`) 被查 **7,752 次**（單 key 佔總流量 7.75%）

**模擬什麼：** 真實 App 的「熱資料反覆被打」情境 — 使用者常開的聯絡人、最近瀏覽
的相簿、首頁那幾筆 item。少數熱 key 把對應 leaf page 撐成熱頁，**leaf 自然會
warm；唯一還是 cold 的是 interior page**。所以這個 workload 是 prefetch 的最佳
舞台，會放大 interior prefetch 的效益。

**用在哪：**
- `prefetch_vacuum/` 第 9–11 週的全部實驗（baseline / range / perpage / layers N）
- `layout_rewriter/` 的 type-aware vacuum 端到端驗證（-69%）
- `layout_rewriter/runs/` 的 1b VACUUM 補測、N sweep × {orig, vacuum} 全矩陣（找到 A vac 新甜蜜點 N=20）
- `prefetch_slru/` 的 2f SLRU 驗證（orig + vacuum DB，first-q -94%、全 workload -39%）

**為什麼這個 workload 會給「-54%」、「-69%」、甚至「-94%」這種看起來很漂亮的
數字：** 因為冷啟動成本被拆成「interior fault + leaf fault + CPU」，Zipfian 下
leaf 部分被反覆查詢拉進 cache，**剩下的瓶頸只有 interior**，prefetch 一解就
見效。而 2f SLRU 連 leaf 一起 preload，連那點 leaf cold fault 都消掉。

---

## Workload B — Uniform Random Point Read

**檔案：** [benchmark_harness/workloads/workload_uniform.txt](benchmark_harness/workloads/workload_uniform.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [1, 99999]（同 Workload A 的 1/6 區段）
**分佈：** 均勻
- 100,000 次查詢觸及 **63,138 個 unique key**（多數查詢是新的）
- 最熱的 key 也只被查 7–8 次
- 每 10k id 區段平均 ~10,000 次（誤差 < 5%）

**模擬什麼：** 沒有熱點的 OLTP/批次掃描情境，例如「按 id 一筆筆檢查」、隨機
sampling、爬蟲式存取。**每筆 query 都打到沒看過的 leaf**，leaf fault 不可避免。

**用在哪：**（最初是對照組，後來變成完整實測 workload）
- `layout_rewriter/runs/` 的 1b VACUUM 補測、1c type-aware 補測、N sweep × {orig, vacuum} 全矩陣
  - **發現一**：B 上 N sweep 從 N=5 開始全 plateau（沒有 A 的 U 型曲線）
  - **發現二**：ta + layers_5 在 B 上反而 +8%（不是 universal best）
- `prefetch_slru/` 的 2f SLRU 驗證（orig + vacuum DB，first-q -94%、全 workload -38%）
- 原始定位：當 Workload A 量出「prefetch 省了 54%」，B 回答「這效益只在熱點下
  才有意義嗎」 — 答案是 prefetch 仍然有效，但比例會被「無法被解決的 leaf
  fault」攤薄

---

## Workload C — High-key Uniform Read（churn 後段查詢）

**檔案：** [prefetch_churn/workloads/page_churn_benchmark_high.txt](prefetch_churn/workloads/page_churn_benchmark_high.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [590000, 609999]（**只打 DB 末段 20k id**，含 churn 後新增的 id）
**分佈：** 均勻覆蓋這 20k 個 id（剛好每個 id 平均被打 5 次）

**模擬什麼：** 「新加入的資料馬上被讀取」— 例如剛收到的訊息、剛拍的照片、剛
push 的 commit。**重點不是熱點，而是 id 落在哪個 file region**。Churn 過程持續
INSERT 會把新資料放在檔尾，這個 workload 就在量「檔尾新資料的冷啟動 latency
怎麼隨 churn 累積而漂移」。

**用在哪：**
- `prefetch_churn/` 的 10 個 checkpoint：每個 checkpoint 之間先用 Workload D
  製造寫入壓力，然後 drop cache，再跑這個 workload 量 cold-start latency
  - 原本只跑 N=5（第四維）
  - **後續 N sweep 補測**：[`prefetch_churn/runs_nsweep/`](prefetch_churn/runs_nsweep/) 跑了
    N=0/1/5/10/20/46/92 × 10 checkpoints，見 [overall_results.md 第十維](overall_results.md#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)
- `layout_rewriter/runs/` 的 1b VACUUM、1c type-aware、N sweep × {orig, vacuum}
  全矩陣
  - **關鍵發現**：C 上 layers_N 必須 N=92（載全部 interior）才有 -46% 改善，
    N≤46 只有 ~15%。原因：C 走的 interior path 不在 file 前段，按 offset 排
    top-N 完全選錯 page。**這直接證明「layers_N 是 zipfian-friendly 啟發式」**
  - **churned DB 上同樣的形狀**（第十維）：N=92 -54%、N≤46 plateau ~10%
- `prefetch_slru/` 的 2f SLRU 驗證（C 上 hot set 只 1.6 MB，prefetch 開銷
  只 1.9 ms vs A/B 的 7.5 ms — 是 2f 的甜蜜情境）

**為什麼選 high-key 而不是低 key：** 因為 prefetch_churn 想觀察 layout 隨寫入
漂移的效果，而新 interior page 都會配在檔尾（id 590k+），打這段最能看到 layout
惡化的影響。**意外副作用**：因 leaves 高度集中在檔尾，C 也成了 2f SLRU 的最
小 hot set 對照點。

---

## Workload D — Mixed Write-heavy Churn Generator

**檔案：** [prefetch_churn/workloads/page_churn_write.txt](prefetch_churn/workloads/page_churn_write.txt)
**規模：** 100,000 ops，混合操作
**Op 組成：**

| op | 次數 | 佔比 |
|---|---:|---:|
| `update` | 30,000 | 30% |
| `insert` | 20,000 | 20% |
| `read` | 20,000 | 20% |
| `readmodifywrite` | 20,000 | 20% |
| `scan <len>` | 10,000 | 10% |

**Key 行為：**
- `insert` 從 id = 600,001 開始往上長（DB 原本 600k 筆，所以每 batch 都是真
  新資料、不是 overwrite）
- `update` / `read` / `rmw` / `scan` 都打既有 id 範圍

**模擬什麼：** **不是用來測 latency 的**。它是 churn generator — 製造大量
INSERT/UPDATE/DELETE 的寫入壓力，讓 SQLite freelist 重新分配、interior pages
分裂、layout 隨時間漂移。

**用在哪：** `prefetch_churn/` 的 checkpoint 之間。每個 checkpoint 之間執行
5,000 ops 的這個 workload（取前 5,000 行），跑 10 次累積 50,000 ops。然後在每個
checkpoint 用 Workload C 量 cold-start latency，看「prefetch 在被 churn 過的
layout 上還剩多少效益」。

---

## Workload 與實驗的對照表

| 實驗 | 用的 workload | 想回答的問題 |
|---|---|---|
| `prefetch_vacuum/` (Week 9–11) | A (Zipfian) | Prefetch interior pages 在熱點 workload 下能省多少？甜蜜點是 N=幾個 page？|
| `layout_rewriter/` (type-aware vacuum 端到端) | A (Zipfian) | 把 interior 重排到檔頭，能不能救回 prefetch 效益？(-69%) |
| `layout_rewriter/runs/` (1b VACUUM × B/C) | B + C | VACUUM 對 baseline 和 prefetch 的影響在非 Zipfian workload 上是什麼樣 |
| `layout_rewriter/runs/` (1c type-aware × B/C) | B + C | ta layout 是否 universal best？(答案：B 上反效果) |
| `layout_rewriter/runs/` (N sweep × A/B/C × {orig, vacuum}) | A + B + C | 「N=5 甜蜜點」是 zipfian-friendly 還是 universal？(答案：zipfian-only) |
| `prefetch_slru/` (2f SLRU × A/B/C × {orig, vacuum}) | A + B + C | mincore-dumped resident set preload 在三種 workload 的效益 (first-q -94%、全 workload A/B -38%、C -7%) |
| `prefetch_churn/` 量測 (N=5 only) | C (high-key uniform) | Layout 隨 churn 漂移後，prefetch 效益怎麼變？|
| `prefetch_churn/runs_nsweep/` (N=0,1,5,10,20,46,92) | C (high-key uniform) | churned DB 的 N sweep 形狀是否跟乾淨 DB 一致？(答案：完全一致，N=92 -54%) |
| `prefetch_churn/` churn 生成 | D (mixed write) | 製造真實的 layout 漂移壓力（不量 latency）|
| `multiprocess/` | 不用 workload（只測 residency / RSS）| MAP_SHARED 是否真的跨 process 共享 page cache？|

---

## 為什麼需要這四種 workload，而不是只用一個

不同 workload 拆解 cold-start latency 的不同 component，缺一不可：

```
[Interior page fault]  +  [Leaf page fault]  +  [SQLite CPU]
        ↑                          ↑
   prefetch 能解決              prefetch 解決不了
                                （workload-dependent）
```

- **Workload A (Zipfian)** 把「leaf fault」這項壓低（leaf 自然熱），讓 interior
  fault 成為唯一瓶頸 → 量出 prefetch 的**上界效益**
- **Workload B (uniform)** 讓「leaf fault」這項變最大，prefetch 只能解決剩下
  的 interior 部分 → 量出 prefetch 的**下界效益**
- **Workload C (high-key uniform)** 同 B 的分佈但鎖定檔尾，跟 Workload D 配合 →
  量「layout 漂移」隨時間的影響
- **Workload D** 不為了 latency 而存在，純粹是製造寫入歷史，讓 layout 偏離
  testdb_builder 剛建好的乾淨狀態

---

## 已知缺口（workload 層級）

- ~~**Zipfian「low-key hotspot」變體**~~：已補（見
  [overall_results.md 第十三維](overall_results.md#第十三維--zipfian-low-key-hotspot-variantworkload-z--n-sweep--3-layouts)）。
  新增 **Workload Z (Zipfian low-key)**：α=0.99, keys [1, 1000], top key 拿走
  13% 讀。結論：跟 mid-key Workload A 結果幾乎同形（差 ≤ 5pp），**「熱點落在哪
  個 key 區段」對 prefetch 效益不是主要變因**；layout 才是。
  「[99k, 100k] high-key hotspot」邏輯上與 Workload C 重疊（後者是 high-key
  uniform），不另跑。
- ~~**N 在 churned DB 上的曲線**~~：已補（見
  [overall_results.md 第十維](overall_results.md#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)）。
  結論：churned DB 上 N≤46 在 -10% 附近 plateau，**N=92 帶來 -54% 改善並在
  10 個 checkpoint 上全部壓制其他 N**，跟乾淨 DB 上的形狀完全一致。Churn 不
  改變「layers_N 在 C 上需要 N=92」的根本問題。
- **RAM 緊縮場景的 workload**：目前的 A/B/C 都是 ~16 MB hot set in unlimited RAM。
  缺一個 cgroup 限制下、hot set > RAM 的 workload，才能看出 2f SLRU vs
  access-count（2d/2e）的差別。

> 策略層級的缺口（2d/2e access-pattern、2f × layout 1c）見
> [overall_results.md](overall_results.md) 的「還沒跑的策略 × workload 組合」表。

## 已完成的覆蓋（A/B/C 三維 × 全策略矩陣）

對照原本只有「A → prefetch_vacuum + layout_rewriter; C → prefetch_churn; B 只
是對照組」的設計，目前實際已跑：

| | A (Zipfian) | B (Uniform) | C (high-key) |
|---|---|---|---|
| **Layout 1a (orig)** | ✅ 全策略 | ✅ 全策略 | ✅ 全策略 |
| **Layout 1b (VACUUM)** | ✅ baseline + range/perpage/layers_5 + **N sweep + 2f SLRU** | ✅ 全策略 | ✅ 全策略 |
| **Layout 1c (type-aware)** | ✅ baseline + range/perpage + **N sweep** + 2f SLRU | ✅ baseline + range/perpage + **N sweep** + 2f SLRU | ✅ baseline + range/perpage + **N sweep** + 2f SLRU |
| **Churn 漂移** | — | — | ✅ 10 checkpoints × **N sweep {0,1,5,10,20,46,92}** |

B 早就不再只是「對照組」 — 它是 prefetch 失敗模式（leaf fault 主導）和 ta
layout 反效果（+8%）的主要證據來源。

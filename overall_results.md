# Overall Results — 策略 × Workload 結果矩陣

對照 [overall_workloads.md](overall_workloads.md) 裡定義的四個 workload。本檔
列出**目前實際跑過的策略對每個 workload 的結果**，以及還沒測的組合。

> **主表**只列原始 prefetch_vacuum 時期跑過的 Workload A + Workload C。Workload
> B 的全策略結果見[第五維](#第五維--策略-4-2f-slru)（2f SLRU）、
> [第六維](#第六維--策略-1b-sqlite-vacuum--workload-b--c)（1b VACUUM）、
> [第七維](#第七維--策略-1c-type-aware-layout--workload-b--c)（1c type-aware）、
> [第八維](#第八維--2c-layers_n-sweep--workload-b--c原始-layout)（N sweep）、
> [第九維](#第九維--layout-1b-vacuum-補測n-sweep--2f-slru--abc)（vacuum × N sweep + 2f）、
> [第十維](#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)（churned DB × N sweep）、
> [第十一維](#第十一維--2f-slru--layout-1c-type-aware)（2f SLRU × type-aware layout）、
> [第十二維](#第十二維--n-sweep--layout-1c-type-aware--abc)（type-aware layout × N sweep — 完成跨三 layout 矩陣）、
> [第十三維](#第十三維--zipfian-low-key-hotspot-variantworkload-z--n-sweep--3-layouts)（Zipfian low-key hotspot variant，新增 Workload Z）。
> Workload D 是 churn generator，沒有自己的 latency 結果。
>
> 不同實驗用的 cold-start 機制不同（`sudo drop_caches` vs
> `posix_fadvise(POSIX_FADV_DONTNEED)`），絕對 µs **不能跨表比較**，但
> 同一表內的相對改善百分比是可靠的。每節都標明資料來源。

---

## 主表 — strategy × workload（base layout、median latency）

| 策略 | Workload A（Zipfian point-read） | Workload C（high-key uniform read） |
|---|---|---|
| **baseline**（no prefetch） | **73 µs** first-query latency | **4,918 µs** first-query latency |
| **range**（merge contiguous interior pages, 1 madvise per range） | **54 µs**（-27%）<br>87 syscalls, prefetch 開銷 2.2 ms | _未測_ |
| **perpage**（每個 interior page 一次 madvise） | **48 µs**（-34%）<br>92 syscalls, prefetch 開銷 2.9 ms | _未測_ |
| **layers_5**（前 5 個 interior page by offset） | **33 µs**（-54%） ← 甜蜜點<br>5 syscalls, prefetch 開銷 94 µs | **5,130 µs**（+4% — baseline 時略差）<br>但隨 churn 累積反轉為 **-10%**（見下節）|

**資料來源：**
- Workload A 來自 [prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv)（Week 9–11，原始 layout，`sudo drop_caches`）
- Workload C 來自 [prefetch_churn/results/](prefetch_churn/results/)（10 checkpoints，每 checkpoint 之間用 Workload D 製造 5,000 ops 寫入壓力）

**讀這張表的兩件事：**
1. **prefetch 對 Workload A 大勝**（最高省 54%），對 Workload C 在乾淨 DB 上沒效益（甚至略差）。差異在於 Workload A 的 leaf 被反覆查詢自然變熱，interior 是唯一瓶頸；Workload C 每筆都打 cold leaf，prefetch 解決不了 leaf 那塊。
2. **越多 prefetch 不一定越好**：perpage 載 92 個 page 比 layers_5 只載 5 個還慢。`madvise(MADV_WILLNEED)` 是非同步的，做太多 syscall 反而讓 OS 來不及在第一筆 query 之前載完。

---

## 第二維 — Layout 對 strategy 的放大效果（Workload A only）

同一個 Workload A，但 DB layout 不同。**這張是 [layout_rewriter/](layout_rewriter/) 的端到端驗證結果**（`posix_fadvise` 冷啟動，3 reps median）：

| Layout | scatter | baseline | range | perpage | **layers_5** |
|---|---:|---:|---:|---:|---:|
| 原始 DB | 0.96 | 318 µs | 370 µs | 319 µs | 224 µs |
| 跑完 SQLite VACUUM | **1.13** ← 變更散 | 333 µs | 330 µs | 338 µs | 234 µs |
| **跑完 layout_rewriter（type-aware）** | **0.00** | 404 µs | 387 µs | 273 µs | **127 µs** ← 全局最佳 |

**相對於該 layout 自己的 baseline：**

| Layout | range | perpage | **layers_5** |
|---|---:|---:|---:|
| 原始 | +16% | +0% | -30% |
| post-VACUUM | -1% | +2% | -30% |
| **post-layout_rewriter** | -4% | -33% | **-69%** |

**這張表回答了 README 第 9 章列的核心研究問題：「Type-aware VACUUM 能不能把
prefetch 效益從 -9% 救回 -54%」 — 答案是：可以，而且超越，推到 -69%。**

副作用：
- **`range` 在 type-aware layout 上 syscall 從 87 → 1**（4.5× 快），但 kernel
  readahead 是 bounded，1 個 `MADV_WILLNEED` 只實際載入 32/92 pages → range
  策略在任何 layout 下都不是好選擇
- **type-aware layout 的 baseline 反而變慢**（318 → 404 µs），因為 leaf 被
  推到高 offset，第一個 cold leaf fault 跑得更遠。但 prefetch 一啟用就完全
  壓過這個 penalty

資料來源：[layout_rewriter/results/results_summary.csv](layout_rewriter/results/results_summary.csv)

---

## 第三維 — N sweep（Workload A，原始 layout，找甜蜜點）

| N（prefetch 幾個 interior page） | syscalls | prefetch 開銷 | first-query latency | 改善 |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 73 µs | baseline |
| 1 | 1 | 35 µs | 38 µs | -48% |
| **5** | **5** | **94 µs** | **33 µs** | **-54%** ← 甜蜜點 |
| 10 | 10 | 273 µs | 44 µs | -39% |
| 20 | 20 | 607 µs | 35 µs | -53% |
| 46 | 46 | 1,173 µs | 41 µs | -45% |
| 92 (= 全部 interior) | 92 | 2,229 µs | 50 µs | -31% |

**U 型曲線**：prefetch 太少（N=1）上層 interior 載到了但中下層還沒；prefetch
太多（N=92）syscall 本身就吃掉 2.2 ms，OS 來不及在 query 開始前載完。**N=5**
是 syscall overhead 和 coverage 的最佳折衷。

資料來源：[prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv) Week 10

---

## 第四維 — Workload C 隨 churn 漂移（10 checkpoints）

`prefetch_churn` 設計：同一個 DB，每個 checkpoint 之間用 Workload D 跑 5,000
ops 製造 layout 漂移，然後 drop cache → 跑 Workload C → 量 latency。

| Checkpoint（累積寫入 ops）| no_prefetch first-query | layers_5 first-query | layers_5 改善 |
|---:|---:|---:|---:|
| baseline (0) | 4,918 µs | 5,130 µs | +4% |
| ck001 (5k) | 4,511 µs | 5,398 µs | +20% ← prefetch 反而傷害 |
| ck002 (10k) | 5,950 µs | 4,554 µs | -23% |
| ck003 (15k) | 9,534 µs | 7,037 µs | -26% |
| ck004 (20k) | 6,574 µs | 5,385 µs | -18% |
| ck005 (25k) | 5,709 µs | 7,055 µs | +24% |
| ck006 (30k) | 7,319 µs | 6,179 µs | -16% |
| ck007 (35k) | 6,924 µs | 6,696 µs | -3% |
| ck008 (40k) | 6,816 µs | 6,795 µs | -0% |
| ck009 (45k) | 7,384 µs | 6,323 µs | -14% |
| ck010 (50k) | 6,892 µs | 6,300 µs | -9% |
| **平均**（ck001-010） | **6,661 µs** | **6,174 µs** | **-7%** |

**單筆 noise 很大**（ck001 +20%、ck003 -26%），但累積 10 個 checkpoint 平均下來
prefetch 仍然省 ~7%（絕對省 ~487 µs/query）。對照 Workload A 的 -54%，這裡的
百分比看起來小，但**絕對省的時間反而多**（A 省 40 µs vs C 省 487 µs），因為
baseline 本來就被 leaf cold fault 拉到 5,000+ µs 起跳。

> **後續補測（第十維）**：本節只跑 N=5 一個 N 值。第十維把 N=1/10/20/46/92
> 全跑過（用 `posix_fadvise` harness、絕對 µs 不能跨表比）— 結論是 churned
> DB 上 N=92 帶來 -54% 改善，且在所有 10 個 checkpoint 上都壓制其他 N。N=5
> 在第十維的 harness 下省 ~10.6%（方向跟本節 -7% 一致）。

資料來源：[prefetch_churn/results/](prefetch_churn/results/)

---

## 第五維 — 策略 4 (2f SLRU)

新策略：跑完一次 workload 後**不要 evict**，直接用 `mincore()` dump 當下 OS
page cache 裡的所有 resident page，存成 `hotpages.csv`。下次 cold start 時對
每個 resident page 一一呼叫 `madvise(MADV_WILLNEED)`。

對照**三個 workload**：A (Zipfian、`workloadc.txt`)、B (Uniform、
`workload_uniform.txt`)、C (high-key uniform、`page_churn_benchmark_high.txt`)，
原始 layout，3 reps median，`posix_fadvise(POSIX_FADV_DONTNEED)` 冷啟動。

> Layout 1b (VACUUM) 版本見 [第九維](#第九維--layout-1b-vacuum-補測n-sweep--2f-slru--abc)，
> Layout 1c (type-aware) 版本見 [第十一維](#第十一維--2f-slru--layout-1c-type-aware)。
> 結論預告：2f SLRU 在三個 layout 上 first-q 都是 13–16 µs（layout-agnostic）。

### Hot set（warmup 後 resident 的 page 分佈）

| Workload | 總 resident | leaf_table | leaf_index | interior_table | interior_index |
|---|---:|---:|---:|---:|---:|
| **A (Zipfian)** | 4,048 | 3,328 | 702 | 10 | 8 |
| **B (Uniform)** | 4,122 | 3,331 | 775 | 10 | 6 |
| **C (high-key)** | **420** | 357 | 59 | 2 | 2 |

A、B 打 id ∈ [1, 100k]（DB 前 1/6 區段），所以 touched leaf 集合大致相同，
hot set 各 ~16 MB。C 打 id ∈ [590k, 610k]（高度集中在 20k 區段、又有半數
落在 600k 後的不存在 id），leaf 高度共享 → **hot set 只有 1.6 MB（10× 小）**，
這直接決定了 2f 的 prefetch overhead 縮水到 1/4。

### Latency 矩陣

| Workload | 策略 | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise 次數 |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | baseline | 251 | 4.11 | 411 | 0 | 0 |
| A (Zipfian) | layers_5 | 133 | 4.13 | 412 | 15 | 5 |
| A (Zipfian) | **2f SLRU** | **14** | **2.50** | **249** | 7,255 | 4,048 |
| B (Uniform) | baseline | 255 | 4.13 | 413 | 0 | 0 |
| B (Uniform) | layers_5 | 137 | 4.11 | 411 | 15 | 5 |
| B (Uniform) | **2f SLRU** | **15** | **2.55** | **255** | 7,478 | 4,122 |
| C (high-key) | baseline | 250 | 2.62 | 262 | 0 | 0 |
| C (high-key) | layers_5 | 185 | 2.66 | 266 | 13 | 5 |
| C (high-key) | **2f SLRU** | **16** | **2.45** | **245** | **1,881** | **420** |

### 與 baseline 比的相對改善

| Workload | 策略 | first-q 改善 | 全 workload 總時間改善 | 端到端 cold start (prefetch+first-q) |
|---|---|---:|---:|---:|
| A (Zipfian) | layers_5 | -47% | ≈ 0% | 148 µs（vs 251 baseline，**-41%**）|
| A (Zipfian) | **2f SLRU** | **-94%** | **-39%** | 7,269 µs（**比 baseline 慢 29×**）|
| B (Uniform) | layers_5 | -46% | ≈ 0% | 152 µs（vs 255 baseline，**-40%**）|
| B (Uniform) | **2f SLRU** | **-94%** | **-38%** | 7,493 µs（**比 baseline 慢 30×**）|
| C (high-key) | layers_5 | -26% | ≈ 0% | 198 µs（vs 250 baseline，**-21%**）|
| C (high-key) | **2f SLRU** | **-94%** | **-7%** | 1,897 µs（**比 baseline 慢 7.6×**）|

### 六個發現

1. **第一筆 query 上 2f 把 layers_5 打到地上**（-94% vs -26~47%）在所有
   workload 都成立。SLRU 把全部 touched leaf prefetch 進來，第一筆不管打哪個
   id 都打到熱 leaf；layers_5 只 prefetch interior，leaf 還是 cold-fault。
2. **2f 的 prefetch 開銷直接由 hot set 大小決定**：A/B 4,000+ syscalls →
   7.5 ms；**C 只 420 syscalls → 1.9 ms（4× 便宜）**。C 端到端 cold start 從
   A/B 的「慢 30×」改善到「慢 7.6×」—— 仍是退步，但差距大幅縮小。
3. **全 workload 改善幅度跟 baseline 的 avg-q 走**：A/B 的 baseline avg-q
   是 4.1 µs（每筆 query 都要 cold-fault leaf），2f 把它壓到 2.5 µs →
   全 workload 省 38~39%；C 的 baseline avg-q 已經是 2.62 µs（leaves 已經
   高度集中、disk seek 路徑短），2f 把它壓到 2.45 µs → 全 workload **只省 7%**。
4. **C 上 layers_5 也大幅退化**（-26% vs A/B 的 -46~47%）。確認先前觀察：
   layers_5「按 file offset 排前 5」對 file-tail workload 命中率低，因為
   query 走的 interior 不在全局上層。
5. **A 和 B 對 2f 沒差**（first-q 14 vs 15 µs）。原本以為 SLRU 在 skewed 上
   會輸給 access-count（無法區分 hot degree），實測一樣。原因：hot set
   (~16 MB) 全塞得進 RAM，沒有「該丟誰」的競爭，frequency 資訊用不上。
6. **2f 在 C 上的「working-set preload」效益大幅縮水**：A/B 全 workload 省
   38%（每筆都解決 leaf fault），C 只省 7%（leaves 已經幾乎共享同個 disk
   region，沒有多少 cold fault 可解）。**2f 的價值跟 hot set 的「leaf
   spread」成正比** —— 越分散，preload 收益越大。

資料來源：[prefetch_slru/results/results_summary.csv](prefetch_slru/results/results_summary.csv)

---

## 第六維 — 策略 1b (SQLite VACUUM) × Workload B / C

`prefetch_vacuum` 早期只在 Workload A 上跑過 VACUUM 對 layout 的影響（scatter
0.96 → 1.13、layers_5 改善退化）。本節補上 **B (Uniform) 和 C (high-key
uniform)** 在同一個 `posix_fadvise` cold-start harness、4 個 prefetch 策略下
的對照（3 reps median）。

兩個 DB：
- `test.db` — 600k rows 原始 layout（scatter 0.96）
- `test_vacuum.db` — 對 `test.db` 跑過 `VACUUM;` 的結果（scatter 1.13、檔案
  從 107.8 MB 縮到 104.9 MB）

### Latency 矩陣（first-query µs）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | vacuum | 503 | 328 (-35%) | 325 (-35%) | **250 (-50%)** |
| **C (high-key)** | orig | 467 | **342 (-27%)** | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | vacuum | 437 | **368 (-16%)** | 384 (-12%) | 408 (-7%) |

百分比都是「同 DB baseline 為比較基準」。

### VACUUM 對 baseline 的影響（不算 prefetch）

| Workload | orig baseline | vacuum baseline | VACUUM 帶來的變化 |
|---|---:|---:|---:|
| **A (Zipfian)** | 318 µs | 333 µs | **+5%（變慢）** |
| **B (Uniform)** | 463 µs | 503 µs | **+8%（變慢）** |
| **C (high-key)** | 467 µs | 437 µs | **-6%（變快）** |

A 數據取自 [layout_rewriter/runs/matrix_results.csv](layout_rewriter/runs/matrix_results.csv)
+ [matrix_vacuum_results.csv](layout_rewriter/runs/matrix_vacuum_results.csv)，
是同一個 harness 量出來的，可直接比較。

### 四個發現

1. **VACUUM 對 baseline 的方向 workload-dependent**：A 和 B（打 id 低段）變
   慢 +5~8%，因 VACUUM 後 interior 被推到更後面、低段 leaf 對應的 interior
   walk 路徑更分散；C（打 id 高段）反而變快 -6%，因為高段 leaf 在原 layout
   上本來就靠檔尾，VACUUM 把整個檔壓緊後 high-key region 的 seek 距離縮短。
2. **VACUUM 沒有殺死 layers_5 在 B 上的效益**（-47% → -50%）。和 README 第
   9 章的「VACUUM 把 layers_5 從 -54% 打到 -9%」現象不一致 —— 那次是
   `sudo drop_caches` + leaf 自然熱的 Workload A，瓶頸全在 interior fault；
   B 上 leaf 都是 cold fault，interior 那點 scatter 變化被攤平。
3. **Workload C 翻轉了 prefetch 策略排名**：range/perpage **打敗** layers_5
   （orig: 342 vs 406、vacuum: 368 vs 408）。原因：C 只打 [590k, 610k] 區
   段，相關 interior 不在「按 file offset 排前 5」裡 —— layers_5 prefetch 的
   是全局上層 interior，但 query 走的 interior path 在檔案中段。需要 range/
   perpage 把**所有** interior 都載入，才能覆蓋到 C 真正會 traverse 的那幾頁。
4. **range/perpage 在 vacuum DB 上反而更有效**（B：-24% → -35% / -19% → -35%）。
   推測是 VACUUM 把 interior 分布拉開後，readahead 路徑變得更線性，少了一些
   被中間 leaf 切碎的 wasted readahead。

### 結論

- **1b VACUUM 不是 universal bad**：在 high-key 讀取場景（Workload C）反而
  讓 baseline 變快 6%；在 leaf-cold-heavy 的 B 上不會殺掉 prefetch 效益。
- **「VACUUM 打到 -9%」是 A 專屬效應**，不能推廣到其他 workload。
- **layers_5 不是萬靈丹**：在 Workload C 這種只打 file region 的 workload 上，
  「按 offset 排前 N」的啟發式會選錯 page，需要改用 range/perpage 或未來的
  access-pattern 排序（2d/2e）。

資料來源：[layout_rewriter/runs/matrix_1b_bc_results.csv](layout_rewriter/runs/matrix_1b_bc_results.csv)
+ [results_1b_bc_summary.csv](layout_rewriter/runs/results_1b_bc_summary.csv)

---

## 第七維 — 策略 1c (Type-aware layout) × Workload B / C

`layout_rewriter` 把所有 interior pages 重排到 file 開頭（pages 2..93 連續），
scatter 0.96 → 0.0001。先前只在 Workload A 上量過（-69% on layers_5）。本節
補上 **B (Uniform) 和 C (high-key uniform)** 在同一 harness 上的對照。

DB：`test_typeaware.db` — 對 `test.db` 跑過 [layout_rewriter](layout_rewriter/layout_rewriter.c)，
`PRAGMA integrity_check` 通過。

### Latency 矩陣（first-query µs，3 reps median）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **A (Zipfian)** | orig | 318 | 370 (+16%) | 319 (+0%) | **224 (-30%)** |
| **A (Zipfian)** | **ta** | 404 | 387 (-4%) | 273 (-32%) | **127 (-69%)** ← 全局最佳 |
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | **ta** | 408 | 366 (-10%) | 352 (-14%) | **440 (+8%)** ← 反效果 |
| **C (high-key)** | orig | 467 | 342 (-27%) | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | **ta** | 467 | 520 (+11%) | **294 (-37%)** | 317 (-32%) |

百分比都是「同 DB baseline 為比較基準」。

### 跨 layout 比較（vs 原始 DB baseline）

| Workload | orig baseline | ta baseline | ta + 最佳 prefetch | 全局最佳改善 |
|---|---:|---:|---:|---:|
| **A** | 318 µs | 404 µs (+27%) | **127 µs (layers_5)** | **-60%** |
| **B** | 463 µs | 408 µs (-12%) | 352 µs (perpage) | -24% |
| **C** | 467 µs | 467 µs (±0%) | **294 µs (perpage)** | **-37%** |

### 五個發現

1. **ta layout 對 baseline 的方向 workload-dependent**：
   - A: +27%（leaves 被推到高 offset、第一個 cold leaf fault 跑得更遠，但 Zipfian 下後續被 prefetch 完全壓過）
   - B: **-12%（變快）** — 推測是 leaf 區也變得連續，cold leaf fault 的 readahead 更高效
   - C: ±0%（高 id leaves 在 ta 後仍位於檔尾，距離沒變）
2. **ta + layers_5 在 B 上反而變慢 +8%**（408 → 440）。原因：ta 把 leaves 推到
   高 offset，layers_5 prefetch 的 5 個 interior 載到了，但第一個 cold leaf
   fault 在很遠的 offset，prefetch 的 5 頁 + 後面的 cold leaf fault 兩個 I/O
   階段串起來反而比裸 baseline 慢。**ta 強在「prefetch coverage 高」時，弱在
   「prefetch 不夠覆蓋」時 —— B uniform 的 leaf coverage 一定不夠**。
3. **ta + perpage 是 Workload C 的最佳組合**（-37%、294 µs）。perpage 把 92
   個 interior **逐頁**載入，配合 ta 的 page 2-93 連續性，kernel 能高效
   sequential read；range 反而失效（+11%）因 1 個 madvise 被 kernel readahead
   限制（~32/92 pages）。
4. **ta + range 在所有 workload 都不是好選擇**：A -4%、B -10%、C +11%。
   `MADV_WILLNEED` 對單一大 range 的 readahead 是 bounded，覆蓋不完 92 個
   interior。
5. **「ta + layers_5」是 A 專屬最強**（-69%）。在 B/C 都不是最佳；對 C 反而
   是 layers_5 在 ta 上才開始有效（orig: -13% → ta: -32%），但仍輸給 perpage。

### 結論

- **ta layout 不是 universal best**：A 上 -69%，B 上反而讓 layers_5 變慢 +8%。
- **配方依 workload 而定**：
  - Zipfian 點讀 (A) → **ta + layers_5**
  - Uniform 全段 (B) → 不要 ta，**orig + layers_5** (-47%) 仍最強
  - File-tail uniform (C) → **ta + perpage** (-37%) 是全局最佳
- **range 在任何 layout 都不該選**：kernel readahead 限制讓它永遠覆蓋不完。

資料來源：[layout_rewriter/runs/matrix_1c_bc_results.csv](layout_rewriter/runs/matrix_1c_bc_results.csv)
+ [results_1c_bc_summary.csv](layout_rewriter/runs/results_1c_bc_summary.csv)
（A 數據 [matrix_results.csv](layout_rewriter/runs/matrix_results.csv) 同 harness 可直接比較）

---

## 第八維 — 2c Layers_N sweep × Workload B / C（原始 layout）

第三維只在 Workload A 上跑過 N sweep（N=1/5/10/20/46/92）。本節補上同一個
sweep 在 **B (Uniform)** 和 **C (high-key uniform)** 上的結果，使用同一個
`posix_fadvise` cold-start harness、原始 layout、3 reps median。

### Latency 矩陣（first-query µs，median of 3）

| N | A baseline 改善 (參考第三維) | **B (Uniform)** | B 改善 | **C (high-key)** | C 改善 |
|---:|---:|---:|---:|---:|---:|
| 0 (baseline) | 73 µs | **470 µs** | — | **491 µs** | — |
| 1 | 38 µs (-48%) | 403 µs | -14% | 414 µs | -16% |
| 5 | **33 µs (-54%)** ← 甜蜜點 | 246 µs | **-48%** | 419 µs | -15% |
| 10 | 44 µs (-39%) | 244 µs | -48% | 406 µs | -17% |
| 20 | 35 µs (-53%) | 245 µs | -48% | 411 µs | -16% |
| 46 | 41 µs (-45%) | 242 µs | **-49%** | 420 µs | -14% |
| 92 (all interior) | 50 µs (-31%) | 243 µs | -48% | **265 µs** | **-46%** ← C 的甜蜜點 |

### 三個發現

1. **B 上 N=5 之後就 plateau**（-48% 全部停在 ~244 µs），完全沒有 A 的 U 型
   曲線。原因：B 的 baseline 470 µs 是被 leaf cold fault 主導，prefetch 多
   個 interior 帶來的 madvise overhead（最多 92 × 1.8 µs ≈ 165 µs）相對於
   leaf fault cost 可忽略。**A 的 U 型曲線專屬於「baseline 已經很低」的場景**
   —— A baseline 73 µs，多打 87 個 madvise 就壓垮收益。

2. **C 上 N=1~46 只有 ~15% 改善**（停在 ~410 µs），**N=92 突然跳到 -46%**
   （265 µs）。原因：C 查 id ∈ [590k, 610k]（檔尾區段），走的 interior
   path **不在前 46 個 page 裡**。layers_N 按 file offset 排序的「top-N」
   對 C 不是 hot interior —— 必須載入**全部** 92 個 interior 才覆蓋到 C
   真正會 traverse 的那幾頁。
   - 這也解釋為什麼第六維裡 C 上 `range` (-27%) 和 `perpage` (-27%) 勝過
     `layers_5` (-13%)：range/perpage 都載全部 interior，layers_5 漏掉中段。

3. **「N=5 是甜蜜點」只在 A 上成立**。三個 workload 的最佳 N 值各不相同：
   - **A**: N=5（-54%）—— 上層 interior 就是熱點
   - **B**: N=5~92 一樣（-48%）—— 任何 N≥5 都打到瓶頸
   - **C**: 必須 N=92（-46%）—— 熱 interior 在 file 中段，前 N 排序選不到

   **這推翻第三維的隱含結論「layers_N 是 universal 啟發式」**：它其實是
   *Zipfian-friendly* 啟發式，依賴「query 走的 interior path 集中在 file
   上層」這個假設。對 file-tail workload (C)，按 offset 排序 + top-N 是
   錯誤的優先順序。

### 結論

- **B 上**：layers_5 已經是 cost-effective 最佳，再多 N 不會更好（也不會更差）。
- **C 上**：layers_N 啟發式失效，要嘛載全部 (perpage/N=92)、要嘛改用
  access-pattern 排序的 2d/2e。
- **「按 file offset 排序的 top-N」是 zipfian-low-key-specific 的啟發式**，
  不能無腦套用到任意 workload。

資料來源：[layout_rewriter/runs/matrix_Nsweep_bc_results.csv](layout_rewriter/runs/matrix_Nsweep_bc_results.csv)
+ [results_Nsweep_bc_summary.csv](layout_rewriter/runs/results_Nsweep_bc_summary.csv)

---

## 第九維 — Layout 1b (VACUUM) 補測：N sweep + 2f SLRU × A/B/C

第六維只跑了 baseline / range / perpage / layers_5 in vacuum DB × B/C。本節
把 Layout 1b 上的兩個剩餘缺口補齊：
- **N sweep**（N=1/5/10/20/46/92）on A/B/C × vacuum DB（layout_rewriter harness）
- **2f SLRU** on A/B/C × vacuum DB（prefetch_slru harness，with mmap）

VACUUM 把 interior 從 92 → 85 個，所以 N=92 的「全部 interior」實際載入 85 個。

### 9.1 N sweep × A/B/C × Layout 1b（first-query µs, median of 3）

跟第八維同一個 layout_rewriter harness（無 mmap、`posix_fadvise` cold-start）。

| N | A orig (第三維) | **A vac** | B orig (第八維) | **B vac** | C orig (第八維) | **C vac** |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 318 | **339** | 470 | **497** | 491 | **434** |
| 1 | — | 405 | 403 | 414 | 414 | 417 |
| 5 | 224 | 243 | 246 | 253 | 419 | 407 |
| 10 | — | 246 | 244 | 247 | 406 | 406 |
| 20 | — | **234** ← A vac 甜蜜點 | 245 | 246 | 411 | 424 |
| 46 | — | 248 | 242 | 255 | 420 | 410 |
| 92 | — | 241 | 243 | 252 | 265 | **246** |

「A orig」N=0/5 從 [layout_rewriter/runs/matrix_results.csv](layout_rewriter/runs/matrix_results.csv) 同 harness 取得；其他 N 在 A orig 上未跑（屬第三維的 prefetch_vacuum harness）。

### 9.2 2f SLRU × A/B/C × Layout 1b（median of 3）

跟第五維同一個 prefetch_slru harness（有 mmap）。

#### Hot set 大小（warmup 後）

| Workload | orig resident (第五維) | **vacuum resident** | 差距 |
|---|---:|---:|---:|
| A (Zipfian) | 4,048 | **3,369** | -17% |
| B (Uniform) | 4,122 | **3,373** | -18% |
| C (high-key) | 420 | **394** | -6% |

VACUUM 後 A/B 的 hot set 縮 17–18% —— 因為 VACUUM 把同一條 query path 的
leaves 排得更連續，一次 readahead 載入的 page 數變多，重複 query 的「需要
獨立 resident 的 page」減少。C 上 hot set 本來就集中，VACUUM 只剩 6% 改善
空間。

#### Latency 矩陣

| Workload | 策略 | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise 次數 |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | baseline (vac) | 219 | 3.56 | 356 | 0 | 0 |
| A (Zipfian) | **2f SLRU (vac)** | **15** | **2.36** | **236** | 6,712 | 3,369 |
| B (Uniform) | baseline (vac) | 230 | 3.56 | 356 | 0 | 0 |
| B (Uniform) | **2f SLRU (vac)** | **14** | **2.39** | **239** | 6,303 | 3,373 |
| C (high-key) | baseline (vac) | 212 | 2.44 | 244 | 0 | 0 |
| C (high-key) | **2f SLRU (vac)** | **14** | **2.28** | **228** | 1,911 | 394 |

#### 與同 harness orig baseline 比

| Workload | 改善類型 | orig (第五維) | vacuum (本節) |
|---|---|---:|---:|
| A | first-q 改善 | -94% | **-93%** |
| A | 全 workload 改善 | -39% | **-34%** |
| A | prefetch 開銷 | 7,255 µs | **6,712 µs (-7%)** |
| B | first-q 改善 | -94% | **-94%** |
| B | 全 workload 改善 | -38% | **-33%** |
| B | prefetch 開銷 | 7,478 µs | **6,303 µs (-16%)** |
| C | first-q 改善 | -94% | **-94%** |
| C | 全 workload 改善 | -7% | **-7%** |
| C | prefetch 開銷 | 1,881 µs | **1,911 µs (≈0%)** |

### 五個發現

1. **VACUUM 在 prefetch_slru harness（mmap-enabled）下對 baseline 是利好**
   （A: 251→219、B: 255→230、C: 250→212）—— 與第六維「VACUUM 讓 A/B baseline
   變慢 +5~8%」相反。差異在 harness：layout_rewriter 沒設 `--mmap-size`，
   prefetch_slru 設了。**mmap 路徑下 VACUUM 把連續 leaf 拉得更近的好處
   compounds，而 pread 路徑下 VACUUM 反而讓 interior path 變遠**。

2. **A vac 在 N-sweep 找到新甜蜜點 N=20**（234 µs），比 N=5 的 243 µs 略勝。
   原因：VACUUM 把 interior 重排後，前 20 個 page 涵蓋了更多 query path；
   N=5 在 vacuum layout 上覆蓋不完。但邊際效益小（4%）—— N=5 已經抓到 95% 的
   好處。

3. **B vac 跟 B orig N-sweep 幾乎一樣**（N≥5 都 plateau 在 ~245 µs）。VACUUM
   沒改變 B 的 prefetch 行為，因為 B 是 leaf-cold-fault 主導。

4. **C vac 上 N=92 依然是最佳**（246 µs，-43%）。VACUUM 沒改變 C 的根本問
   題：query 走的 interior path 不在 file 前段，必須載全部才覆蓋到。**這
   confirm 第八維結論「layers_N 是 zipfian-friendly 啟發式」適用在所有 layout
   上**。

5. **2f SLRU 在 vacuum 下 prefetch 開銷 A/B 省 7-16%、C 不變**。跟 hot set
   縮減比例 (-17%、-18%、-6%) 一致 —— VACUUM 替 2f 帶來邊際 prefetch cost
   節省，但全 workload 改善反而從 -38% → -33%（A）因 baseline 已經更快、
   SLRU 拉得到的下限差距變小。

### 結論

- **Layout 1b 補測完成**：A/B/C × {N=1,5,10,20,46,92, baseline, range, perpage, 2f SLRU} 全部跑過。
- **N=5 仍是大部分 workload 的 cost-effective 選擇**（A vac N=20 只多省 4%）。
- **2f SLRU 的「VACUUM 加持」效果有限**：prefetch overhead 微降，但全 workload
  改善幅度反而縮水（因 baseline 變更快）。沒有 layout × prefetch 的乘數效應。

資料來源：
- N sweep: [layout_rewriter/runs/matrix_Nsweep_vac_results.csv](layout_rewriter/runs/matrix_Nsweep_vac_results.csv)
  + [results_Nsweep_vac_summary.csv](layout_rewriter/runs/results_Nsweep_vac_summary.csv)
- SLRU: [prefetch_slru/runs/matrix_vacuum_results.csv](prefetch_slru/runs/matrix_vacuum_results.csv)
  + [results/results_vacuum_summary.csv](prefetch_slru/results/results_vacuum_summary.csv)

---

## 第十維 — N sweep × Workload C × churned DB（補齊 prefetch_churn 缺口）

第四維只用 N=5 跑了 10 個 churn checkpoint，第八維只在乾淨 DB 上做 N sweep。
本節在 **churned DB × Workload C** 上補上 N=1/10/20/46/92 sweep，回答「乾淨 DB
的『N=92 必勝、N≤46 plateau』結論在 churn 漂移後是否還成立」。

**Harness 注意：** 本節用 `posix_fadvise(POSIX_FADV_DONTNEED)` evict（不需要
sudo），跟第四維的 `sudo drop_caches` **不同冷啟動機制**，絕對 µs 不能跟第四
維直接比。第四維 baseline ~5,130 µs（全 kernel cache 清空），本節 baseline
~462 µs（只 evict file pages，slab/syscall cache 留住）。**本節內 N 值之間
可直接比較**。

### Latency 矩陣（first-query µs，每個 N 一個獨立 run）

每個 checkpoint 之間用 Workload D 跑 5,000 ops 製造 churn，10 個 checkpoint
累積 50,000 ops。每個 cell 是一次 run（不是 median）。

| Checkpoint (ops) | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | **N=92** |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (0) | 407 | 422 | 387 | 383 | 389 | 385 | **209** |
| ck001 (5k) | 387 | 420 | 443 | 523 | 331 | 396 | **202** |
| ck002 (10k) | 450 | 417 | 408 | 465 | 403 | 422 | **203** |
| ck003 (15k) | 433 | 409 | 396 | 437 | 390 | 393 | **232** |
| ck004 (20k) | 460 | 403 | 380 | 364 | 391 | 323 | **208** |
| ck005 (25k) | 502 | 465 | 388 | 431 | 452 | 408 | **176** |
| ck006 (30k) | 431 | 462 | 406 | 393 | 392 | 392 | **218** |
| ck007 (35k) | 428 | 411 | 344 | 362 | 378 | 354 | **227** |
| ck008 (40k) | 492 | 504 | 466 | 409 | 451 | 453 | **193** |
| ck009 (45k) | 488 | 503 | 405 | 426 | 496 | 463 | **229** |
| ck010 (50k) | 549 | 497 | 496 | 439 | 498 | 456 | **242** |

### 跨 10 checkpoint 平均（ck001-010）

| N | avg first-q (µs) | vs N=0 baseline |
|---:|---:|---:|
| 0 (no prefetch) | 462 | — |
| 1 | 449 | -2.8% |
| 5 | 413 | -10.6% |
| 10 | 425 | -8.0% |
| 20 | 418 | -9.5% |
| 46 | 406 | -12.1% |
| **92 (all interior)** | **213** | **-53.9%** ← clear winner |

### 四個發現

1. **churned DB 的 N sweep 形狀跟乾淨 DB 完全一致**：N=1~46 都 plateau 在
   -10% 附近，N=92 跳到 -54%。第八維乾淨 DB 上是 N=1~46 plateau 在 -15%、
   N=92 跳到 -46%。**Churn 沒有改變 layers_N 在 C 上的根本問題**。

2. **N=92 在所有 11 個 checkpoint 都壓制其他 N**（包括 baseline checkpoint）。
   churn 累積到 50k ops 後，N=92 仍穩定在 200~240 µs，其他 N 漂移到 400~550 µs。
   **layers_N=92 是 churn-robust 的選擇**。

3. **N=5 也省 -10.6%**（413 vs 462）— 跟第四維「ck001-010 平均 -7%」方向一致，
   只是 harness 不同所以絕對值不同。第四維是 sudo drop_caches 下平均省
   ~487 µs；本節是 posix_fadvise 下平均省 ~49 µs。**相對改善的方向 robust，
   絕對節省值跟冷啟動機制有關**。

4. **單筆 noise 很大**（ck005 N=10 從 N=5 的 388 跳到 431，N=20 又跳到 452，
   ck008 N=1 從 N=0 的 492 漲到 504）— 跟第四維觀察到的「單 checkpoint
   ±20% 噪音」一致。每個 N 跑單一 run、沒 median 之下，要看 ck001-010 平均
   才有意義。

### 結論

- **layers_N 在 C 上的「N=92 必勝」結論在 churned DB 上同樣成立**：第八維乾
  淨 DB 上是 -46%、churned DB 上是 -54%，churn 反而把 N=92 的相對優勢拉大。
- **解釋**：C 走的 interior path 不在 file 前段（清楚證據已在第八維）。Churn
  會把新 interior 配到更亂的 file 位置（freelist 重用），讓「按 offset 排序的
  top-N」更不準。N=92 載全部 interior 就不受 layout 漂移影響。
- **prefetch_churn 第四維補齊**：N 在 churned DB 上的曲線從只有 N=5 補到完整
  sweep。剩餘缺口（README/overall_workloads.md 已知缺口）只剩 Zipfian
  low-key hotspot 變體 + RAM-constrained 對照。

資料來源：
- 完整 matrix: [prefetch_churn/results/nsweep_churn_matrix_first_q_us.csv](prefetch_churn/results/nsweep_churn_matrix_first_q_us.csv)
- 摘要: [prefetch_churn/results/nsweep_churn_summary.csv](prefetch_churn/results/nsweep_churn_summary.csv)
- Per-N benchmark dirs: [prefetch_churn/runs_nsweep/n{0,1,5,10,20,46,92}/benchmark_summary.csv](prefetch_churn/runs_nsweep/)
- N-sweep wrapper: [prefetch_churn/runs_nsweep/run_nsweep.sh](prefetch_churn/runs_nsweep/run_nsweep.sh)

---

## 第十一維 — 2f SLRU × Layout 1c (type-aware)

第五維把 2f SLRU 跑在 Layout 1a 上、第九維補 Layout 1b（vacuum）。本節補上剩餘
缺口 **Layout 1c × {baseline, layers_5, 2f SLRU} × Workload A/B/C × 3 reps**，
回答「type-aware layout 把 interior 集中到檔頭之後，2f SLRU 還能再省什麼」。

**直覺：** 1c 把 interior 排到 page 2..93，但 2f SLRU 的 prefetch 集合是
mincore-dumped resident set（~4,000 個 page，主要由 leaf 組成），跟 interior
位置幾乎無關。預測：first-q 不會更好，prefetch overhead 也不會明顯下降。

### Latency 矩陣（median over 3 reps）

| Workload | 策略 | first-q (µs) | avg (µs) | prefetch (µs) | n_prefetch |
|---|---|---:|---:|---:|---:|
| **A** | baseline | 321 | 4.06 | — | — |
| A | layers_5 | 127（-61%） | 4.03 | 11 | 5 |
| A | **2f SLRU** | **15（-95%）** | **2.41（-41%）** | 7,596 | 4,043 |
| **B** | baseline | 304 | 4.03 | — | — |
| B | layers_5 | 132（-56%） | 4.03 | 17 | 5 |
| B | **2f SLRU** | **16（-95%）** | **2.45（-39%）** | 7,497 | 4,107 |
| **C** | baseline | 249 | 2.53 | — | — |
| C | layers_5 | 140（-44%） | 2.52 | 18 | 5 |
| C | **2f SLRU** | **13（-95%）** | **2.35（-7%）** | 1,845 | 417 |

### 跨 layout 對照（2f SLRU 三個 layout 並列）

| Workload | Layout 1a (orig) | Layout 1b (vacuum) | Layout 1c (type-aware) |
|---|---|---|---|
| A first-q (µs) | 13.88 | 15.07 | 14.98 |
| A prefetch (µs) | 7,478 | 6,704 | 7,596 |
| A n_prefetch | 4,048 | 3,369 | 4,043 |
| B first-q (µs) | 14.61 | 14.34 | 16.05 |
| B prefetch (µs) | 7,614 | 6,303 | 7,497 |
| B n_prefetch | 4,122 | 3,373 | 4,107 |
| C first-q (µs) | 16.17 | 13.54 | 13.28 |
| C prefetch (µs) | 1,881 | 1,910 | 1,845 |
| C n_prefetch | 420 | 394 | 417 |

### 四個發現

1. **2f SLRU 是 layout-agnostic**：first-q 在三個 layout 上都落在 13–16 µs，
   差異 < 3 µs（小於單筆 noise）。Layout 改 interior 位置對 mincore 撈到的
   resident set 幾乎沒影響。

2. **1c 沒有像 layers_5 那樣放大 2f SLRU 效益**：1c × layers_5 在 A 上 -69%
   （第二維），相對於 1a × layers_5 的 -54% 是顯著放大；但 1c × 2f SLRU
   只有 -95%（基本上跟 1a/1b 一樣），因為 2f SLRU 的 -94~95% 是 leaf preload
   主導，已經接近 RAM hit 上限，不留 layout 加成空間。

3. **1b（vacuum）才是真正能省 prefetch overhead 的 layout**：n_prefetch
   從 1a 的 4,048 / 4,122 降到 1b 的 3,369 / 3,373（A/B 各省 ~17%）；1c
   的 n_prefetch 跟 1a 幾乎一致。原因：VACUUM 物理壓縮 file，working set
   裡的 page 數量真的變少；layout_rewriter 只搬位置不刪 page。

4. **1c baseline 在 B 上也是最差的（304 µs，比 1a 255 µs / 1b 230 µs 高）**：
   跟第七維「1c 在 B 上 baseline 變慢」結論一致。但 2f SLRU 蓋掉這個 penalty
   後，1c 的 first-q 跟 1a/1b 並排。

### 結論

- **2f SLRU 不需要也用不到 layout 1c**：working-set preload 機制天花板已碰到
  RAM hit，layout 加成空間 < 3 µs。
- **想堆 layout × prefetch 乘數效應的人應該選 1c + layers_5**（A 上 -69% 是
  全局最強）；2f SLRU 應該用 layout 1a 或 1b。
- **1b 是 2f SLRU 的省 RAM 搭檔**：working set 縮 ~17%，prefetch 開銷下降，
  全 workload 改善仍 -38~40%（第九維）。

資料來源：
- 矩陣: [prefetch_slru/runs/matrix_ta_results.csv](prefetch_slru/runs/matrix_ta_results.csv)
- Median 摘要: [prefetch_slru/runs/matrix_ta_aggregated.csv](prefetch_slru/runs/matrix_ta_aggregated.csv)
- 跑法: [prefetch_slru/runs/runmatrix_ta.sh](prefetch_slru/runs/runmatrix_ta.sh) + [warmup_ta.sh](prefetch_slru/runs/warmup_ta.sh)
- Hot-set CSVs: [hotpages_a_ta.csv](prefetch_slru/runs/hotpages_a_ta.csv) / [b_ta](prefetch_slru/runs/hotpages_b_ta.csv) / [c_ta](prefetch_slru/runs/hotpages_c_ta.csv)

---

## 第十二維 — N sweep × Layout 1c (type-aware) × A/B/C

第三維只在 Layout 1a 上做 A 的 N sweep；第八維補 1a × B/C；第九維補 Layout 1b × A/B/C。
本節補上 **Layout 1c (type-aware) × A/B/C × N ∈ {1, 5, 10, 20, 46, 92}** 共 21 cells × 3 reps
（B/C 因高 variance 加跑到 6 reps），完成跨三 layout 的 N sweep 矩陣。同時補上
Layout 1a × A 的 N sweep（先前只有 N=0/5 在這個 harness 下跑過），讓三個 layout
在同一個 `posix_fadvise` harness 下可直接比對。

**Harness：** 跟第八/九維一樣 — `layout_rewriter/runs/benchmark_harness`，
`--cold-advice dontneed`，`cold_ta.sh` evict，3 (A) / 6 (B,C) reps median。
**絕對 µs 跟第十一維（prefetch_slru 用 mmap）不能直接比**，但跟第八/九維可比。

### 12.1 Layout 1c × N sweep（first-query µs，median）

| Workload | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | N=92 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **A** | 406 | 411（+1%） | 137（-66%） | 129（-68%） | 128（-69%） | 131（-68%） | **116（-71%）** |
| **B** | 414 | 409（-1%） | 432（+4%） | 432（+4%） | 411（-1%） | **320（-23%）** | 423（+2%） |
| **C** | 460 | 409（-11%） | 326（-29%） | 317（-31%） | 328（-29%） | **311（-32%）** | 413（-10%） |

### 12.2 跨 layout N sweep 對照（first-q median µs，3 layout 並列）

| WL | N | 1a (orig) | 1b (vacuum) | 1c (ta) | 1a improve | 1b improve | 1c improve |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0 | 303 | 339 | 406 | — | — | — |
| A | 5 | 229 | 243 | **137** | -24% | -28% | **-66%** |
| A | 20 | 225 | 234 | 128 | -26% | -31% | **-69%** |
| A | 92 | 224 | 241 | **116** | -26% | -29% | **-71%** |
| B | 0 | 470 | 497 | 414 | — | — | — |
| B | 5 | 246 | 253 | 432 | **-48%** | **-49%** | +4% ⚠️ |
| B | 46 | 242 | 255 | 320 | -49% | -49% | -23% |
| B | 92 | 243 | 252 | 423 | -48% | -49% | +2% ⚠️ |
| C | 0 | 491 | 434 | 460 | — | — | — |
| C | 5 | 419 | 407 | **326** | -15% | -6% | **-29%** |
| C | 46 | 420 | 410 | **311** | -14% | -5% | **-32%** |
| C | 92 | 265 | 246 | 413 | **-46%** | **-43%** | -10% ⚠️ |

### 三個發現

1. **Layout 1c 把 A 的 layers_N 上限從 -26% 推到 -71%**：1a/1b 的 layers_N 在 A 上
   省 ~25-30%（U 型曲線 N=5/20 微差），到 1c 上整條曲線往下沉 ~40 個百分點，**且
   N ≥ 5 全部 plateau 在 -66~71%**（U 型曲線消失）。原因：TA layout 把所有
   table interior 集中到 page 2..52，prefetch 任何 N≥5 都能 cover 到 A 的熱
   interior path，**「N=5 vs N=20 vs N=92」差別小於 noise**。

2. **Layout 1c 讓 B 的 layers_N 失效**：B 在 1a/1b 上任何 N≥5 都穩定 -48~49%
   plateau；到 1c 上 **N=5/10 完全沒幫助（+4%）、N=46 才達到 -23%（最佳）、
   N=92 又回到 +2%**。3 reps 之後 B 在 N=20/46/92 都觀察到 bimodal 行為
   （min~240, max~445）。**TA 拆散了 B 在 1a 上靠的「load 任何 5 個 interior
   就 cover uniform read」效應** — TA 按頁類型重排後，前 5 個 interior 對
   uniform B 不再 representative。這跟第七維「1c × baseline B 變慢」、第十一
   維「1c × 2f SLRU 蓋掉 B baseline penalty」結論同源：**1c 對 B 是 layout-hostile，
   只有 SLRU 那種 leaf-preload 蓋得住，layers_N 蓋不住**。

3. **Layout 1c 把 C 從「必須 N=92」翻成「N≥5 就有 -30%」**：1a/1b 上 C 卡在
   「layers_N≤46 只 -15%，N=92 才跳到 -46%」(cliff)；1c 上 **N=5 已經 -29%、
   N=46 -32%、反而 N=92 退回 -10%**（inverted cliff）。原因：
   - TA 把 table interior 集中在 page 2..52，C 走的 PK lookup interior path
     **全在這個區段**；N=5 就能蓋到熱頁。
   - N=92 額外載的 41 個 interior_index page 對 C（PK lookup）完全無用，
     並且推測有 async I/O queue 競爭，把熱 interior 的 ready time 拖慢。
   **這推翻第八/九維「C 必須 N=92」結論在 type-aware layout 上不成立** —
   **1c × layers_46 是 C 的新最佳 (不需要 perpage, 不需要載全 92 個)**。

### 結論

- **2c × Layout 1c 矩陣補齊**：A 上 layers_N 升級為 -71%（最強）；C 上
  cost-effective N 從 92 降到 5-46；B 上 layers_N 在 1c 失效，要回到 1a/1b 用
  N≥5 或改用 2f SLRU。
- **「layers_N 的最佳 N 跟 layout 強耦合」**：
  - 1a A: N=20 (-26%, 微差於 N=5)
  - 1b A: N=20 (-31%) — 第九維新甜蜜點
  - 1c A: N=92 (-71%) — 但 N≥5 全 plateau
  - 1a/1b C: N=92 only
  - 1c C: N=5-46 全好，N=92 退化
- **完整三 layout × 三 workload × 7 N 值矩陣**（共 63 cells × 3-6 reps = 189-378
  runs）。剩餘缺口只剩 strategy 級別（2d/2e access-pattern、2f cgroup-bounded）
  跟 workload 變體（Zipfian low/high-key）。

資料來源：
- 1c 矩陣: [layout_rewriter/runs/matrix_Nsweep_ta_results.csv](layout_rewriter/runs/matrix_Nsweep_ta_results.csv)
- 1c 摘要: [layout_rewriter/runs/results_Nsweep_ta_summary.csv](layout_rewriter/runs/results_Nsweep_ta_summary.csv)
- 1c 跑法: [layout_rewriter/runs/runmatrix_Nsweep_ta_abc.sh](layout_rewriter/runs/runmatrix_Nsweep_ta_abc.sh)
- 1a × A 補測: [layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv](layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv) + [results_Nsweep_orig_a_summary.csv](layout_rewriter/runs/results_Nsweep_orig_a_summary.csv) + [runmatrix_Nsweep_orig_a.sh](layout_rewriter/runs/runmatrix_Nsweep_orig_a.sh)
- 1a × B/C: [results_Nsweep_bc_summary.csv](layout_rewriter/runs/results_Nsweep_bc_summary.csv)（第八維）
- 1b × A/B/C: [results_Nsweep_vac_summary.csv](layout_rewriter/runs/results_Nsweep_vac_summary.csv)（第九維）

---

## 第十三維 — Zipfian low-key hotspot variant（Workload Z） × N sweep × 3 layouts

第八/九/十二維把 Workload A (Zipfian 熱點分佈在 [8, 99997]) 在三個 layout × N sweep
全跑過，但**熱點在哪個 key 區段**這個變因沒被隔離。本節新增 **Workload Z (Zipfian
low-key hotspot)**：α=0.99，熱點全部集中在 keys [1, 1000]，top key 拿走 13% 的讀、
top 10 keys 拿走 38%（相比之下 A 的 top key 只 7.8%）。

**問題：** 把 Zipfian 熱點從「散在整個 100k key range」改成「全集中在前 1000 key」，
prefetch 的甜蜜點會變嗎？1c 還是最強的 layout 嗎？

**Harness：** 同第八/九/十二維（`benchmark_harness`，`--cold-advice dontneed`），
3 reps median，每個 cell 一個 100k-op run。

### 13.1 Zipfian low-key × N sweep × 3 layouts（first-q median µs）

| Layout | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | N=92 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **1a (orig)** | 319 | 390（+22%）⚠️ | 222（-30%） | 220（-31%） | **219（-31%）** | 224（-30%） | 225（-30%） |
| **1b (vacuum)** | 341 | 413（+21%）⚠️ | **237（-31%）** | 254（-26%） | 244（-28%） | 252（-26%） | 249（-27%） |
| **1c (type-aware)** | 414 | 409（-1%） | 128（-69%） | 127（-69%） | 130（-69%） | 130（-69%） | **115（-72%）** |

### 13.2 跟 Workload A（mid-key Zipfian）對照

| Layout | N | Workload A first-q | Workload Z first-q | Δ (Z vs A) |
|---|---:|---:|---:|---:|
| 1a | 0 | 303 | 319 | +16 µs（Z baseline 微高） |
| 1a | 5 | 229（-24%） | 222（-30%） | **Z 多省 6pp** |
| 1a | 20 | 225（-26%） | 219（-31%） | Z 多省 5pp |
| 1a | 92 | 224（-26%） | 225（-30%） | Z 多省 4pp |
| 1b | 5 | 243（-28%） | 237（-31%） | Z 多省 3pp |
| 1b | 20 | 234（-31%） | 244（-28%） | A 多省 3pp |
| 1c | 5 | 137（-66%） | 128（-69%） | Z 多省 3pp |
| 1c | 92 | 116（-71%） | 115（-72%） | 持平 |

### 四個發現

1. **「Zipfian 熱點散開 vs 集中」對 prefetch 效益基本沒影響**：跨 layout × N 的相對改善
   幅度跟 A 在 3pp 以內。意外（也是好消息）—— **layers_N heuristic 對 Zipf 整體
   robust，不依賴熱點落在哪個 key 區段**。
   原因：Zipfian 工作集本身就小（top 10 keys 拿 38%），10 個 key 落在 1-2 個 leaf page、
   走 2-3 個 interior page。layout 重排把這些 interior 集中後，prefetch 任意 N≥5
   就 cover 到 — 熱點的 key 編號落在哪反而不重要。

2. **N=1 在 Zipfian 上**一律**比 baseline 還差**（1a: +22%, 1b: +21%, 1c: -1%）：
   只 prefetch page 1（root）幾乎沒幫助（root 開檔就常駐 cache），反而吃 madvise
   syscall ~75 µs 的 overhead。**「N=1 是 cost-effective baseline」的直覺是錯的，
   N=5 才是真正的下界**。1c 上 N=1 沒退化是因為 baseline 本身已經高（414 vs 1a 319）。

3. **1a vs 1b 的相對 ranking 在 Z 上跟 A 上一致**：1a baseline 比 1b 低 ~20 µs
   （VACUUM 把 baseline 稍微推高），但兩者的 layers_N 收斂值差不多 (~220 µs)。
   **VACUUM 對 Zipfian 沒有額外幫助**，跟第五/六維結論一致。

4. **1c 又是最強的 layout**：Z 上 N=92 -72% vs A 上 N=92 -71%，幾乎一致。**TA
   layout × Zipfian 是個跨熱點區段都成立的最佳組合**（不論熱點是 mid-key 還是
   low-key）。

### 結論

- **Zipfian low-key hotspot 不是 prefetch 失敗模式** — 跟原本 Workload A 結果基本同
  形（同甜蜜點、同收斂值、同 layout ranking）。**low-key 反而比 mid-key 微好** ~3-5pp
  on 1a/1b（熱點集中意味著走的 interior path 更窄）。
- **append-only churn workload 預測**：append 寫入意味著熱點集中在最新一段 key range，
  本實驗用 Zipfian + low-key 作為 stable proxy，結論是 **append-only 場景的 prefetch
  效益會比 random-churn 略好（≤ 5pp）、不會有 qualitative 差異**。
- **N=1 應該從預設 sweep 集合中刪掉** — 在所有 Zipfian/uniform workload 上都比
  baseline 差，純粹是 madvise overhead 沒回收。
- **剩餘缺口收斂**：原本「Zipfian 熱點變體」這個未測項目消除；剩下只有 strategy 級
  （2d/2e access-pattern、2f cgroup-bounded）跟 high-key Zipfian variant（如果想對稱
  測 [99k, 100k]，但邏輯上跟 Workload C 已重疊）。

資料來源：
- 原始矩陣（63 cells）: [layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv](layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv)
- Median 摘要: [layout_rewriter/runs/results_Nsweep_zlowkey_summary.csv](layout_rewriter/runs/results_Nsweep_zlowkey_summary.csv)
- 跑法: [layout_rewriter/runs/runmatrix_Nsweep_zlowkey.sh](layout_rewriter/runs/runmatrix_Nsweep_zlowkey.sh)
- Workload 生成器: [benchmark_harness/workloads/gen_zipf_lowkey.py](benchmark_harness/workloads/gen_zipf_lowkey.py) (Zipfian α=0.99, keys [1, 1000], 100k ops, seed 42)
- Workload 檔案: [benchmark_harness/workloads/workload_zipf_lowkey.txt](benchmark_harness/workloads/workload_zipf_lowkey.txt)

---

## 還沒跑的策略 × workload 組合

| 缺口 | 為什麼值得測 |
|---|---|
| **2d Access pattern, interior-only** | 整個策略未實作。`layers_N` 假設「offset 越小 = 越熱」對 B+tree 結構成立，但忽略不同 query 路徑使用不同分支。**第八維已直接證明這個假設在 Workload C 上失效**（layers_N≤46 只 -15%，必須 N=92 才 -46%）。用 access count 排序的前 N 個 interior 應該能在 C 上以遠少於 92 個 syscall 達到相近效益 |
| **2e Access pattern, interior + leaf (7:3 / 5:5)** | 未實作。Workload A 有 leaf-level 熱點，prefetch top-K interior + top-M leaf 可能直接砍掉部分 leaf fault；可以驗證「2f 之所以 -94% 是因為 leaf preload」這個假設能否用更少 syscall 達成 |
| **2f SLRU 在 RAM 緊的對照** | 第五維是 RAM 充裕情境，2f vs 2d/2e 看不出差異。用 cgroup 把 RAM 預算壓到 < working set，才能體現 SLRU 不會挑重點的缺點 |
| ~~**Zipfian low-key hotspot variant**~~ | ~~目前 Workload A 的熱點分佈在整個 [8, 99997] 區段。若熱點全在 [1, 1000]（≈ append-only churn）或全在 [99k, 100k]（≈ random churn），prefetch 效益會分歧~~ → **已完成 (第十三維)**：low-key hotspot 跟 mid-key 結果同形（差異 ≤5pp），「熱點落在哪個 key 區段」不是 prefetch 效益的主要變因 |

---

## 一句話總結

| Workload | 評估指標 | 最佳策略 | 改善幅度 | 條件 |
|---|---|---|---|---|
| **A（Zipfian）** | first-q | layers_5 on type-aware layout | **-69%**（404 → 127 µs） | 需先跑 layout_rewriter |
| **A（Zipfian）** | first-q | layers_5 on 原始 layout | **-54%**（73 → 33 µs） | 不改 layout，立即可用 |
| **A（Zipfian）** | first-q | **2f SLRU** on 原始 layout | **-94%**（251 → 14 µs）| 但 prefetch 自己花 7.3 ms，端到端 cold start 慢 29× |
| **A（Zipfian）** | 全 workload | **2f SLRU** on 原始 layout | **-39%**（411 → 249 ms）| 需要 warmup pass 先 dump hotpages |
| **B（Uniform）** | first-q | layers_5 on 原始 layout | **-47%**（463 → 244 µs） | ⚠️ 在 ta layout 上 layers_5 反而 +8%；B 不適合 ta |
| **B（Uniform）** | first-q | **2f SLRU** on 原始 layout | **-94%**（255 → 15 µs）| prefetch 7.5 ms，cold start 慢 30× |
| **B（Uniform）** | 全 workload | **2f SLRU** on 原始 layout | **-38%**（413 → 255 ms）| 需要 warmup pass 先 dump hotpages |
| **C（high-key）** | first-q | **2f SLRU** on 原始 layout | **-94%**（250 → 16 µs）| hot set 小，prefetch 只 1.9 ms，cold start 只慢 7.6× ← C 的甜蜜情境 |
| **C（high-key）** | first-q | **perpage on type-aware layout** | **-37%**（467 → 294 µs） | ta + perpage 是不需要 warmup pass 的最佳組合 |
| **C（high-key）** | first-q | **layers_92 (全部 interior) on 原始 layout** | **-46%**（491 → 265 µs） | 不改 layout，但要載全部 92 個 interior |
| **C（high-key）** | 全 workload | **2f SLRU** on 原始 layout | **-7%**（262 → 245 ms）| ⚠️ 收益小，因 baseline avg-q 已接近 readahead 下限 |
| **C（high-key）** | first-q | layers_5 on churned DB | **-10%**（avg）| 隨 churn 累積才看出效益（第四維 sudo drop_caches） |
| **C（high-key）** | first-q | **layers_92 on churned DB** | **-54%**（462 → 213 µs avg）| 第十維 posix_fadvise harness：N=92 是 churn-robust 的選擇，10 個 checkpoint 全部 -50% 以上 |

**速記：**
- 「**點開就看一筆**」（聯絡人、設定）→ **layers_5**（cold start 152 µs vs SLRU 7,500 µs）
- 「**開了會跑一整段**」（瀏覽列表、滑相簿）→ **2f SLRU**（全 workload 省 38%）
- 兩個都要 → 看 [prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md) 的 trade-off 矩陣

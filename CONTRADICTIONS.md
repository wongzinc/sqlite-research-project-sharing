# SQLite 冷啟動 Prefetch 研究 — 文件矛盾彙整

> 本檔為跨文件一致性審查的彙整清單,**僅作為審查紀錄,未改動任何原始文件**。
> 審查範圍:`sqlite-research-project-sharing/` 底下的 `REPORT.md`、`overall_results.md`、
> `overall_strategies.md`、`overall_workloads.md`、`strategies_explained.md`、
> `WORKLOAD_FILE_REFERENCE.md`。

出處縮寫(連結可點開):
**RP**=[REPORT.md](sqlite-research-project-sharing/REPORT.md)、
**OR**=[overall_results.md](sqlite-research-project-sharing/overall_results.md)、
**OS**=[overall_strategies.md](sqlite-research-project-sharing/overall_strategies.md)、
**OW**=[overall_workloads.md](sqlite-research-project-sharing/overall_workloads.md)、
**SE**=[strategies_explained.md](sqlite-research-project-sharing/strategies_explained.md)、
**WFR**=[WORKLOAD_FILE_REFERENCE.md](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md)。

性質:🔴 硬矛盾 / 🟠 待釐清 / 🟡 可調和 / ⚪ 編輯殘留。
（RP 行號為審查當下已被編輯過的版本。）

> **2026-06-22 P0 更新**:P0 pipeline(`run_p0.py` + `p0_env.sh` + harness `--verify-hotset`)上線並通過審查,**流程根因已從工具面堵住**:#24(機制不統一)→ 每 cell 同一條全機 `drop-caches` + 同一個 `warmer` 交付引擎;#27(步驟序)→ harness 序固定 `open/prepare(before-cold) → drop-caches → verify cold_pct → prefetch → verify delivery_pct → 首查`,`cold_pct>1%` 自動剔除。**數據類矛盾(#1–#16)P0 不能回溯改舊數字**,只能靠 master rerun 產生單一權威值、並刪掉舊 P1/P2/P3 表 + 從新 `summary_p0.csv` 重算每個 %;在那之前仍標 🔴。另補 **baseline(無 prefetch)臂**,improvement-% 才有分母(關係到 #2/#8/#13/#15/#16)。

---

## 主表:矛盾點彙整

| # | 類別 | 矛盾點 | 衝突的說法與出處 | 性質 |
|---|---|---|---|---|
| 1 | 數據 | Workload A 冷啟動 first-q baseline 多達 ~10 個值 | 318([RP:16](sqlite-research-project-sharing/REPORT.md#L16),[447](sqlite-research-project-sharing/REPORT.md#L447)) / 305([RP:424](sqlite-research-project-sharing/REPORT.md#L424)) / 404([RP:457](sqlite-research-project-sharing/REPORT.md#L457)) / 505([RP:530](sqlite-research-project-sharing/REPORT.md#L530));另 73/251/299.7/321/634([OR:55](sqlite-research-project-sharing/overall_results.md#L55),[210](sqlite-research-project-sharing/overall_results.md#L210),[942](sqlite-research-project-sharing/overall_results.md#L942)) | 🔴 |
| 2 | 數據 | layers_5 on A 改善% 五種 | −54%([OS:36](sqlite-research-project-sharing/overall_strategies.md#L36)) / −41~42%([OS:152](sqlite-research-project-sharing/overall_strategies.md#L152)) / −30%([OS:53](sqlite-research-project-sharing/overall_strategies.md#L53)) / −29%([RP §5.2](sqlite-research-project-sharing/REPORT.md#L443)) / −47%([OR:58](sqlite-research-project-sharing/overall_results.md#L58)) | 🔴 |
| 3 | 數據 | §8 結論算術錯 | 「318→127(**−69%**)」實為 −60%([RP:678](sqlite-research-project-sharing/REPORT.md#L678));且 preprocessing 可忽略卻又稱 e2e −68%([RP:679](sqlite-research-project-sharing/REPORT.md#L679)) | 🔴 |
| 4 | 數據 | Abstract 同病 | 「318→127」配「e2e −68%(preprocessing 1.1µs 可忽略)」——可忽略則應 ≈−60%([RP:16](sqlite-research-project-sharing/REPORT.md#L16),[52](sqlite-research-project-sharing/REPORT.md#L52)) | 🔴 |
| 5 | 數據 | §5.2 表 vs 同節圖2 | 表:baseline 318→127=**−60%**([RP:447-449](sqlite-research-project-sharing/REPORT.md#L447));圖2:baseline 404→127=**−69%**([RP:457](sqlite-research-project-sharing/REPORT.md#L457)) | 🔴 |
| 6 | 數據 | §5.2 表 vs §5.5.2 表(同一組 A 策略) | baseline 318 vs 505;layers_5 224 vs 296;1c+layers_5 127/−60% vs 160/−68%([RP:447](sqlite-research-project-sharing/REPORT.md#L447) vs [530-534](sqlite-research-project-sharing/REPORT.md#L530)) | 🔴 |
| 7 | 數據 | 2f SLRU「慢幾倍」全文不一 | 3–7×([RP:16](sqlite-research-project-sharing/REPORT.md#L16),[543](sqlite-research-project-sharing/REPORT.md#L543)) / 2–6×([RP:431](sqlite-research-project-sharing/REPORT.md#L431)) / 3.6×+261%([RP:538](sqlite-research-project-sharing/REPORT.md#L538));29×([OR:210](sqlite-research-project-sharing/overall_results.md#L210)) / 7×+625%([OR:1321](sqlite-research-project-sharing/overall_results.md#L1321));30× vs 1.9–6×([OS:319](sqlite-research-project-sharing/overall_strategies.md#L319) vs [335](sqlite-research-project-sharing/overall_strategies.md#L335)) | 🔴 |
| 8 | 數據 | load-all-92 on C + 「追平」方向反轉 | −46%([RP:55](sqlite-research-project-sharing/REPORT.md#L55)) vs −54%([RP:480](sqlite-research-project-sharing/REPORT.md#L480));Abstract 說 access(−47)勝 load-all(−46),§5.4 反成 access −48 < load-all −54 | 🔴 |
| 9 | 數據 | Workload C baseline | 671([RP:426](sqlite-research-project-sharing/REPORT.md#L426)) / 1,079(§5.4);4,918([OR:55](sqlite-research-project-sharing/overall_results.md#L55)) / 667([OR:1142](sqlite-research-project-sharing/overall_results.md#L1142)) / 468([OR:942](sqlite-research-project-sharing/overall_results.md#L942)) | 🔴 |
| 10 | 數據 | DB 總頁數 | 26,331(RP/OW/[SE:386](sqlite-research-project-sharing/strategies_explained.md#L386)) vs **25,613**([OS:437](sqlite-research-project-sharing/overall_strategies.md#L437),疑筆誤) | 🔴 |
| 11 | 數據 | 2f prefetch 開銷自身兩值 | A 7,255([OR:190](sqlite-research-project-sharing/overall_results.md#L190)) vs 7,478([OR:692](sqlite-research-project-sharing/overall_results.md#L692));B 7,478([OR:193](sqlite-research-project-sharing/overall_results.md#L193)) vs 7,614([OR:694](sqlite-research-project-sharing/overall_results.md#L694)) | 🔴 |
| 12 | 數據 | cgroup working set | 「20M ≪ working set ~16MB」方向算反(20>16)([OR:1112](sqlite-research-project-sharing/overall_results.md#L1112));RP「20M ≈ 1/5 working set」(暗示 ~100MB)([RP:16](sqlite-research-project-sharing/REPORT.md#L16)) | 🔴 |
| 13 | 數據 | churn 後 C×layers_92 改善 | −55.2%([OR:613](sqlite-research-project-sharing/overall_results.md#L613)) / −58%([OR:644](sqlite-research-project-sharing/overall_results.md#L644)) / −51%([OR:1334](sqlite-research-project-sharing/overall_results.md#L1334));RP −54%([RP:579](sqlite-research-project-sharing/REPORT.md#L579)) | 🔴 |
| 14 | 數據 | 第18維表 vs 同節文字 | 2e_K10 表 −47.6% vs 文字 −48.8%;layers_92 表 −46.1% vs 文字 −49.2%([OR:1547](sqlite-research-project-sharing/overall_results.md#L1547) vs [1558](sqlite-research-project-sharing/overall_results.md#L1558)) | 🔴 |
| 15 | 數據 | C 2e_K10 跨維度 | −83.9%(15維 [OR:1047](sqlite-research-project-sharing/overall_results.md#L1047)) vs −88%(16維 [OR:1165](sqlite-research-project-sharing/overall_results.md#L1165));RP −83% | 🔴 |
| 16 | 數據 | 2d C×1a 改善 | −47.2%([OR:942](sqlite-research-project-sharing/overall_results.md#L942)) / −47.6%([OR:952](sqlite-research-project-sharing/overall_results.md#L952)) / −48%([OR:959](sqlite-research-project-sharing/overall_results.md#L959)) / −46%([OR:1329](sqlite-research-project-sharing/overall_results.md#L1329)) | 🔴 |
| ~~17~~ | ~~理論~~ | ~~`MADV_WILLNEED` 保不保證載入~~ | ✅ **已解（2026-06-19）**：統一為「async hint、不阻塞、不保證、實測 range 模式只載 32/92 為本地佐證」。改寫位置：REPORT §6.1 / overall_strategies §2a/2b / overall_results 主表 + N sweep | ✅ |
| 18 | 理論 | 「載太多變慢」歸因 | ⚠️ **部分解（2026-06-19 第二輪）**：syscall overhead 可忽略（calibration ≈14 µs）此事實為 robust 結論；但「N>5 變慢」**現象本身**只在舊 P3 era 數據成立，當前 P1 dense sweep 已部分推翻（A 1b N=62 最佳、C 1a N=92 大勝、多數 cell plateau）。**完整因果敘事 pending P0 master rerun + per-cell majflt count**。內部 contradiction（成本可忽略 vs 載太多變慢）已先以 "pending" marker 表明、不再算內部不一致 | ⚠️ |
| 19 | 理論 | plateau vs U 型退化 | ⚠️ **部分解（2026-06-19 第二輪）**：原描述上 "U 形" / "plateau" 兩種看法互相打架的內部 contradiction 已表明（同一 phenomenon 在不同 (workload, layout) cell 表現不同形狀）；但「A on 1a 是哪種形狀、其他 cell 行為」**pending P0 master rerun** 才能定論。改寫位置：overall_strategies §2c 表 + 全 caption 改為 "P3 era 數字、pending P0 rerun" | ⚠️ |
| ~~20~~ | ~~理論~~ | ~~「leaves 自然在 cache」解釋 first-query~~ | ✅ **已解**：明示「first-q：leaf 仍 cold，layers_5 只移除 interior fault、仍付一次 leaf fault；穩態：hot leaves 已 warm，interior 才是唯一反覆需要的瓶頸」——two-window 拆解。改寫位置：REPORT §5.3 圖 4 caption / overall_results 主表 reading point | ✅ |
| 21 | 理論 | 1c 重排對 A/B 相反因果 | ⚠️ **部分解（2026-06-19 第二輪）**：seek distance hypothesis 已寫進去當 hedge；但 (a) 1c 對 A 加速 / 對 B 變慢的方向與強度都來自 P1 baseline（跨 pipeline 不可比）、(b) seek distance 假設**尚未量測**、(c) P0 rerun 後方向可能收斂或反轉。**論文最終用前必須等 P0 數字 + 補 leaf-fault distance 小實驗 verify**。改寫位置：REPORT §6.1 #3 已含完整 pending caveat | ⚠️ |
| ~~22~~ | ~~理論~~ | ~~layers_N 定義自我抵觸~~ | ✅ **已解**：嚴格定義 = qsort by file offset + take first N interior。「≈ B+tree 上 N 層」**只在 1c 成立**；1a/1b 不成立。**勘誤**：page 1 是 schema root 不是 items 表 root（CONTRADICTIONS 原 audit 跟我前一版都誤）。改寫位置：REPORT §4.2 / overall_strategies §2c | ✅ |
| ~~23~~ | ~~理論~~ | ~~multi-process cadence 規則相反~~ | ✅ **已解**：兩條規則不是兩個獨立 metric，是**同一條 trade-off frontier 的兩端**——cadence 小 = warm 但 overhead 高；cadence 大 = 省 overhead 但 first-q 退回 cold。實測 cadence=1s first-q 19 µs、30s 已退到 ~347 µs ≈ baseline。改寫位置：REPORT §6.1 footnote + §6.2.3 圖 8 caption | ✅ |
| 24 | 流程 | 冷啟動清快取機制三種 + RP 宣稱「一致可比」 | RP:`posix_fadvise`+「所有數字一致可比」([RP:107](sqlite-research-project-sharing/REPORT.md#L107),[132](sqlite-research-project-sharing/REPORT.md#L132));SE:`MADV_COLD→PAGEOUT→DONTNEED` 主+fadvise 補([SE:39](sqlite-research-project-sharing/strategies_explained.md#L39));OR:「機制不同**不能跨表比**,A 用 sudo drop_caches」([OR:45](sqlite-research-project-sharing/overall_results.md#L45),[61](sqlite-research-project-sharing/overall_results.md#L61)) | 🟠 **工具面已解(2026-06-22)**：P0 每 cell 統一 `madvise chain + 全機 drop-caches`,單一 `warmer` 引擎;**數據收斂待 master rerun** 取代舊表 |
| 25 | 流程 | 「免 warmup pass」誤貼 history 派 | 2d([OR:981](sqlite-research-project-sharing/overall_results.md#L981))、2e_K10([OS:271](sqlite-research-project-sharing/overall_strategies.md#L271)) 被稱「不需 warmup pass」;但定義為「看歷史=先跑一輪 dump」([RP:391](sqlite-research-project-sharing/REPORT.md#L391)) | ✅ **已解(2026-06-22)**：P0 `--regen-hotsets` Step A 明確做 warmup pass(drop→workload→殘留快照)重產 2d/2e/2f |
| 26 | 流程 | structure 工具名/命令簽章不一 | `prefetch_layers <db> <classify> 92 4096 range`([WFR:51](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md#L51),[145](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md#L145)) vs `prefetch test.db classify range`([SE:102](sqlite-research-project-sharing/strategies_explained.md#L102),[225](sqlite-research-project-sharing/strategies_explained.md#L225)) | ✅ **moot(2026-06-22)**：P0 把 native tool 降為離線 hotset 產生器,量測一律走 `warmer`,簽章不再在量測路徑上 |
| 27 | 流程 | harness 步驟序 / 「before≈0」 | SE 步①(evict 前)盤點卻稱「before≈0」([SE:37](sqlite-research-project-sharing/strategies_explained.md#L37),[92](sqlite-research-project-sharing/strategies_explained.md#L92));RP 把 open/prepare/cache_size=0/pre-clear mincore 放 clear 前([RP:311-314](sqlite-research-project-sharing/REPORT.md#L311)),SE timeline 無這些步 | ✅ **已解(2026-06-22)**：harness 序固定 `open/prepare(before-cold) → drop-caches → cold_pct → prefetch → delivery_pct → 首查`;open/prepare 摸到的 schema 頁會被後續全機 drop 清掉,故「before≈0」成立且可由 `cold_pct` 稽核;RP §3.3 已改寫對齊 |
| 28 | 流程 | workload 副本 symlink vs copy | A=symlink([WFR:76](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md#L76)) 有 md5 一致保證;B/C=「另一份 copy」([WFR:85](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md#L85),[94](sqlite-research-project-sharing/WORKLOAD_FILE_REFERENCE.md#L94)) 可能漂移 | ✅ **已解(2026-06-22)**：P0 freeze manifest 把三個 workload `.txt` 一併 checksum 凍結,`--verify-frozen` 把關 |
| 29 | 流程 | Workload D 規模標示 | 標「100,000 ops」([OW:196](sqlite-research-project-sharing/overall_workloads.md#L196)) 但實際只用「5,000×10=50,000」([OW:218](sqlite-research-project-sharing/overall_workloads.md#L218)) | 🔴 |
| ~~30~~ | ~~編輯~~ | ~~§2.3 TODO 殘留~~ | ✅ **已解（2026-06-19）**：TODO blockquote 移除，§2.3 開頭改為直接敘述 | ✅ |

**Bonus 順手修（程式碼）**：`prefetch_vacuum/src/prefetch.c:116-122` 的 range 模式
原本用 O(n²) bubble sort，跟做同件事的 `prefetch_layers.c:62` 用 `qsort`
不一致——已統一改用 qsort（新增 `cmp_ll` comparator，pattern 跟 prefetch_layers.c
完全一致）。**非正確性 bug**，純 code hygiene。Binary 已 rebuild。

---

## 附表:看似矛盾、查證後可調和(供參考,不必當缺陷修)

| # | 矛盾點 | 調和方式 | 性質 |
|---|---|---|---|
| R1 | 2f「跑完不要 evict」vs 每格 DONTNEED 清快取([OS:301](sqlite-research-project-sharing/overall_strategies.md#L301)) | resident set 先 dump 成 hotpages.csv 存磁碟,「不要 evict」指快照那一刻 | 🟡 |
| R2 | Workload C「uniform」vs「locality」([OW:159](sqlite-research-project-sharing/overall_workloads.md#L159),[103](sqlite-research-project-sharing/overall_workloads.md#L103)) | 鎖定檔尾區段(locality)＋區段內均勻(uniform),兩者同時成立 | 🟡 |
| R3 | 「七個策略」vs 列 8 個標籤([SE:9](sqlite-research-project-sharing/strategies_explained.md#L9)) | 3a/3b 已宣告為 2e 的對照子變體,非新策略([SE:293](sqlite-research-project-sharing/strategies_explained.md#L293)) | 🟡 |
| R4 | t=0 hotpages「不 decay」vs「24%→0.9% 衰退」([SE:168](sqlite-research-project-sharing/strategies_explained.md#L168),[406](sqlite-research-project-sharing/strategies_explained.md#L406)) | 前者尾端 append insert(0 頁移動),後者熱鍵 page-split,兩種 churn | 🟡 |
| R5 | VACUUM「別為 cold-start 做」([OS:62](sqlite-research-project-sharing/overall_strategies.md#L62)) vs「RAM 壓力下唯一全保留 layout」([OS:341](sqlite-research-project-sharing/overall_strategies.md#L341)) | 不同軸(scatter/效益 vs 縮檔塞 cgroup),但兩處建議方向相反、未在同處收束 | 🟠 |
| R6 | ta interior「2..93」vs「2..52」([OR:313](sqlite-research-project-sharing/overall_results.md#L313),[791](sqlite-research-project-sharing/overall_results.md#L791)) | 51 table interior(2..52)＋41 index interior(53..93)=全部 92(2..93),子集關係 | 🟡 |
| R7 | DB 大小 102MB vs 107.8MB([RP:16](sqlite-research-project-sharing/REPORT.md#L16) vs [OR:253](sqlite-research-project-sharing/overall_results.md#L253)) | 102=邏輯資料、107.8=on-disk 檔案大小 | 🟡 |

---

## 統計與優先順序

**統計**:🔴 硬矛盾 28 條、⚪ 編輯殘留 1 條、🟠 待釐清 1 條、🟡 可調和 6 條。

**兩個「根因」最該優先處理**:

1. **第 24 條(冷啟動清快取機制不統一)** — companion 文件白紙黑字說各維度機制不同、
   「不能跨表比較」,報告卻宣稱「所有數字一致可比」並把不同機制的數字拉進同一張比較表。
   這是第 1 / 6 / 7 / 9 等一票數據矛盾的**流程根源**。**✅ 工具面已解(2026-06-22)**:P0
   鎖定單一清快取機制(全機 `drop-caches`)與單一交付引擎(`warmer`),每 cell 同條流程。
   **剩下的是執行**:跑 P0 master batch 產生單一權威數字、刪掉舊 P1/P2/P3 表、從新
   `summary_p0.csv` 重算所有 %,#1/#6/#7/#9 等才真正關閉。

2. **第 18–20 條(madvise 語意、「載太多變慢」歸因、leaves 自然熱)** — 這幾條是論文
   因果敘事的主梁,且彼此相互牽連。建議:統一 `MADV_WILLNEED` 的描述(async hint、
   不保證即時載入),並把「first-query(冷)」與「avg/穩態(熱)」兩種 metric 的解釋分開。

> 註:本清單為審查當下狀態。`REPORT.md` 在審查期間曾被編輯(行號位移、新增 Yi et al. [2026]
> 等),引用行號以本檔產生時為準;companion 文件未變動。

# Claude Code 主控執行文檔：Type-aware SQLite + Cold-Start (Level 1) → Physical Segregation in FEMU (Level 2)

> 這份文檔是你（Claude Code）的唯一作業依據。從上到下嚴格照做。
> 整份分成 **PART A (Level 1)** 與 **PART B (Level 2)**，先完成 A 再進 B。
> 每個 Phase 結束都有「驗證關卡 + commit」，**沒過關卡不准進下一個 Phase**。

---

## 0. 最高指導原則（每個 Phase 開始前都要重讀這一段）

1. **先探索，再動手。** 每個 Part 的 Phase 0 都要先寫 PLAN 文件並 commit，才開始實作。
2. **不要相信任何宣稱的 API ——包含這份文檔。** 本文檔裡所有 struct 名稱、欄位、ioctl、flag、函式名，都只是「設計意圖」。Phase 0 一律寫小程式或用 `grep`/`find` 實測確認，把實測結論寫進 PLAN。**若實測結果與本文檔不符，停下來、在回覆裡說明落差、不要硬套本文檔的寫法。**
3. **大量重用 repo 既有資產。** repo 已有 page classifier、benchmark harness、residency checker、drop_caches 腳本、testdb builder、plotting 腳本。共用邏輯抽成共享模組，**不要複製貼上、不要重寫已存在的東西**。
4. **絕不捏造或美化量測數據。** 數據說什麼就報什麼。**null result（沒看到改善）是有效且預期內的結果**，如實報告並解釋原因。嚴禁為了「看起來有效」灌水。
5. **baseline 與 treatment 必須是同一套程式**，用 config / env var 切換，確保公平比較。
6. **不可破壞 SQLite 正確性與 durability。** 每個會動到寫入路徑的 Phase 結束都要過 `PRAGMA integrity_check`，並做一次 crash/kill 測試。
7. **逐 Phase commit**，message 清楚，保持 diff 可審查。
8. **卡住或遇到模稜兩可的設計決策時，停下來說明，不要亂猜。** 文檔裡標 `⛔ STOP-AND-REPORT` 的地方是強制停點。
9. **不要 over-engineer。** Level 1 不是 SPDK；Level 2 不是完整 NVMe Directives 標準。維持 PoC 範圍。
10. **所有產出都是 repo 內實際存在、已 commit、可編譯的實體檔案**，不是文字描述、不是只貼 diff 片段。

---

## 0.1 範圍誠實聲明（這是要寫進 README 的，不是免責話術）

- **Level 1 的 shadow tagging 在本整合版有實際工作：** VFS 在寫入時分類，並把每頁的 class 記進一張 in-RAM **metadata 活表**（page number → class）；build 結束時把活表持久化成 hotset sidecar。實際寫入仍委派 parent VFS，**Level 1 不注入真 kernel hint**（真 hint 屬 Level 2 FEMU 階段）。在一般硬體上，shadow tagging 對 latency 是 no-op，但它的「分類產出」直接餵給 warmer。
- **Level 1 真正會量到 cold-start 改善的是 prefetch warmer，不是 VFS。** VFS 是「分類基礎建設 + 即時產出 hotset」；warmer 是「把分類結果拿去暖 page cache」。
- **hotset 來源（整合後的主路徑）= 活表持久化；`classify_pages.c` 降級為 oracle**（驗證活表正確性、算 precision/recall、活表不可用時的 fallback）。
- **hot-leaf 學習式 prefetch 是「觀察出來」的可選 ablation 條件**，不是結構性的。它 workload-dependent，必須遵守 train/test 切分（見 F11），且做成可開關，誠實量「到底有沒有幫助」。
- **Level 2 進入裸裝置 / 無檔案系統領域**，採最小 PoC 範圍：一個 namespace = 一個 DB、LBA identity mapping、單 process 單 connection、不支援並發、不掛 fs。這些是明確限制，要寫進文件，不可隱藏。
- **Level 2 純隔離（identity LBA + 同種 NAND）不會自動讓 TTFQ 崩塌。** 真正讓 cold-read 變快的槓桿是 **fast tier**（把 INTERNAL 與 HOT-LEAF line 設成較低讀延遲）。所以純隔離本身的 TTFQ 改善可能很小、甚至落在雜訊內 —— 這是預期結果，當假設量測。
- **Level 2 採 temperature-aware 三 stream（整合後）：** stream 0 = COLD/DEFAULT（cold leaf + OTHER）、stream 1 = INTERNAL、stream 2 = HOT-LEAF。temperature 在 build 時**一次定死**（依 Level 1 profile），PoC 不做執行期 temperature 遷移（那超出範圍）。因為 hot/cold 非結構性，VFS 寫入時要靠 Level 1 產出的 hot-leaf 清單才能分 stream → 導致 **two-pass build**（見 §B.0）。

---

## 0.2 全域禁止事項（這些會直接毀掉專案，當成硬性紅線）

| # | 禁止 | 為什麼 |
|---|------|--------|
| F1 | VFS 自開任何指向 DB 檔的 `fd` | POSIX fcntl advisory lock 語意：同一 process 內 `close()` 掉指向該 inode 的**任一** fd，會釋放該 process 在該 inode 上的**所有**鎖 → 摧毀 SQLite 自己持有的鎖 → `SQLITE_BUSY` 或 DB 損毀。一律委派 parent xWrite。|
| F2 | VFS 內走訪 freelist 做分類 | 走 freelist 是 O(N) 多次同步 disk I/O，會讓寫入崩潰甚至死鎖。VFS 只能用 O(1) byte-signature 啟發式，猜不到就 OTHER。|
| F3 | reach into parent VFS 的 `unixFile` 內部 struct 去挖 fd | 版本一變就壞。|
| F4 | warmer 或 VFS 自建記憶體 cache buffer 存頁面**內容** | 一旦自有 data cache 就要負責跟 SQLite Pager 維持 coherence，極易讀到舊資料。warmer 保持 stateless，只暖 OS page cache。**註：page→class 的 metadata 活表不算違反 F4**——它只記「哪頁是哪類」，不存頁面內容，沒有 coherence 問題；持久化的 hotset / hotleaf sidecar 同理。|
| F5 | 量到 warm cache | 每次 run 前務必 drop cache + 開新 process。沒 root 不能 drop cache → harness **大聲報錯中止**，絕不默默量。|
| F6 | hotset / hotleaf sidecar 過期卻照用 | benchmark 紀律：Build DB → 產 sidecar → 之後唯讀（凍結 DB）。**機制防線**：sidecar 內存 SQLite file change counter（header offset 24）；cold start 先比對，不符就 best-effort 或跳過、**不重建**（cold start 要快），並 log。不可在 counter 不符時靜默全用。|
| F7 | (Level 2) passthrough 寫入路徑做靜默 RMW | RMW 的 read-then-write 非原子、有 torn-write 風險；且會掩蓋「對齊假設被違反」的訊號。不對齊就**斷言失敗、大聲報錯停止**。|
| F8 | (Level 2) 用 `struct nvme_user_io` 送 passthrough | 它沒有 cdw10–15 欄位，塞不了 cdw13。必用 `struct nvme_passthru_cmd` + `ioctl(fd, NVME_IOCTL_IO_CMD, &cmd)`。|
| F9 | (Level 2) 把已建好的完整 DB `dd` 進裸裝置 | 那樣資料不帶 tag = 沒有隔離。測試 DB 必須在 passthrough 模式下「邊灌邊分流」。|
| F10 | 美化 / 灌水任何量測數據 | null result 是有效結果。|
| F11 | (hot-leaf) profile 與 benchmark 用同一批 query | 等於先偷看答案再考試，hot-leaf 命中率虛高 = 灌水。**硬規則：profiling workload 與 cold-start benchmark workload 必須切分（train/test disjoint）**，並在報告明說 hot-leaf 是 workload-dependent。|

---

## 0.3 通用 Phase 收尾流程（每個 Phase 結束都跑這一套）

```
1. 編譯通過（無 warning 視情況；error 一律修掉）
2. 跑該 Phase 的「驗證關卡」全部通過
3. 若動到寫入路徑：PRAGMA integrity_check = ok
4. git add -A && git commit -m "<Phase X>: <一句話說明做了什麼>"
5. 在回覆裡簡述：這個 Phase 做了什麼、關卡結果、有沒有偏離本文檔的地方
```

---
---

# PART A — LEVEL 1

> 目標：type-aware shadow-tagging VFS + 獨立 prefetch warmer + 嚴謹 cold-start 量測 + README。

## A. 專案根目錄

Level 1 直接在既有 research repo 內操作；Level 2 會把它整理成 §B.0 的結構。先確立根目錄（即 `wongzinc/sqlite-research-project-sharing` 的 clone）。**不要把檔案散落到 /tmp、家目錄、系統目錄。**

---

## Phase A0 — 探索與環境盤點 → `PLAN.md`

### A0.1 取得 / 確認 repo
- Clone（或在已 clone 目錄內操作）`https://github.com/wongzinc/sqlite-research-project-sharing`。

### A0.2 完整讀過並做筆記（列進 PLAN.md 的「既有資產盤點」）
- 文件：`README.md`、`BENCHMARK_HARNESS.md`、`RESIDENCY_CHECKER.md`、`SQLITE_PREFETCH_CHURN_EXPERIMENT.md`、`16week_plan.jsx`
- 程式：`classify_pages.c`、`benchmark_harness.c`、`residency_checker.c`、`build_testdb.py`、`testdb_builder.py`、`drop_caches.sh`、`benchmark_harness_*.py`、`sqlite_prefetch_churn_experiment.py`
- 資料夾：`prefetch_vacuum/`、`multiprocess/`、`workload/` 與結果檔

> ⚠️ 若上述任何檔名實際不存在或名稱不同，**以實際 `ls`/`find` 結果為準**，在 PLAN.md 記錄真實檔名與用途，不要假設。

### A0.3 環境盤點 + API 實測（每一項都要實際跑，結論寫進 PLAN.md）
- `uname -r`、`gcc --version`、是否有 root（`id -u`）。
- `liburing` 是否安裝（`pkg-config --exists liburing; echo $?`、找 header）；寫一支最小 io_uring 讀寫程式確認能跑。
- **write hint 機制實測**（用來印證 §0.1「Level 1 不注入真 hint」的判斷，也避免之後誤用）：
  - 小程式測 `fcntl(fd, F_SET_RW_HINT, ...)` / `F_SET_FILE_RW_HINT` 是否成功。
  - 確認 `pwritev2()` 的 `RWF_*` flag 裡**有沒有** write-life 類 flag（預期沒有——write-life 常數是 `RWH_WRITE_LIFE_*`，屬 fcntl 不是 pwritev2 flag；務必實測記錄）。
  - 確認 io_uring 的 write SQE **有沒有** per-I/O hint 欄位。
- SQLite 版本、有無 `sqlite3.h`、能否取得 amalgamation 原始碼。
- 測試裝置與檔案系統：`df -T`、`lsblk`。
- 編譯並試跑 `classify_pages.c`，**確認其實際輸出格式**（預期類似 `page_number,page_type,file_offset`，但以實跑為準）。

### A0.4 產出 `PLAN.md` 並 commit
內容：既有資產盤點（真實檔名）、環境/API 實測結論、各 Phase 步驟與檔案清單。

> **驗證關卡 A0：** PLAN.md 存在且含上述三大塊；所有「實測項」都有實際指令輸出佐證，不是憑空寫結論。→ commit。

---

## Phase A1 — Type-aware SQLite VFS（shadow tagging）

### A1.1 抽出 O(1) 共享分類模組 `page_classify.c` / `page_classify.h`

這是 Level 1 與 Level 2 共用的核心，**只看 byte signature、O(1)、零額外 I/O**。介面：

```c
// page_classify.h
typedef enum { PAGE_OTHER = 0, PAGE_INTERNAL = 1, PAGE_LEAF = 2 } page_class_t;

// is_page1: 此 buffer 是否為 DB 的 page 1 (iOfst == 0)
int is_internal_node(const unsigned char *buf, int is_page1);
int is_leaf_node(const unsigned char *buf, int is_page1);
page_class_t classify_page(const unsigned char *buf, int is_page1);

// 從 db header 讀 page size：offset 16, big-endian 2-byte
// 注意特例：該值若為 1 代表 page size = 65536
unsigned int read_page_size_from_header(const unsigned char *buf);
```

**分類規則（釘死，不要自由發揮）：**
- 取要檢查的 b-tree flag byte：
  - 若 `is_page1`（iOfst == 0）：檢查 `buf[100]`（b-tree flag 在 100-byte db header 之後）。
  - 否則：檢查 `buf[0]`。
- 對該 byte 判斷：
  - `0x05` interior table / `0x02` interior index → **INTERNAL**
  - `0x0D` leaf table / `0x0A` leaf index → **LEAF**
  - 其餘 → **OTHER**
- **嚴禁在此函式做任何 I/O、走 freelist（紅線 F2）。**

> O(1) 啟發式會有偽陽性（非 b-tree page 的該 byte 剛好等於上述值）。**不要假裝它精確**，Phase A3 會量化它的 precision/recall。

**`classify_pages.c` 重構：** 把它原本的「byte 判斷」邏輯改成呼叫這份共享模組，確保 offline classifier 與 runtime VFS **共用同一份程式碼**（驗收要求）。offline 額外能精確走 freelist trunk/leaf chain、處理 lock-byte page，那部分保留在 `classify_pages.c`，不要塞進共享模組。

**unit test：** 為 `page_classify` 寫 unit test（手刻幾個已知 signature 的 4KB buffer，驗證分類正確、含 page1 特例、含偽陽性邊界）。

### A1.2 VFS 本體（shim，鎖機制 100% 不動）

`type_aware_vfs.c` / `type_aware_vfs.h`：
- `sqlite3_vfs_find(NULL)` 取得預設 unix VFS 當 parent；`sqlite3_vfs_register` 註冊 shim VFS。
- 所有方法**委派 parent**，只有 `xWrite` 多做一件事。
- shim 的 `sqlite3_file` **包住** parent 的 `sqlite3_file`（不是繼承內部 struct）。
- **只對 `SQLITE_OPEN_MAIN_DB` 的檔案分類**；`SQLITE_OPEN_WAL`、`SQLITE_OPEN_MAIN_JOURNAL`、temp 等全部直接委派 parent。
- `xWrite`（main DB）：先用 §A1.1 的 O(1) 函式分類，**把該頁的 class 寫進 in-RAM metadata 活表**（page number → class，例如一個按 page number 索引的緊湊陣列），並更新 INTERNAL/LEAF/OTHER 計數器，**然後呼叫 parent 的 xWrite 完成實際寫入**。

> ⛔ **硬性規定（紅線 F1/F3）：** VFS 嚴禁自己 `open()` 任何指向 DB 檔的 fd，嚴禁挖 parent 的內部 fd。委派 parent xWrite 就完全避開 POSIX 鎖地雷。

### A1.3 Shadow tagging = 維護活表（這版的真正工作，不是純計數器）
- **in-RAM metadata 活表**：page number → class。每次 main DB 寫入就增量更新該頁的 class（頁被改寫成別的型別就改標記）。這是 metadata，**不存頁面內容，不違反 F4**。
- 計數器：INTERNAL / LEAF / OTHER 各一，供統計用。
- **持久化**：build 結束（DB 定版）時，把活表中所有 INTERNAL page 的 `(page_number, file_offset)` 寫成 sidecar `<db>.hotset`，並把當下 SQLite **file change counter**（header offset 24，big-endian 4-byte）一併寫進 sidecar header。這份「寫的時候順手標、結束直接倒出」比事後重掃整個 DB 省。
- `classify_pages.c`（precise、走 freelist）保留為 **oracle**：A3 用它驗活表正確性、算 precision/recall；活表不可用時當 fallback 重建 hotset。
- 可選 tag log `(offset, class, timestamp)`，供研究與未來 FEMU 整合用。
- 全部用 env var 開關（baseline 與 treatment 同一套程式，§0 原則 5）。

> **驗證關卡 A1：**
> 1. 編譯通過，SQLite 跑在 shim VFS 上正常讀寫。
> 2. 跑一段實際 workload → `PRAGMA integrity_check` = ok。
> 3. crash 測試：寫入中途 `kill -9` → 重開 → `integrity_check` = ok（因只委派 parent，應很容易過，但仍要驗）。
> 4. `page_classify` unit test 全綠。
> 5. **活表正確性**：build 後把活表產的 hotset 與 `classify_pages.c` oracle 的 INTERNAL 集合比對，差異即 O(1) 啟發式的偽陽/偽陰，記錄下來（A3 會量化）。
> → commit。

---

## Phase A2 — Cold-start Prefetch Warmer（獨立工具，真正會量到改善）

設計成**獨立的 warmer 程式**，由 harness 在 SQLite 開檔**之前**執行（此時沒鎖、沒 fd 衝突、沒 cache coherence 問題）。

### A2.1 hotset 來源（整合後：活表為主，oracle 為輔）
- **主路徑**：用 A1.3 在 build 結束持久化的 `<db>.hotset`（由 shadow-tagging 活表倒出）。這是預設來源。
- **oracle / fallback 路徑**：`classify_pages.c` 分析最終狀態 DB 產生 precise hotset。用於驗證主路徑、或主路徑缺失時重建。
- **過期防線（紅線 F6）**：sidecar 內含 file change counter。warmer 啟動時讀當前 DB 的 counter 比對：
  - 相符 → 全用（benchmark 凍結 DB 必然相符）。
  - 不符 → best-effort（只暖仍合法的部分）或直接跳過，**不重建**（cold start 要快），並 log 警告。
- ⛔ benchmark 紀律：產 sidecar 後 DB 唯讀，不得 INSERT/UPDATE/VACUUM。

### A2.2 Runtime：transparent warming
- warmer 開**自己的** fd（安全：SQLite 還沒 open DB），讀 sidecar，把那些 page 暖進 OS page cache，然後 `close` fd。
- ⛔ **紅線 F4：** 嚴禁在 warmer 內建記憶體 buffer 當 data cache。保持 stateless，只暖 OS page cache，SQLite 後續常規 xRead 自然命中。
- 暖法（擇一；Phase A0 確認 liburing 可用就優先 io_uring）：
  - **io_uring batched read**：把各 page 一次平行讀進一塊**用完即丟的 scratch buffer**（只為觸發 OS 把頁讀進 page cache）。
  - 或 `posix_fadvise(fd, off, len, POSIX_FADV_WILLNEED)` / `readahead()`。
  - 注意：`posix_fadvise` 是給 **fd** 的；`posix_madvise` 是給 mmap 記憶體的，**別用錯**。
  - `fadvise` 只是 best-effort 提示；**若要確保 page 確實 resident，就實際把 bytes 讀出來**。

### A2.3 （可選）Hot-leaf 學習式 prefetch
> 這是 ablation 用的可選臂。internal 是結構推出來的；hot-leaf 是觀察出來的、workload-dependent，**必須誠實**。

- **profiling pass**：在一個 **training workload** 上跑 DB，instrument xRead（或用獨立 profiling harness）對每頁 leaf 累計借閱次數（read tally）。
- 挑 top-K 最常被讀的 leaf → sidecar `<db>.hotleaf`（同樣寫入 file change counter）。
- warmer 增加開關：`WARM_HOTLEAF=1` 時，除 INTERNAL 外也照 `.hotleaf` 暖 hot leaf。
- ⛔ **紅線 F11**：profiling 的 training workload 與 A3 cold-start benchmark 的 workload **必須 disjoint**。報告明說 hot-leaf 是 workload-dependent，並說明 train/test 怎麼切。

### A2.4 暖的時機與優先序（避免拖累 TTFQ — 重要）
> 問題：暖不是免費的，要先把那些頁從冷 disk 讀進來。若「先暖完整批、再跑第一個 query」，暖的時間就**直接加在 TTFQ 上**；而一次 point lookup 只走到「深度」那幾個 internal，warmer 卻暖了「全部」internal → 對單一查詢是巨大的**過度預取**。所以暖是「攤在多個 query 上」才划算，**不可預設整批同步暖**。

實作三段策略，用 env 切換：

- **(策略 B) 樹頂優先、只同步暖樹頂**：hotset 依「樹的層數」標優先序（root → 上層 → 下層）。同步只暖前 K 層（root + 上面 1–2 層；數量極少、很快），就能塌掉「深層散落、要一頁追一頁」的鏈，**連第一個 query 都受惠**。
  - 層數來源：用 `classify_pages.c`（oracle，本來就走樹）或從 b-tree roots 做一次淺層 BFS，在產 hotset 時算出每頁的 level/priority 寫進 sidecar。拿不到層資訊時 fall back 成「平坦暖全部」。
- **(策略 A) 其餘丟背景、非阻塞**：剩下的 internal 用背景 thread（io_uring）或 `posix_fadvise(WILLNEED)`（非阻塞提示）邊跑 query 邊補，**第一個 query 不被整批暖卡住**。
- **(回本點 budget)**：背景要補多少由預期 query 數決定，用 env 設上限（如 `WARM_MAX_PAGES`）。暖一次成本固定、每個 query 省的有限 → 要跑到「累積省下的 > 暖的成本」才回本。**若情境是「開檔→一個 query→關檔」，預設別暖**（淨虧）。

env 開關建議：`WARM_MODE ∈ {off, top, full, top+bg}`、`WARM_TOP_LEVELS=K`、`WARM_MAX_PAGES=N`。baseline 與各 treatment 同一套程式、只切 env。

> **驗證關卡 A2：** 用 repo 的 `residency_checker.c` 驗證暖完後目標 page **確實在 page cache 裡**（internal-only 與 internal+hotleaf 兩種都驗）。→ commit。

---

## Phase A3 — Cold-start Latency 量測（最重要）

### A3.1 指標
- **TTFQ (Time-To-First-Query)**：process 啟動 / DB open 到第一個 query 回傳，cache 全冷。**必須報兩個版本**（見 A3.7）：不含 warmer 時間、含 warmer 時間。
- **Warmer wall-clock**：warmer 從開始到暖完的時間，單獨量、單獨報（用來推導「含 warmer 時間的 TTFQ」）。
- **Time-to-warm**：前 N 個 query（例如 100）累計時間。
- Cold path 的 read I/O 數量與 read amplification。
- 每個 query 的 latency 分佈（cold path）。
- **O(1) 啟發式準確度**：全 DB 跑 O(1) 啟發式分類 vs `classify_pages.c` ground truth，報告 **precision / recall**。
- 可選：用 `residency_checker.c` 觀察 INTERNAL page residency 變化。

### A3.2 Cold-cache 紀律（沒做對整個量測就無效）
- 每次 run 前用 `drop_caches.sh`（`echo 3 > /proc/sys/vm/drop_caches`）清 cache。
- 每次 run 用**全新 process**。
- ⛔ **紅線 F5：** 無法清 cache（沒 root）時，harness **大聲報錯中止**，絕不默默量 warm cache。

### A3.3 比較條件（同一 DB、同一 workload、同一機器）
- **(A) baseline**：預設 unix VFS，cold，不跑 warmer。
- **(B) treatment — internal-only**：cold，warmer 只暖 INTERNAL。← 對照重點。
- **(B2) treatment — internal + hot-leaf**（可選，需 A2.3）：cold，warmer 暖 INTERNAL + hot leaf。**必須遵守 F11 train/test 切分。**
- **(C) 參考上界**：warm cache 跑一次。
- 另外**獨立報告**：type-aware VFS 的分類統計（INTERNAL/LEAF/OTHER 寫入比例）與啟發式準確度。
  - 注意：shadow-tagging 本身**不改變 latency**，所以它不是獨立 latency 條件，但統計數據要報。
  - **precision/recall 直接 = 你實際用的 hotset 品質**（因為主路徑 hotset 來自啟發式活表），不只是抽象數字。

### A3.4 嚴格管線順序（避免 sidecar 過期）
```
Build Test DB → 產生 hotset → drop caches → 跑 warmer(條件B) → 執行 read benchmark
```
- 產生 hotset 之後**嚴禁任何寫入**。
- benchmark DB 設 `PRAGMA journal_mode = DELETE`（或 TRUNCATE），避開 WAL frame header，本次只專注 main DB cold start。

### A3.4b 「禁寫」只保護「凍結窗口」那幾秒，不是整個 benchmark（重要澄清）
> 真實 cold start 不會是純讀；別把 §F6 的「禁寫」誤解成「整個 benchmark 不准有寫」。把時間軸拆三段就清楚：

- **建 DB（寫入非寫不可）**：DB 是用一堆 INSERT「長」出來的；Level 2 還必須在 passthrough 模式下建，tag 才會跟著寫入下去、segregation 才成形。
- **凍結窗口（唯一禁寫的一小段，約幾秒）**：`產 hotset → drop caches → 跑 warmer → 量測開始` 這一窄段。hotset 是「**這一刻** DB 的快照」，你接下來要量的也是「這一刻」的 DB；中間插一筆寫 → 樹 rebalance → 清單對不上實際 DB → 暖錯頁。**禁寫禁的是這幾秒，不是一輩子。**
- **量測（之後可混寫）**：cold start 第一波讀打到空 cache，warmer 已把「當下這版」的 internal 暖好 → 就在這一瞬間省到。**第一波讀命中後 cache 自然變熱，hotset 任務已完成**；之後 workload 開始寫、樹微調，動到的是「已經熱了的 cache」，動不到那筆已付掉/省掉的 cold-start 成本。所以**量測過程中混寫在方法上完全 OK**。

**為什麼 headline 畫成純讀**：那是 OFAT（one-factor-at-a-time）的 controlled default——把要量的東西（cold-start 讀路徑加速）單獨拉出來給一個乾淨、不受干擾的數字，不是宣稱真實世界純讀。

**讀寫混合 = 「何時有用」的敏感度 sweep**（對應 §A3.3 honest 預期與 null result）：`100% read → 幫最多`、`混一點寫 → 幫少一點`、`寫很多 → 中性甚至變慢`（即「寫多」negative space，要誠實報）。

**直覺補充**：寫入也要先沿 B-Tree 往下找插入點（下行時也讀 internal node），所以暖好的 internal 對「寫的下行」同樣有幫助；真正侵蝕效益的是寫造成的 **rebalance churn**，不是「有寫」本身。

### A3.5 統計嚴謹度
- 每個條件至少跑 **20–30 次**。
- 報告 **median、p95、p99、min、stdev**（不要只報 mean，cold start 是 tail-sensitive 的）。
- 用 `taskset` 綁核降噪；記錄機器規格、kernel、檔案系統、裝置。

### A3.6 使用既有 harness
- 讀 `BENCHMARK_HARNESS.md`，看 `benchmark_harness.c` 已量了什麼。**能用就用，不夠就擴充**（缺 TTFQ 或 cold-path I/O 計數就補上）。
- 測試 DB 用既有 `build_testdb.py` / `testdb_builder.py` 與 workload 檔；**確認 B-Tree 夠深（多層 interior），internal node 才有意義** —— 太淺就擴充 builder（數百萬列 + index）。
- 結果輸出 CSV/JSON；**重用既有 plotting 腳本**產生 cold-start latency 比較圖。

### A3.7 TTFQ 的兩種報法（誠實 — 跟 warmer 設計綁在一起）
> 你的管線是「warmer 先跑 → 才開 SQLite 量 TTFQ」，所以 warmer 的時間**沒被算進 TTFQ**。這在「部署有啟動空檔、warmer 能跟其他啟動工作平行（策略 C）」時是公平的；但若 warmer 其實卡在關鍵路徑上，這樣量就**高估**了好處。所以**必須兩種都報**，不可只挑好看的：

- **TTFQ（不含 warmer 時間）**：從 DB open 量起，假設 warmer 已在背景/空檔跑完。
- **TTFQ（含 warmer 時間）= warmer wall-clock + 上者**：假設 warmer 卡在關鍵路徑。
- **Time-to-warm（前 N 個 query 累計）**：不受上面爭議影響，且正是 warmer 真正發光處（好處本來就攤在多個 query）。

真相落在前兩個數字中間，看部署有沒有空檔。**兩個都報出來才不會騙到自己**，這條直接接上「null result / 不灌水」的誠實線。注意：策略 B（只同步暖樹頂）會讓「含 warmer 時間」那版的懲罰小很多，因為同步暖的只有樹頂那一小撮——這個對比本身就是值得報的結果。

> **驗證關卡 A3：**
> 1. harness 自動完成 §A3.4 管線；無 root 會中止（驗一次）。
> 2. 輸出含 median/p95/p99 的統計 CSV/JSON + 比較圖。
> 3. 有 baseline vs warmer 數據 + 啟發式 precision/recall 數字。
> 4. **TTFQ 兩版都報**：不含 warmer 時間、含 warmer 時間（+ warmer wall-clock + time-to-warm）。
> 5. **若 (B) 相對 (A) 沒看到明顯改善 → 如實報告 null result 並解釋**（Level 1 在一般機器上很可能如此）。
> → commit。

---

## Phase A4 — `README.md` 與可重現性

- README 內容：type-aware VFS 與 warmer 是什麼、cross-layer 動機（一段）、架構說明、相依與環境需求（kernel 版本 / liburing / root）、如何 build、如何跑 baseline vs treatment、如何端到端重現（一個腳本）。
- **誠實的結果區塊**：呈現實際數據，並明說限制——shadow tagging 對 latency 是 by design 的 no-op、真正的 NVMe stream tagging 屬未來 FEMU 階段、warmer 的改善依賴 OS page cache 行為；**TTFQ 同時呈現「含/不含 warmer 時間」兩版**，並說明 warmer 是「攤在多個 query 上才回本」的投資（開檔→一個 query→關檔的情境不該暖）。
- 提供 `run_coldstart_benchmark.sh`（或 make target）一鍵完成 §A3.4 完整管線。

> **驗證關卡 A4：** 在乾淨環境照 README 一鍵重現成功。→ commit。

### Level 1 驗收 checklist（全部要打勾才算 A 完成）
- [ ] type-aware VFS 能 build，SQLite 正常讀寫，`integrity_check` 過，crash 測試過。
- [ ] xWrite 只委派 parent + O(1) 分類，**無自開 fd、無 freelist 走訪**。
- [ ] O(1) 分類與 offline classifier **共用同一份程式碼**，有 unit test。
- [ ] warmer 獨立、stateless、只暖 OS page cache，殘留可用 residency_checker 驗。
- [ ] **warmer 暖法可切換（off/top/full/top+bg）；樹頂優先同步暖、其餘背景非阻塞，第一個 query 不被整批暖卡住。**
- [ ] **TTFQ 報兩版（含/不含 warmer 時間）+ warmer wall-clock + time-to-warm；不挑好看的單報。**
- [ ] **shadow-tagging 活表能即時維護並在 build 結束持久化成 hotset；file change counter 過期偵測可運作。**
- [ ] **（可選）hot-leaf profiling 與 prefetch 可開關，且 train/test 切分有落實（F11）。**
- [ ] tagging/prefetch 可用 config/env var 開關，baseline 與 treatment 同一套程式。
- [ ] cold-start harness 可重現、自動完成管線、輸出 median/p95/p99。
- [ ] 有 baseline vs warmer 數據與圖 + 啟發式準確度數字。
- [ ] README 完整且結果誠實（含 null result 與限制）。
- [ ] 每個 Phase 都有 commit。

---
---

# PART B — LEVEL 2：Physical Segregation in FEMU

> 角色：同時熟悉 Linux NVMe stack 與 SSD FTL 韌體的系統工程師。
> 目標：讓 SQLite B-Tree 的 internal node 與 leaf node 在 FEMU SSD 模擬器內被寫進**不同實體 block (line)**。
> 雙面動刀：(1) host VFS 用 NVMe passthrough 把 `stream_id` 夾在寫入指令；(2) FEMU NVMe 前端 + blackbox FTL 依 stream_id 分流，GC 維持隔離。

## B.0 關鍵架構決定（先在此釘死，不准模稜兩可）

| 項目 | 決定 |
|------|------|
| 指令欄位 | `stream_id` 一律放 NVMe Write 指令的 **CDW13**。Host 用 `struct nvme_passthru_cmd.cdw13`；FEMU 在 `NvmeRwCmd` 讀對應欄位（CDW13 對 RW 指令即 **dsmgmt**）。**不准用 cdw12 / apptag 這種寫法。** |
| ioctl / struct | `struct nvme_passthru_cmd` + `ioctl(fd, NVME_IOCTL_IO_CMD, &cmd)`。**不要用 `struct nvme_user_io`**（紅線 F8）。 |
| LBA 映射 | identity mapping：`SLBA = iOfst / lba_size`。不實作 host 端 block allocator。 |
| stream_id 取值 | **0 = COLD/DEFAULT（cold leaf + OTHER）, 1 = INTERNAL, 2 = HOT-LEAF**。temperature 在 build 時依 Level 1 的 `.hotleaf` 清單一次定死，PoC 不做執行期遷移。|
| DB 建置順序 | **two-pass build**（因 hot/cold 非結構性）：pass 1 在 passthrough 下建 DB + profile 讀取得 `.hotleaf`；pass 2 帶 temperature tag 重建（先寫最小空 skeleton 再灌數百萬列，紅線 F9）。若不啟用 hot-leaf，則 stream 2 不用、退化成 OTHER/INTERNAL/LEAF 的單趟 build。|
| page/lba size | 建議 namespace 格式化成 **4KB LBA**，使 `page_size == lba_size`，main DB 寫入天生對齊。|

## B.0.1 專案目錄結構與「自我封閉」原則（重要）

整個專案 = **單一根目錄、單一 git repo**，一切都在它底下。**不跨目錄去專案外找檔案、不把產出散到 /tmp / 家目錄 / 系統目錄。** 專案根目錄可以就是現有 research repo。Phase B0 第一件事就是確立根目錄並建立以下結構（名稱可調，精神不可變）：

```
<project-root>/              單一 git repo
├─ README.md
├─ PLAN_LEVEL2.md
├─ host/                     type_aware_vfs.c/.h、page_classify.c/.h、Makefile
├─ benchmark/                coldstart_bench、classify_pages.c、residency_checker.c、
│                            build_testdb、workloads、drop_caches.sh、run 腳本
├─ femu/                     FEMU 原始樹（clone 進這個子目錄，就地修改）
├─ scripts/                  端到端 build/run/重現腳本
├─ results/                  量測 CSV、圖
└─ docs/                     LEVEL2_FEMU_CHANGES.md 等
```
規則：外部 repo（FEMU）一律 clone 進 `femu/`；既有 benchmark 資產整理進 `benchmark/`；新建/修改檔案都在根目錄底下並 commit；FEMU build 產物用 `.gitignore` 排除，但**改過的 .c/.h 要留在樹內並 commit**。

---

## Phase B0 — Codebase 探索 → `PLAN_LEVEL2.md`

### B0.1 確立根目錄與結構
建立 §B.0.1 的目錄結構，把 Level 1 產物（`type_aware_vfs.c/.h`、`page_classify.c/.h`）整理進 `host/`，benchmark 資產整理進 `benchmark/`。

### B0.2 Host 端盤點
- 找到 Level 1 的 `type_aware_vfs.c` 與 `page_classify.c/.h`。
- ⛔ **若這些檔案不存在**（Level 1 沒落地或找不到）：**你必須先從頭實作一份完整、可編譯的 `type_aware_vfs.c`**（照 PART A 的 §A1，最小需求：shim VFS + O(1) 分類 + 只對 MAIN_DB 分類），commit 成實體檔案後再進 Level 2。**不可跳過、不可用空 stub。** 在 `PLAN_LEVEL2.md` 註明是「沿用既有」還是「從頭重新實作」。

### B0.3 FEMU 端盤點（用 grep/find，不要猜路徑）
clone FEMU 進 `femu/`，然後 grep 出（名稱可能因版本漂移，**一律以實際 grep 結果為準**）：
- **NVMe 前端**：處理 Write 的進入點（`nvme_rw` / `nvme_io_cmd`），以及 `NvmeRwCmd`、`NvmeRequest`、`NvmeCmd` 定義。
- **Blackbox FTL**：`bbssd/ftl.c`、`ftl.h`；`ssd_write`、`ssd_read`、`ftl_thread`。
- **寫入位置管理**：`struct write_pointer`、`struct line`、`struct line_mgmt`、`get_new_page`、`ssd_advance_write_pointer`、`get_next_free_line`。
- **映射表**：`maptbl` (L2P)、`rmap` (physical→logical)。
- **GC**：`do_gc`、victim line 選擇、`gc_read_page`、`gc_write_page`。
- FEMU 的 **build 流程**（可能是專屬 script，不是單純 make）、SSD 容量/參數設定位置。

### B0.4 產出 `PLAN_LEVEL2.md` 並 commit
列出：將修改的**確切**檔案 / struct / function（grep 出的真名）；FEMU SSD 容量是否足夠（> DB 大小 + 3 條 stream + GC over-provisioning）；環境（FEMU guest 內是否有 build tools）。

> ⛔ **STOP-AND-REPORT：** 任何「grep 不到對應 struct/function」或「容量明顯不足」→ 停下來說明，不要硬猜後面照做。
> **驗證關卡 B0：** PLAN_LEVEL2.md 含上述全部、每個 FEMU 名稱都有 grep 佐證。→ commit。

---

## Phase B1 — Host 端 NVMe Passthrough VFS（含對齊處理）

修改 `host/type_aware_vfs.c`，新增由 env `FEMU_PASSTHROUGH=1` 啟用的模式；**未設此 env 時維持 Level 1 行為**。所有程式跑在 FEMU guest VM 內，`/dev/nvme0n1` 是 FEMU 模擬裝置。

### B1.0 對齊的正確認知（決定對齊邏輯放哪——放錯就全錯）
- **寫入永遠對齊：** SQLite pager 對 main DB 的 xWrite 永遠是整頁、頁對齊（它不會單獨寫 100-byte header；改 header 是整個 page 1 一起寫）。只要 `page_size == lba_size`（都設 4KB），main DB 每次寫入天生 block 對齊，**不需要 RMW**。
- **對齊問題在讀取：** SQLite 開檔時會先 `xRead` 正好 100 bytes @ offset 0 去讀 header 取得 page size。O_DIRECT / passthrough 都無法做 100-byte 傳輸。**所以對齊處理做在 xRead。**
- **sub-block 寫入（4-byte rollback journal、24/32-byte WAL）只在 journal/WAL 檔**，不在 main DB → 讓那些檔走正常 VFS，**不要在 passthrough 路徑做 RMW**。

### B1.1 檔案分流
- `SQLITE_OPEN_MAIN_DB` → **passthrough**（裸裝置）。
- `SQLITE_OPEN_MAIN_JOURNAL` / `SQLITE_OPEN_TEMP_*` / `SQLITE_OPEN_TRANSIENT_DB` → **委派 parent VFS**（寫到 guest 正常 fs，buffered I/O 接受任意大小）。
- passthrough 建 DB 時把 `PRAGMA journal_mode` 設為 **OFF（或 MEMORY）**：DB 路徑是 `/dev/nvme0n1`，自動推導的 `-journal` 是無法建立的怪路徑；OFF/MEMORY 直接迴避。讀取階段唯讀本就不需 journal。

### B1.2 `xOpen`(main DB)
- `O_RDWR | O_DIRECT` 開裸裝置（路徑用 env `FEMU_NVME_DEV`，預設 `/dev/nvme0n1`）。
- 取得 `lba_size`、`nsid`、namespace 容量。建議 namespace 格式化成 4KB LBA。
- `posix_memalign` 配一塊對齊 bounce buffer（至少 1 page，對齊到 `lba_size`）。

### B1.3 裝置初始化（provisioning，別漏）
裸裝置一開始是垃圾；SQLite 看到「size≠0 但 header 不合法」會直接報 `"not a database"`。所以**建 DB 前先把一個最小空 SQLite DB image**（由 `sqlite3 empty.db "VACUUM;"` 產生，通常 1–2 頁）寫到裝置 LBA 0。之後在 passthrough 模式灌數百萬列——這數百萬次 page write 才是帶 tag、被 FEMU 分流的部分（最初 1–2 頁未 tag，歸 OTHER，可忽略）。

### B1.4 `xWrite`(main DB) — temperature-aware stream 指派
```
1. 跑 O(1) 分類（重用 page_classify 模組）得 class ∈ {INTERNAL, LEAF, OTHER}
2. 決定 stream_id：
     class == INTERNAL                         → stream_id = 1
     class == LEAF 且 該 page 在 .hotleaf 清單   → stream_id = 2  (HOT-LEAF)
     class == LEAF 且 不在 .hotleaf            → stream_id = 0  (COLD/DEFAULT)
     class == OTHER                            → stream_id = 0
   註：.hotleaf 由 pass-1 profiling 產生（見 §B.0 two-pass）。
       pass-1（還沒有 .hotleaf）時，所有 LEAF 一律 stream 0；
       未啟用 hot-leaf 時，stream 2 不使用。
3. 對齊斷言：iOfst 與 iAmt 都必須是 lba_size 整數倍
   → 若失敗：⛔ 大聲報錯停止（紅線 F7）。不要靜默 RMW。
4. memcpy page 進 bounce buffer
5. 建 struct nvme_passthru_cmd：
     opcode=0x01, nsid, addr=bounce, data_len=iAmt,
     cdw10/11=SLBA(=iOfst/lba_size), cdw12=NLB(0-based), cdw13=stream_id
6. ioctl(fd, NVME_IOCTL_IO_CMD, &cmd)；檢查回傳值與 cmd.result
```

### B1.5 `xRead`(main DB) — 真正需要對齊邏輯之處
- **若 iOfst 與 iAmt 都對齊 lba_size**（一般整頁讀取）：直接 `pread()` 進對齊 bounce buffer，再 memcpy 給 SQLite。
- **若未對齊**（典型：開檔讀 100-byte header @ offset 0）：做**對齊超集讀取**——iOfst 往下取整、iOfst+iAmt 往上取整到 lba_size 邊界，`pread()` 整段對齊範圍進 bounce buffer，再把 `[iOfst, iOfst+iAmt)` 切片 memcpy 給 SQLite。**讀取不需要 RMW（不寫回）。**
- 讀取**不帶 stream_id**（placement 在寫入時就決定）。
- 依 SQLite 慣例處理 short-read：讀超過有效範圍時尾端補零。

### B1.6 其餘方法
- `xSync`：送 NVMe Flush（opcode `0x00`，經 nvme_passthru_cmd），或寫入指令設 FUA。**不可做成 no-op。**
- `xFileSize`：回傳 namespace 容量（`ioctl BLKGETSIZE64`）。
- `xTruncate`：裸裝置上視為 no-op。
- `xLock` / `xUnlock` / `xCheckReservedLock`：本 PoC 限定**單 process 單 connection**，回 `SQLITE_OK`。**在 README 明確標註此限制。**

### B1.7 DB 建置順序（two-pass，因 temperature 非結構性）
harness 的 build-test-DB 步驟在 Level 2 必須在 `FEMU_PASSTHROUGH=1` 下執行，先 provision 空 skeleton 再灌資料，讓建 DB 期間**每次 page write 都帶 tag 進 FEMU**。啟用 hot-leaf 時：
- **pass 1**：`.hotleaf` 還不存在 → 所有 LEAF 走 stream 0，建好 DB 後在 training workload 上 profile 讀取得 `.hotleaf`（重用 Level 1 §A2.3，且遵守 F11 train/test 切分）。
- **pass 2**：帶 `.hotleaf` 重新 provision + 灌資料 → 這次 hot leaf 才會被打成 stream 2 進 FEMU 分流。
- 不啟用 hot-leaf 時退化成單趟 build（只有 stream 0/1）。

> **驗證關卡 B1：**
> 1. 普通模式（未設 env）`PRAGMA integrity_check` = ok（Level 1 行為沒壞）。
> 2. passthrough 模式能建 DB（provision + 灌資料）、能讀 DB。
> 3. 對齊斷言確實會在被違反時報錯停止（可手動構造一次驗）。
> → commit。

---

## Phase B2 — FEMU NVMe 前端攔截

修改 FEMU NVMe 前端（用 B0 grep 到的真實位置）：
- 定位 Write 指令解碼處（`NvmeRwCmd`）。
- 從 CDW13 取 `stream_id`（RW 指令 CDW13 即 `dsmgmt`；以 grep 為準）：`stream_id = rw->dsmgmt & 0xFF;`
- 在 FEMU 內部 request 結構（`NvmeRequest` 或傳給 FTL 的 wrapper）新增 `uint8_t stream_id;`，解碼時填入。
- 把 `stream_id` 一路傳到 FTL 的 `ssd_write`。
- 防呆：`stream_id` 不在 `{0,1,2}` 一律當 `0`（COLD/DEFAULT）。
- 讀取指令沒有 stream_id，正常。

> **驗證關卡 B2：** FEMU 帶此改動能編譯；加暫時性 printf 確認寫入時 FTL 端收到的 stream_id 與 host 端送的一致。→ commit。

---

## Phase B3 — FTL 多 Active-Line 配置

### B3.A 多 active line（核心隔離）
- 資料結構：FTL 目前的單一 `struct write_pointer wp` 改成陣列 `struct write_pointer wp[3]`（索引 = stream_id）。SSD init 時為每個 stream 各配一條起始 free line。
- 配置邏輯：`get_new_page()` 改成 `get_new_page(ssd, stream_id)`，用 `wp[stream_id]`。某 stream 的 line 寫滿時，`ssd_advance_write_pointer(ssd, stream_id)` 封存該 line，並從**共用 line_mgmt free pool** 為該 stream 取一條新 free line。
- 三條 stream 的語意：`wp[0]`=COLD/DEFAULT、`wp[1]`=INTERNAL、`wp[2]`=HOT-LEAF。
- `ssd_write` 把 `req->stream_id` 傳給 `get_new_page`。
- 三個 stream **共用同一個 free-line pool**，確保 `lm->free_line_cnt` 等計數正確。

### B3.B Fast tier for INTERNAL + HOT-LEAF（建議做——這是 cold-read 變快的真正槓桿）
- 給 **INTERNAL（stream 1）與 HOT-LEAF（stream 2）** 的 line 一個**較低的 NAND 讀延遲**參數（模擬 SLC 區），例如比一般 line 快 2–3 倍；COLD/DEFAULT（stream 0）維持一般延遲。
- 在 FEMU latency model（`ssdparams` / NAND read timing）裡，依該 page 所屬 line 的 stream 類別套用不同讀延遲。
- **做成可開關的 config 常數**，且**兩條 fast 線可分別開關**（要能做「只 internal fast」vs「internal+hotleaf fast」的 ablation）。
- 量測報告誠實說明：這是被建模出來的 tier，數值依 FEMU latency model 而定；HOT-LEAF 的好處還額外取決於 hot-leaf 命中率（workload-dependent）。

> **驗證關卡 B3：** FEMU 編譯通過；init 時三條 wp 各有起始 line；fast tier config（兩條線）可獨立切換。→ commit。

---

## Phase B4 — Stream-aware Garbage Collection（陷阱所在）

> 跳過這步，GC 會把隔離毀掉。注意：**GC 主要在建 DB / 寫入密集期觸發**（B-Tree 成長與 rebalance 反覆改寫 internal node）；純讀的 cold-start benchmark 本身不觸發 GC。所以驗證隔離要在「一次會觸發 GC 的 build」之後檢查。

- **持久化 tag：** 新增一個與 `rmap` 平行、以 physical page 為索引的陣列 `uint8_t *page_stream;`。每次寫入完成時記錄該實體頁的 stream_id（比改 maptbl entry 侵入性低）。
- **victim 選擇不變：** GC 仍全域挑「invalid page 最多的 line」當 victim，不分 stream。
- **隔離式 rewrite：** GC 搬移 valid page 時，用 `page_stream[old_ppa]` 查出它的 stream（0/1/2），把這次 GC 寫入導向該 stream 的 `wp[stream]`（`get_new_page(ssd, stream)`），並更新 `page_stream[new_ppa]`。
- ⛔ **絕不可把不同 stream（INTERNAL / HOT-LEAF / COLD）的 GC rewrite 混進同一條 generic line。**

> **驗證關卡 B4：** FEMU 編譯通過。→ commit（純度的真正驗證在 B5.2）。

---

## Phase B5 — 驗證與誠實量測

### B5.1 Build
確認 FEMU 帶全部修改能成功編譯（用 B0 找到的實際 build 流程）。

### B5.2 實體純度指標（機制是否成立的「主要證據」）
- 在 FEMU 加一個 debug 介面（HMP/QMP 指令，或可觸發的列印），輸出每條 line/block 組成：`Block X: Y% INTERNAL / Z% LEAF / W% OTHER`。
- 在 FEMU 加一個 debug 介面（HMP/QMP 指令，或可觸發的列印），輸出每條 line/block 組成：`Block X: a% INTERNAL / b% HOT-LEAF / c% COLD/OTHER`（依 `page_stream` 的 0/1/2 統計）。
- **機制成功的定義 =** 在一次**會觸發 GC 的 build** 之後，各 line 仍接近「單一 stream 純度」（接近 100%）。這是 cross-layer 訊號端到端打通的直接證據，**與 latency 數字無關，本身就是有效研究結果**。

### B5.3 Cold-start latency 量測（誠實）
先在 passthrough 模式建好測試 DB，用 B5.2 確認隔離成立。在 FEMU guest 內跑 Level 1 的 coldstart_bench，O_DIRECT 讀取，cold cache。

**Ablation 條件矩陣（fast tier 與 hot-leaf 拆開,才能歸因）：**
| 條件 | 隔離(3A) | INTERNAL fast | HOT-LEAF fast | software warmer |
|------|---------|---------------|---------------|-----------------|
| A baseline | 關（或單 stream 建的 DB） | — | — | 無 |
| B 純隔離 | 開 | 關 | 關 | 無 |
| C internal fast | 開 | 開 | 關 | 無 |
| C2 internal+hotleaf fast | 開 | 開 | 開 | 無 |
| D 隔離 + warmer | 開 | — | — | 開（Level 1 warmer，可含 hot-leaf）|
| E warm cache 上界 | — | — | — | — |

- 每條件至少 **20–30 次**，報告 median / p95 / p99 / stdev。
- ⛔ **誠實預期（當假設量測，不可當既定結論灌水）：**
  - **B**（純隔離、identity LBA、相依讀取、同 NAND tier）主要只有 GC 隔離的好處，TTFQ 改善可能很小、甚至落在雜訊內。
  - **C**（internal fast）應出現明顯 per-read 延遲下降（每次走到 internal node 都變快）。
  - **C2**（再加 hot-leaf fast）的額外好處**取決於 hot-leaf 命中率**；若 benchmark workload 與 profiling workload 不同（F11 要求 disjoint），命中率可能下降，**這要如實反映在數字裡，不可用同一批 query 灌高命中率**。
  - **D** 顯示隔離讓 bulk prefetch 變得高效。
- **如實報告實際數字。若 B 沒改善，那是正確且預期內的結果**——明說並解釋（隔離改變的是實體 placement，但 host 仍對 identity-mapped LBA 發出相依讀取）。**嚴禁斷言「不靠 warmer，type-aware 就把 TTFQ 降到 warmer 等級」。**
- 若 FEMU 能輸出 per-die 存取分佈 / read amplification，一併報告。

> **驗證關卡 B5：** B5.2 純度報告 + B5.3 完整 A–E（含 C2）矩陣統計 + 誠實結論（含可能的 null result 與 hot-leaf workload-dependence 說明）。→ commit。

### Level 2 驗收 checklist
- [ ] FEMU 帶修改能編譯。
- [ ] B5.2 純度：一次觸發 GC 的 build 之後，各 line 仍接近單一 stream 純度。
- [ ] host passthrough VFS：能建立並讀取 DB、`integrity_check` 過；xRead（含 100-byte header 對齊超集讀取）、xWrite（含對齊斷言）、xSync（NVMe Flush）、xFileSize 都實作；journal/temp 委派 parent。
- [ ] stream_id 全程貫穿 host → FEMU 前端 → FTL → GC（以「GC 後純度仍在」驗證）。
- [ ] Host 與 FEMU 用同一個 dword（CDW13）；host 用 `nvme_passthru_cmd` + `NVME_IOCTL_IO_CMD`。
- [ ] Ablation 矩陣 A–E（含 C2）完成，統計嚴謹，結果誠實（含 null result 與 hot-leaf workload-dependence）。
- [ ] 每個 Phase 都有 commit；`PLAN_LEVEL2.md`、README / 結果文件更新。
- [ ] 所有 .c/.h 實體存在於 repo、已 commit、可直接編譯；若 `type_aware_vfs.c` 原本不存在，已附從頭實作的完整版（非 stub）。

### Level 2 交付物
- `host/type_aware_vfs.c` (+header)：含 passthrough 模式。
- `host/page_classify.c` / `.h`：O(1) 分類共享模組。
- FEMU 端實際被改的 .c/.h（NVMe 前端、`bbssd/ftl.c` 等）留在 `femu/` 樹內並 commit；另附 `docs/LEVEL2_FEMU_CHANGES.md` 摘要改了哪些檔案與函式。
- benchmark/工具的 .c/.py、build/執行腳本、`results/` 量測 CSV/圖。
- `PLAN_LEVEL2.md`；更新的 README（架構、如何重現、誠實結果、§0.1 最小範圍限制）。

---
---

# 附錄 A — O(1) 分類器 byte signature 速查（Level 1 + Level 2 共用，唯一真相）

| 要檢查的 byte | 來源 | 值 | 分類 |
|---------------|------|-----|------|
| `buf[100]`（若 is_page1）/ 否則 `buf[0]` | b-tree page header flag | `0x05` interior table | INTERNAL |
| 同上 | 同上 | `0x02` interior index | INTERNAL |
| 同上 | 同上 | `0x0D` leaf table | LEAF |
| 同上 | 同上 | `0x0A` leaf index | LEAF |
| 同上 | 同上 | 其餘 | OTHER |

- page size：db header **offset 16**，big-endian 2-byte；值為 `1` 代表 65536。
- file change counter：db header **offset 24**，big-endian 4-byte（sidecar 過期偵測用）。
- **stream_id 對映（Level 2，temperature-aware）：**
  - `0` = COLD/DEFAULT = (LEAF 且不在 hotleaf) 或 OTHER
  - `1` = INTERNAL
  - `2` = HOT-LEAF = (LEAF 且在 `.hotleaf` 清單)
  - hot/cold 非結構性，需 Level 1 profiling 產出的 `.hotleaf`；未啟用時 stream 2 不用。

# 附錄 B — NVMe passthrough Write 指令欄位（Level 2 唯一真相）

| 欄位 | 值 |
|------|-----|
| 機制 | `struct nvme_passthru_cmd` + `ioctl(fd, NVME_IOCTL_IO_CMD, &cmd)` |
| opcode (Write) | `0x01` |
| opcode (Flush) | `0x00` |
| cdw10/11 | SLBA = `iOfst / lba_size` |
| cdw12 | NLB（**0-based**）|
| cdw13 | **stream_id**（host 端）→ FEMU 端讀 `NvmeRwCmd` 的 `dsmgmt & 0xFF` |
| addr / data_len | bounce buffer / iAmt |

> 禁用 `struct nvme_user_io`（無 cdw10–15）。

# 附錄 C — STOP-AND-REPORT 停點總表

1. Phase A0 / B0 任一「實測 API」結果與本文檔不符 → 停、說明落差。
2. B0 FEMU grep 不到對應 struct/function，或 SSD 容量不足 → 停、說明。
3. B1 對齊斷言被觸發 → 停、報告，當成發現去調查，不要 RMW 粉飾。
4. 任何量測出現需要解釋的異常（例如 warm cache 沒被清掉、純度遠低於 100%）→ 停、說明。
5. 任何「該重用的既有資產」找不到 → 停、列出實際 repo 內容，不要重造輪子前先確認。

# 附錄 D — 一眼看完的「絕對不要做」清單

- 不要 VFS 自開 fd 指向 DB 檔（F1）。
- 不要 VFS 走 freelist 分類（F2）。
- 不要挖 parent unixFile 內部 fd（F3）。
- 不要 warmer/VFS 自建 cache buffer（F4）。
- 不要量到 warm cache；沒 root 不能 drop cache 就中止（F5）。
- 不要 sidecar 過期卻照用；用 file change counter 偵測，不符就 best-effort/跳過、不重建（F6）。
- 不要在 passthrough 寫入路徑做靜默 RMW；不對齊就報錯停（F7）。
- 不要用 `nvme_user_io`（F8）。
- 不要把完整 DB `dd` 進裸裝置（F9）。
- 不要灌水/美化數據；null result 是有效結果（F10）。
- 不要用同一批 query 同時做 hot-leaf profiling 與 benchmark；train/test 必須切分（F11）。
- 不要相信本文檔宣稱的任何 API——Phase 0 一律實測。
- 註：page→class 活表、hotset/hotleaf sidecar 是 metadata，不違反 F4（F4 只禁快取頁面內容）。

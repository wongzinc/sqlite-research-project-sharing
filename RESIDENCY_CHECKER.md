# Residency Checker

`residency_checker` 用來檢查 SQLite database 檔案中，每一個 SQLite page 目前是否 resident，也就是該 page 對應到的檔案內容是否已經在作業系統的 memory/page cache 中。

這支程序的重點是觀察「當下」的 residency 狀態，因此它刻意避免讀取 SQLite database header，避免檢查工具本身把 header page 載入 memory，污染量測結果。

## 使用方式

```bash
./residency_checker <database.db> <output.csv>
```

如果沒有提供 SQLite page size，預設使用 `4096` bytes。

也可以明確指定 SQLite page size：

```bash
./residency_checker <database.db> <sqlite-page-size> <output.csv>
```

例如：

```bash
./residency_checker test.db residency.csv
./residency_checker test.db 8192 residency.csv
```

## 輸出格式

輸出是一個 CSV 檔案：

```csv
page_number,is_resident
1,1
2,0
3,1
```

欄位意義：

- `page_number`: SQLite page number，從 `1` 開始。
- `is_resident`: `1` 表示該 SQLite page resident，`0` 表示不 resident。

## 量測邏輯

程序會先取得 OS page size：

```c
sysconf(_SC_PAGESIZE)
```

接著用唯讀方式開啟 database 檔案，取得檔案大小，然後使用：

```c
mmap(..., PROT_READ, MAP_PRIVATE, ...)
```

將整個 database 檔案映射到記憶體位址空間。

注意：`mmap()` 建立的是 mapping，不代表整個檔案內容已經被讀入 memory。

之後程序配置一個 `mincore()` vector，每一個 OS page 對應一個 byte，然後呼叫：

```c
mincore(mapping, file_size, vec)
```

`mincore()` 會回報每個 OS page 是否 resident。程式使用 `vec[i] & 1` 判斷該 OS page 是否 resident。

## SQLite Page 到 OS Page 的換算

SQLite page size 可能和 OS page size 不同，所以程序會把每個 SQLite page 的檔案 offset 區間換算成它涵蓋的 OS pages。

對第 `N` 個 SQLite page：

```c
sqlite_begin = (N - 1) * sqlite_page_size;
sqlite_end = sqlite_begin + sqlite_page_size;
first_os_page = sqlite_begin / os_page_size;
last_os_page = (sqlite_end - 1) / os_page_size;
```

判定規則是：

> 一個 SQLite page 涵蓋到的所有 OS pages 都 resident，該 SQLite page 才算 resident。

也就是說，只要其中任何一個 OS page 不 resident，該 SQLite page 就會輸出 `0`。

## Page Size 行為

`residency_checker` 不會從 SQLite header 讀 page size。

原因是 SQLite page size 存在 database header 的 offset 16-17。如果 checker 自己讀取 header，就可能觸發 page fault，讓 database 開頭的 OS page 變成 resident。這會讓輸出結果受到 checker 本身影響。

因此目前行為是：

- 未指定 SQLite page size 時，預設 `4096`。
- 有指定時，使用外部傳入的值。
- 傳入值必須是合法 SQLite page size：
  - 最小 `512`
  - 最大 `65536`
  - 必須是 2 的次方

如果實際 database page size 不是 `4096`，建議明確傳入正確值。

## 不做的事情

這支程序刻意不做以下事情：

- 不檢查 SQLite header magic。
- 不從 SQLite header 讀 page size。
- 不解析 SQLite B-tree。
- 不判斷 page type。
- 不主動 drop cache。
- 不保證 database 是有效 SQLite database。

它只根據檔案大小、SQLite page size、OS page size，以及 `mincore()` 回傳結果產生 residency CSV。

## 可能影響結果的因素

以下狀況都可能讓某些 pages 在執行 checker 前就已經 resident：

- database 剛被 SQLite 或其他程序讀過。
- 先前跑過 benchmark、classifier、plot/join 流程。
- 系統 page cache 尚未清掉。
- OS 或其他背景程序讀取過該檔案。
- kernel readahead 已經載入附近 pages。

`residency_checker` 只觀察執行當下的 residency 狀態，不負責建立 cold-cache 條件。

## 平台假設

這支程序假定在 Linux/POSIX-like 環境執行，並需要：

- `mmap()`
- `mincore()`
- `sysconf(_SC_PAGESIZE)`

目前程式沒有保留非 POSIX fallback。

## 成功時的 stderr 摘要

成功產生 CSV 後，程序會在 stderr 印出摘要，例如：

```text
db=test.db file_size=104857600 sqlite_page_size=4096 sqlite_pages=25600 os_page_size=4096 os_pages=25600 output=residency.csv
```

這行可用來確認本次使用的 SQLite page size、OS page size，以及產生的 page 數。

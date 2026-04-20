import { useState } from "react";

const weeks = [
  {
    week: 1,
    phase: "基礎建設",
    title: "環境搭建 & SQLite 編譯",
    color: "#2563eb",
    tasks: [
      {
        name: "編譯 SQLite from source",
        details: [
          "從 sqlite.org/download.html 下載 amalgamation（sqlite3.c + sqlite3.h + shell.c）",
          "用 gcc -O2 -o sqlite3 shell.c sqlite3.c -lpthread -ldl 編譯",
          "確認能執行 ./sqlite3 --version",
          "另外 clone 完整 source tree（https://sqlite.org/src）以便後續查 code"
        ]
      },
      {
        name: "建立測試用 database",
        details: [
          "寫一個 Python 或 C script 建立 ~100MB 的 DB",
          "Schema: CREATE TABLE t(id INTEGER PRIMARY KEY, payload BLOB, tag TEXT); CREATE INDEX idx_tag ON t(tag);",
          "payload 用 100 bytes random data，tag 用隨機字串（建 index 用）",
          "插入約 50 萬筆資料",
          "記錄最終檔案大小、page count（PRAGMA page_count）、page size（PRAGMA page_size）"
        ]
      },
      {
        name: "閱讀 SQLite file format spec",
        details: [
          "精讀官方文件 https://www.sqlite.org/fileformat2.html",
          "重點理解：database header 的前 100 bytes、B-tree page header 結構",
          "記住 page type flag 的位置：page 1 在 offset 100，其餘在 offset 0",
          "四種 page type flag：0x02(index interior), 0x05(table interior), 0x0A(index leaf), 0x0D(table leaf)",
          "Leaf flag 特徵：bit 3 被設定（flag & 0x08 != 0）"
        ]
      }
    ]
  },
  {
    week: 2,
    phase: "基礎建設",
    title: "Page Classifier 開發",
    color: "#2563eb",
    tasks: [
      {
        name: "寫 Page Classifier（建議用 C）",
        details: [
          "開啟 database file（用 open() + read()，不需要 link SQLite library）",
          "讀取 header 取得 page_size（offset 16-17, big-endian 2 bytes）",
          "讀取 page_count（offset 28-31, big-endian 4 bytes）",
          "迴圈讀取每個 page 的第一個 byte（page 1 的 flag 在 offset 100）",
          "分類為 interior / leaf / freelist / overflow",
          "注意排除 freelist page（trunk page 和 leaf page）和 overflow page"
        ]
      },
      {
        name: "輸出分析結果",
        details: [
          "輸出格式：page_number, page_type, file_offset",
          "統計 interior page 數量與佔比",
          "用 Python matplotlib 或 gnuplot 畫出 page type 在檔案中的空間分佈圖",
          "X 軸是 page number，Y 軸用顏色區分 interior vs leaf",
          "觀察 interior page 是集中還是分散？"
        ]
      }
    ]
  },
  {
    week: 3,
    phase: "基礎建設",
    title: "mmap 與 madvise 基礎",
    color: "#2563eb",
    tasks: [
      {
        name: "閱讀 madvise / process_madvise man pages",
        details: [
          "man 2 madvise：理解 MADV_COLD、MADV_WILLNEED、MADV_PAGEOUT 的語義差異",
          "man 2 process_madvise：理解如何對其他 process 的記憶體做 advise",
          "重點筆記：MADV_COLD 把 page 移到 inactive LRU list，MADV_WILLNEED 觸發 readahead"
        ]
      },
      {
        name: "閱讀 SQLite mmap 官方文件",
        details: [
          "精讀 https://www.sqlite.org/mmap.html",
          "理解 PRAGMA mmap_size 的運作方式",
          "理解 xFetch 在 mmap 模式下的行為",
          "理解 mmap 與 page cache 的互動關係"
        ]
      },
      {
        name: "寫一個簡單的 mmap 實驗",
        details: [
          "用 C 寫：mmap 開啟你的測試 DB，呼叫 madvise(MADV_COLD)，再用 mincore() 檢查 residency",
          "確認你能成功操作這三個 syscall",
          "這是後續所有實驗的基礎，務必跑通"
        ]
      }
    ]
  },
  {
    week: 4,
    phase: "層次一：觀察與量測",
    title: "Residency Checker 開發",
    color: "#059669",
    tasks: [
      {
        name: "開發 Residency Checker",
        details: [
          "用 C 撰寫：mmap 整個 database file",
          "呼叫 mincore() 取得每個 page 的 resident/non-resident 狀態",
          "mincore() 回傳的 vec 每個 byte 對應一個 page frame（4KB）",
          "注意：SQLite page size 可能不等於 OS page size，需要做對應轉換",
          "輸出格式：page_number, is_resident (0/1)"
        ]
      },
      {
        name: "合併 Page Classifier 輸出",
        details: [
          "把 page classifier 和 residency checker 的輸出 join 起來",
          "產生：page_number, page_type, is_resident",
          "畫圖：哪些 page 是 resident、哪些不是，用顏色同時標示 type",
          "觀察冷啟動前後的 residency 差異"
        ]
      }
    ]
  },
  {
    week: 5,
    phase: "層次一：觀察與量測",
    title: "冷啟動模擬 & Benchmark Harness",
    color: "#059669",
    tasks: [
      {
        name: "開發 Cold-Start Simulator",
        details: [
          "用 madvise(MADV_COLD) 或搭配 cgroup memory pressure 來模擬冷啟動",
          "方法一（簡單）：對整個 mmap region 呼叫 madvise(MADV_COLD)",
          "方法二（更真實）：用 cgroup v2 的 memory.max 限制記憶體，迫使 kernel 淘汰頁面",
          "先用方法一開始，確認 mincore() 顯示頁面被淘汰"
        ]
      },
      {
        name: "開發 Benchmark Harness",
        details: [
          "用 C 撰寫，需要 link SQLite library（-lsqlite3 或直接編譯 sqlite3.c）",
          "開啟 DB 時設定 PRAGMA mmap_size = <file_size>",
          "跑 100 次 random point query：SELECT * FROM t WHERE id = ?",
          "用 clock_gettime(CLOCK_MONOTONIC) 記錄每次查詢的 wall-clock latency",
          "同時用 perf stat -e page-faults 觀察 page fault 數量"
        ]
      }
    ]
  },
  {
    week: 6,
    phase: "層次一：觀察與量測",
    title: "冷啟動 Baseline 量測",
    color: "#059669",
    tasks: [
      {
        name: "完整的冷啟動量測實驗",
        details: [
          "流程：(1) 開 DB → (2) MADV_COLD → (3) 跑 100 次 random query → (4) 記錄每次 latency",
          "畫出 latency 分佈圖：X 軸是第幾次查詢，Y 軸是 latency",
          "觀察：第一次查詢 vs 後續查詢的 latency 差異有多大？",
          "用 perf stat -e page-faults 記錄總 page fault 數量",
          "重複實驗 5-10 次取平均，確認結果穩定"
        ]
      },
      {
        name: "分析瓶頸",
        details: [
          "瓶頸是 fault 數量還是每次 fault 的延遲？",
          "用 perf record -e page-faults 搭配 perf report 看 fault 發生在哪些 address",
          "對照 page classifier 的輸出，判斷 fault 集中在 interior page 還是 leaf page",
          "記錄所有數據，寫入 research log"
        ]
      }
    ]
  },
  {
    week: 7,
    phase: "層次一：觀察與量測",
    title: "論文閱讀 & VACUUM 分析",
    color: "#059669",
    tasks: [
      {
        name: "精讀 Crotty et al. (CIDR 2022) Section 3 & 4",
        details: [
          "論文：\"Are You Sure You Want to Use MMAP in Your Database Management System?\"",
          "重點理解 mmap 的三個主要問題：page table contention、single-threaded eviction、TLB shootdown",
          "思考：這些問題在 embedded/mobile SQLite 場景下是否同樣嚴重？",
          "筆記你的分析，這會是你報告中 Related Work 的重要內容"
        ]
      },
      {
        name: "VACUUM 前後分析",
        details: [
          "對測試 DB 執行 VACUUM",
          "重新跑 page classifier，比較 VACUUM 前後 interior page 的空間分佈",
          "VACUUM 是否改善了 interior page 的聚集程度？",
          "畫 VACUUM 前後的對比圖"
        ]
      }
    ]
  },
  {
    week: 8,
    phase: "中期整理",
    title: "數據整理 & 層次一總結",
    color: "#d97706",
    tasks: [
      {
        name: "整理所有層次一的實驗數據",
        details: [
          "整理所有圖表：page type 分佈圖、residency 圖、latency 分佈圖、VACUUM 前後比較",
          "寫一份「層次一實驗報告」，回答：現狀到底長什麼樣？",
          "關鍵數字：interior page 佔比、冷啟動 fault 數量、第一次查詢 latency、VACUUM 效果"
        ]
      },
      {
        name: "精讀 Leis et al. (SIGMOD 2023) vmcache",
        details: [
          "論文：\"Virtual-Memory Assisted Buffer Management (vmcache)\"",
          "理解用 virtual memory 做 page-to-address translation 同時保留 eviction 控制的思路",
          "思考：這個概念能否啟發 SQLite 的 mmap 改進？",
          "整理筆記"
        ]
      },
      {
        name: "更新 project tracking sheet",
        details: [
          "同步進度到 tracking sheet",
          "整理已讀文獻列表",
          "規劃層次二的詳細步驟"
        ]
      }
    ]
  },
  {
    week: 9,
    phase: "層次二：介入與比較",
    title: "Prefetch 策略實作（一）",
    color: "#7c3aed",
    tasks: [
      {
        name: "實作基礎 prefetch：整段連續 madvise",
        details: [
          "找出所有 interior page 的 file offset（用 page classifier 的輸出）",
          "排序這些 offset，找出連續的 byte range",
          "對這些 range 呼叫 madvise(MADV_WILLNEED)",
          "量測：syscall 數量、完成時間",
          "跑冷啟動 benchmark，記錄 latency 改善"
        ]
      },
      {
        name: "實作逐頁 prefetch：個別 madvise",
        details: [
          "對每個 interior page 的 4KB range 個別呼叫 madvise(MADV_WILLNEED)",
          "量測：syscall 數量（會很多）、完成時間",
          "跑同樣的冷啟動 benchmark",
          "對比兩種策略的 latency 差異和 syscall overhead"
        ]
      }
    ]
  },
  {
    week: 10,
    phase: "層次二：介入與比較",
    title: "Prefetch 策略實作（二）",
    color: "#7c3aed",
    tasks: [
      {
        name: "實作分層 prefetch",
        details: [
          "思考：是否需要 prefetch 所有 interior page？",
          "嘗試只 prefetch root page + 前幾層 interior page",
          "B+tree 深度 D 大約 3-4，試試只 prefetch 前 1 層、前 2 層、全部",
          "畫出 cost-benefit 曲線：X 軸是 prefetch 的頁數，Y 軸是 latency 改善"
        ]
      },
      {
        name: "找出 sweet spot",
        details: [
          "分析：prefetch 多少 interior page 效益最高？",
          "考慮因素：prefetch 太多浪費 I/O、太少沒效果",
          "記錄最佳策略的參數",
          "把所有實驗結果整理成表格"
        ]
      }
    ]
  },
  {
    week: 11,
    phase: "層次二：介入與比較",
    title: "VACUUM & File Layout 介入",
    color: "#7c3aed",
    tasks: [
      {
        name: "VACUUM 前後的 prefetch 效果比較",
        details: [
          "在 VACUUM 前的 DB 上跑最佳 prefetch 策略，記錄 latency",
          "執行 VACUUM",
          "在 VACUUM 後的 DB 上跑同樣策略，記錄 latency",
          "比較：VACUUM 是否改善了 interior page 的空間聚集程度？",
          "VACUUM 後是否只需更少的 madvise 呼叫？"
        ]
      },
      {
        name: "探索 SQLite source code 中的 VACUUM 實作",
        details: [
          "讀 src/vacuum.c 中的 sqlite3RunVacuum()",
          "理解重建流程中 page 是如何被分配的",
          "觀察：VACUUM 是否有考慮 page type 的排列？（答案很可能是沒有）",
          "這是你提出改進方案的理論基礎"
        ]
      }
    ]
  },
  {
    week: 12,
    phase: "層次二：介入與比較",
    title: "Multi-Process 場景實驗",
    color: "#7c3aed",
    tasks: [
      {
        name: "Multi-process mmap 實驗",
        details: [
          "開多個 process 用 MAP_SHARED 存取同一個 database file",
          "用 mincore() 觀察 residency 是否跨 process 共享",
          "比較：跟每個 process 用 PRAGMA cache_size 開獨立 buffer pool 的差異",
          "量測總 RSS（Resident Set Size）差異"
        ]
      },
      {
        name: "閱讀 Linux kernel madvise.c",
        details: [
          "讀 https://github.com/torvalds/linux/blob/master/mm/madvise.c",
          "理解 MADV_COLD 和 MADV_WILLNEED 在 kernel 層的實際行為",
          "MADV_COLD：把 page 移到 inactive LRU list",
          "MADV_WILLNEED：觸發 readahead",
          "筆記關鍵 code path"
        ]
      }
    ]
  },
  {
    week: 13,
    phase: "層次三：持續性觀察",
    title: "寫入負載下的佈局變化",
    color: "#dc2626",
    tasks: [
      {
        name: "寫入負載實驗",
        details: [
          "在已分析過佈局的 DB 上持續做 INSERT 和 DELETE",
          "每隔一段時間（例如每 1000 次操作）重新跑 page type 分佈分析",
          "觀察：Interior page 的分佈如何隨寫入量改變？",
          "新產生的 interior page 會被分配到哪裡？"
        ]
      },
      {
        name: "長時間運行觀察",
        details: [
          "跑一個模擬 App 使用情境的 workload（讀寫混合）",
          "每隔固定時間做一次完整的 page type + residency snapshot",
          "畫出隨時間變化的 interior page 聚集程度趨勢圖",
          "這些數據說明：佈局最佳化的效果能持續多久？"
        ]
      }
    ]
  },
  {
    week: 14,
    phase: "收尾",
    title: "實驗補充 & 數據完善",
    color: "#64748b",
    tasks: [
      {
        name: "補跑缺失的實驗",
        details: [
          "檢查所有層次的實驗是否都有足夠的數據點",
          "重複跑不穩定的實驗，增加 sample size",
          "確認所有實驗的環境參數都有記錄（CPU、memory、kernel version、SQLite version）"
        ]
      },
      {
        name: "製作所有最終圖表",
        details: [
          "用 matplotlib / gnuplot 製作 publication quality 的圖表",
          "每張圖都要有清楚的 title、axis label、legend",
          "關鍵圖表：page 分佈圖、latency CDF、prefetch 策略比較、VACUUM 效果、寫入後佈局變化"
        ]
      }
    ]
  },
  {
    week: 15,
    phase: "收尾",
    title: "報告撰寫",
    color: "#64748b",
    tasks: [
      {
        name: "撰寫完整報告",
        details: [
          "結構：Background → Problem Statement → Methodology → 三個層次的實驗結果 → Discussion → Conclusion",
          "Background 部分整合你讀的論文和 SQLite 文件",
          "每個實驗都要有：目的、方法、結果、分析",
          "Discussion：你的發現對 SQLite / embedded DB 的意義是什麼？可能的改進方向？"
        ]
      },
      {
        name: "整理程式碼",
        details: [
          "把所有工具（page classifier、residency checker、benchmark harness、cold-start simulator）整理到一個 repo",
          "每個工具加上 README 說明用法",
          "加上 Makefile 方便一鍵編譯"
        ]
      }
    ]
  },
  {
    week: 16,
    phase: "收尾",
    title: "簡報準備 & 最終提交",
    color: "#64748b",
    tasks: [
      {
        name: "準備口頭報告簡報",
        details: [
          "簡報結構：問題是什麼 → 為什麼重要 → 怎麼做的 → 發現了什麼 → 未來可以怎麼做",
          "每張 slide 一個重點，搭配圖表",
          "準備 demo：現場跑 page classifier 或展示冷啟動 latency 差異",
          "練習口頭報告 2-3 次，控制在時間限制內"
        ]
      },
      {
        name: "最終提交",
        details: [
          "最終檢查報告格式、圖表、參考文獻",
          "確認程式碼 repo 乾淨可用",
          "提交報告 + 程式碼 + 簡報",
          "更新 project tracking sheet 的最終狀態"
        ]
      }
    ]
  }
];

const phases = [
  { name: "基礎建設", weeks: "1-3", color: "#2563eb", icon: "🔧" },
  { name: "層次一：觀察與量測", weeks: "4-7", color: "#059669", icon: "🔬" },
  { name: "中期整理", weeks: "8", color: "#d97706", icon: "📊" },
  { name: "層次二：介入與比較", weeks: "9-12", color: "#7c3aed", icon: "⚗️" },
  { name: "層次三：持續性觀察", weeks: "13", color: "#dc2626", icon: "📈" },
  { name: "收尾", weeks: "14-16", color: "#64748b", icon: "📝" },
];

export default function WeeklyPlan() {
  const [selectedWeek, setSelectedWeek] = useState(0);
  const [expandedTask, setExpandedTask] = useState(null);

  const current = weeks[selectedWeek];

  return (
    <div style={{
      fontFamily: "'Noto Sans TC', 'Helvetica Neue', sans-serif",
      background: "#0f172a",
      color: "#e2e8f0",
      minHeight: "100vh",
      padding: "24px 16px",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
      
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{
            fontSize: 22,
            fontWeight: 700,
            color: "#f8fafc",
            margin: 0,
            letterSpacing: "-0.5px",
          }}>
            SQLite 冷啟動檔案佈局最佳化
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 14, margin: "6px 0 0" }}>
            16 週學習與實驗計畫
          </p>
        </div>

        {/* Phase overview */}
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          marginBottom: 24,
        }}>
          {phases.map((p, i) => (
            <div key={i} style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "rgba(255,255,255,0.05)",
              borderRadius: 6,
              padding: "5px 10px",
              fontSize: 12,
              color: p.color,
              border: `1px solid ${p.color}33`,
            }}>
              <span>{p.icon}</span>
              <span style={{ fontWeight: 500 }}>{p.name}</span>
              <span style={{ color: "#64748b", fontSize: 11 }}>W{p.weeks}</span>
            </div>
          ))}
        </div>

        {/* Week selector - timeline */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(16, 1fr)",
          gap: 3,
          marginBottom: 24,
        }}>
          {weeks.map((w, i) => (
            <button
              key={i}
              onClick={() => { setSelectedWeek(i); setExpandedTask(null); }}
              style={{
                background: i === selectedWeek ? w.color : `${w.color}22`,
                border: i === selectedWeek ? `2px solid ${w.color}` : "2px solid transparent",
                borderRadius: 6,
                padding: "8px 0",
                cursor: "pointer",
                color: i === selectedWeek ? "#fff" : "#94a3b8",
                fontSize: 11,
                fontWeight: i === selectedWeek ? 700 : 500,
                fontFamily: "'JetBrains Mono', monospace",
                transition: "all 0.15s ease",
              }}
            >
              {w.week}
            </button>
          ))}
        </div>

        {/* Selected week detail */}
        <div style={{
          background: "rgba(255,255,255,0.03)",
          border: `1px solid ${current.color}44`,
          borderRadius: 12,
          overflow: "hidden",
        }}>
          {/* Week header */}
          <div style={{
            background: `${current.color}15`,
            borderBottom: `1px solid ${current.color}33`,
            padding: "16px 20px",
          }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}>
              <span style={{
                background: current.color,
                color: "#fff",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                fontWeight: 700,
                padding: "3px 8px",
                borderRadius: 4,
              }}>
                W{current.week}
              </span>
              <span style={{
                color: current.color,
                fontSize: 11,
                fontWeight: 500,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
              }}>
                {current.phase}
              </span>
            </div>
            <h2 style={{
              fontSize: 20,
              fontWeight: 700,
              color: "#f1f5f9",
              margin: "10px 0 0",
            }}>
              {current.title}
            </h2>
          </div>

          {/* Tasks */}
          <div style={{ padding: "8px 0" }}>
            {current.tasks.map((task, ti) => {
              const isExpanded = expandedTask === ti;
              return (
                <div key={ti}>
                  <button
                    onClick={() => setExpandedTask(isExpanded ? null : ti)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      width: "100%",
                      textAlign: "left",
                      background: isExpanded ? "rgba(255,255,255,0.04)" : "transparent",
                      border: "none",
                      padding: "14px 20px",
                      cursor: "pointer",
                      color: "#e2e8f0",
                      fontSize: 15,
                      fontWeight: 600,
                      fontFamily: "'Noto Sans TC', sans-serif",
                      transition: "background 0.15s",
                    }}
                  >
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: `${current.color}33`,
                      color: current.color,
                      fontSize: 12,
                      fontWeight: 700,
                      fontFamily: "'JetBrains Mono', monospace",
                      flexShrink: 0,
                    }}>
                      {ti + 1}
                    </span>
                    <span style={{ flex: 1 }}>{task.name}</span>
                    <span style={{
                      color: "#64748b",
                      fontSize: 18,
                      transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                      transition: "transform 0.2s",
                    }}>›</span>
                  </button>

                  {isExpanded && (
                    <div style={{
                      padding: "0 20px 16px 54px",
                    }}>
                      {task.details.map((d, di) => (
                        <div key={di} style={{
                          display: "flex",
                          gap: 10,
                          marginBottom: 8,
                          fontSize: 13,
                          lineHeight: 1.7,
                          color: "#cbd5e1",
                        }}>
                          <span style={{
                            color: `${current.color}aa`,
                            flexShrink: 0,
                            marginTop: 2,
                            fontSize: 8,
                          }}>●</span>
                          <span style={{
                            fontFamily: d.match(/^[a-zA-Z#\-]/) && d.includes('(') 
                              ? "'JetBrains Mono', monospace" 
                              : "'Noto Sans TC', sans-serif",
                          }}>
                            {d.split(/(`[^`]+`|[A-Z_]{2,}(?:\([^)]*\))?|\b(?:sqlite3|madvise|mincore|mmap|munmap|perf|gcc|clock_gettime|PRAGMA|SELECT|CREATE|INSERT|DELETE|VACUUM|MAP_SHARED)\b(?:\([^)]*\))?)/).map((part, pi) => {
                              if (/^`[^`]+`$/.test(part)) {
                                return <code key={pi} style={{
                                  background: "rgba(255,255,255,0.08)",
                                  padding: "1px 5px",
                                  borderRadius: 3,
                                  fontSize: 12,
                                  fontFamily: "'JetBrains Mono', monospace",
                                  color: "#93c5fd",
                                }}>{part.slice(1, -1)}</code>;
                              }
                              if (/^[A-Z_]{3,}/.test(part) || /^(?:sqlite3|madvise|mincore|mmap|perf|gcc|clock_gettime|PRAGMA|SELECT|CREATE|INSERT|DELETE|VACUUM|MAP_SHARED)/.test(part)) {
                                return <code key={pi} style={{
                                  background: "rgba(255,255,255,0.06)",
                                  padding: "1px 4px",
                                  borderRadius: 3,
                                  fontSize: 12,
                                  fontFamily: "'JetBrains Mono', monospace",
                                  color: "#a5b4fc",
                                }}>{part}</code>;
                              }
                              return <span key={pi}>{part}</span>;
                            })}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Navigation */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 16,
          gap: 8,
        }}>
          <button
            onClick={() => { setSelectedWeek(Math.max(0, selectedWeek - 1)); setExpandedTask(null); }}
            disabled={selectedWeek === 0}
            style={{
              flex: 1,
              padding: "10px",
              background: selectedWeek === 0 ? "rgba(255,255,255,0.02)" : "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: selectedWeek === 0 ? "#475569" : "#94a3b8",
              cursor: selectedWeek === 0 ? "default" : "pointer",
              fontSize: 13,
              fontFamily: "'Noto Sans TC', sans-serif",
            }}
          >
            ← 上一週
          </button>
          <button
            onClick={() => { setSelectedWeek(Math.min(15, selectedWeek + 1)); setExpandedTask(null); }}
            disabled={selectedWeek === 15}
            style={{
              flex: 1,
              padding: "10px",
              background: selectedWeek === 15 ? "rgba(255,255,255,0.02)" : "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: selectedWeek === 15 ? "#475569" : "#94a3b8",
              cursor: selectedWeek === 15 ? "default" : "pointer",
              fontSize: 13,
              fontFamily: "'Noto Sans TC', sans-serif",
            }}
          >
            下一週 →
          </button>
        </div>
      </div>
    </div>
  );
}

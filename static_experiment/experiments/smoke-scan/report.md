# 實驗報告：smoke-scan

## 實驗摘要

| 項目 | 值 |
| --- | --- |
| Experiment ID | smoke-scan |
| Prefetch backends | madvise → pread |
| Enabled layouts | original |
| Workload types | scan_zipf_full |
| Training file count | 5 |
| Measurement file count | 5 |
| Measurement repetitions | 1 |
| Memory conditions | unlimited (unlimited) |
| SQLite page size | original=4096 |
| Completed | 45 |
| Failed | 0 |
| Timeout | 0 |
| Invalid | 0 |

## 執行環境

| 項目 | 值 |
| --- | --- |
| Linux kernel | 6.17.0-19-generic |
| Hostname | meow1 |
| CPU model | AMD Ryzen 9 9950X 16-Core Processor |
| Logical CPU count | 32 |
| Total RAM | 59.21 GiB |
| Filesystem type | xfs |
| Storage devices | sda (3.6T, WUS721204BLE6L4 ), nvme2n1 (1.9T, KINGSTON SKC3000D2048G), nvme0n1 (1.9T, KINGSTON SKC3000D2048G), nvme1n1 (1.9T, KINGSTON SKC3000D2048G) |
| SQLite version | 3.46.1 |

## 各 workload type 結果

### scan_zipf_full

#### Memory condition：unlimited

##### Layout 比較

| Layout | First-query median | First-query P25–P75 | First-query P99 | 改善 vs original | Average-query median | Average-query改善 vs original |
| --- | --- | --- | --- | --- | --- | --- |
| original | 430.55 µs | 428.81 µs–433.35 µs | 443.82 µs | 0.00% | 49.26 µs | 0.00% |

##### original / unlimited / madvise：Strategy 比較

`Effective first-query latency = prefetch elapsed + first-query latency`；其改善率使用相同measurement file與repetition的baseline first-query latency配對計算。

| Strategy key | Prefetch median | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio | Major faults | Minor faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 430.55 µs | 0.00% | 430.55 µs | 0.00% | 49.26 µs | 0.00% | — | — | 264.00 | 107.00 |
| range_interior | 118.00 µs | 251.54 µs | 29.08% | 377.01 µs | -0.12% | 43.59 µs | -2.01% | 1.0000 | 1.0000 | 234.00 | 151.00 |
| offset_topk_interior_n5 | 7.00 µs | 402.92 µs | -26.80% | 408.92 µs | -28.66% | 51.23 µs | -41.58% | 1.0000 | 1.0000 | 264.00 | 110.00 |
| residency_topk_interior5_leaf0_i5_l0 | 5.00 µs | 378.22 µs | -22.08% | 383.22 µs | -23.34% | 47.96 µs | -13.49% | 1.0000 | 1.0000 | 264.00 | 109.00 |
| residency_topk_interior5_leaf5_i5_l5 | 7.00 µs | 387.46 µs | 15.11% | 394.46 µs | 13.57% | 50.42 µs | -13.64% | 1.0000 | 1.0000 | 264.00 | 109.00 |

Distribution 詳細：

| Strategy key | Metric | P25 | Median | P75 | P99 |
| --- | --- | --- | --- | --- | --- |
| baseline | first_query_latency_us | 428.81 µs | 430.55 µs | 433.35 µs | 443.82 µs |
| baseline | effective_first_query_latency_us | 428.81 µs | 430.55 µs | 433.35 µs | 443.82 µs |
| baseline | average_latency_us | 46.57 µs | 49.26 µs | 50.69 µs | 72.20 µs |
| baseline | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| baseline | minor_page_faults | 102.00 | 107.00 | 110.00 | 118.00 |
| range_interior | prefetch_elapsed_us | 112.00 µs | 118.00 µs | 141.00 µs | 141.00 µs |
| range_interior | first_query_latency_us | 233.29 µs | 251.54 µs | 259.01 µs | 561.49 µs |
| range_interior | effective_first_query_latency_us | 374.29 µs | 377.01 µs | 392.54 µs | 672.49 µs |
| range_interior | average_latency_us | 41.56 µs | 43.59 µs | 45.33 µs | 91.81 µs |
| range_interior | major_page_faults | 220.00 | 234.00 | 239.00 | 239.00 |
| range_interior | minor_page_faults | 147.00 | 151.00 | 153.00 | 155.00 |
| range_interior | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| range_interior | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | prefetch_elapsed_us | 6.00 µs | 7.00 µs | 7.00 µs | 14.00 µs |
| offset_topk_interior_n5 | first_query_latency_us | 400.74 µs | 402.92 µs | 681.97 µs | 850.23 µs |
| offset_topk_interior_n5 | effective_first_query_latency_us | 407.74 µs | 408.92 µs | 688.97 µs | 856.23 µs |
| offset_topk_interior_n5 | average_latency_us | 49.61 µs | 51.23 µs | 96.88 µs | 106.40 µs |
| offset_topk_interior_n5 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| offset_topk_interior_n5 | minor_page_faults | 103.00 | 110.00 | 111.00 | 118.00 |
| offset_topk_interior_n5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | prefetch_elapsed_us | 5.00 µs | 5.00 µs | 5.00 µs | 7.00 µs |
| residency_topk_interior5_leaf0_i5_l0 | first_query_latency_us | 370.78 µs | 378.22 µs | 443.82 µs | 1160.39 µs |
| residency_topk_interior5_leaf0_i5_l0 | effective_first_query_latency_us | 377.78 µs | 383.22 µs | 448.82 µs | 1165.39 µs |
| residency_topk_interior5_leaf0_i5_l0 | average_latency_us | 47.91 µs | 47.96 µs | 49.43 µs | 101.87 µs |
| residency_topk_interior5_leaf0_i5_l0 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| residency_topk_interior5_leaf0_i5_l0 | minor_page_faults | 104.00 | 109.00 | 111.00 | 120.00 |
| residency_topk_interior5_leaf0_i5_l0 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | prefetch_elapsed_us | 6.00 µs | 7.00 µs | 7.00 µs | 8.00 µs |
| residency_topk_interior5_leaf5_i5_l5 | first_query_latency_us | 373.15 µs | 387.46 µs | 390.88 µs | 408.77 µs |
| residency_topk_interior5_leaf5_i5_l5 | effective_first_query_latency_us | 381.15 µs | 394.46 µs | 396.88 µs | 415.77 µs |
| residency_topk_interior5_leaf5_i5_l5 | average_latency_us | 45.99 µs | 50.42 µs | 51.56 µs | 121.97 µs |
| residency_topk_interior5_leaf5_i5_l5 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| residency_topk_interior5_leaf5_i5_l5 | minor_page_faults | 103.00 | 109.00 | 111.00 | 118.00 |
| residency_topk_interior5_leaf5_i5_l5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |

##### original / unlimited / pread：Strategy 比較

`Effective first-query latency = prefetch elapsed + first-query latency`；其改善率使用相同measurement file與repetition的baseline first-query latency配對計算。

| Strategy key | Prefetch median | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio | Major faults | Minor faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 430.55 µs | 0.00% | 430.55 µs | 0.00% | 49.26 µs | 0.00% | — | — | 264.00 | 107.00 |
| range_interior | 4817.00 µs | 245.94 µs | 42.02% | 5073.94 µs | -2525.36% | 43.86 µs | 4.60% | 1.0000 | 1.0000 | 234.00 | 152.00 |
| offset_topk_interior_n5 | 129.00 µs | 368.45 µs | -3.59% | 505.79 µs | -63.00% | 49.67 µs | -7.49% | 1.0000 | 1.0000 | 264.00 | 109.00 |
| residency_topk_interior5_leaf0_i5_l0 | 135.00 µs | 432.32 µs | -18.30% | 565.32 µs | -75.18% | 50.94 µs | -42.35% | 1.0000 | 1.0000 | 264.00 | 109.00 |
| residency_topk_interior5_leaf5_i5_l5 | 134.00 µs | 371.42 µs | 15.29% | 562.16 µs | -23.66% | 49.12 µs | 5.85% | 1.0000 | 1.0000 | 264.00 | 110.00 |

Distribution 詳細：

| Strategy key | Metric | P25 | Median | P75 | P99 |
| --- | --- | --- | --- | --- | --- |
| baseline | first_query_latency_us | 428.81 µs | 430.55 µs | 433.35 µs | 443.82 µs |
| baseline | effective_first_query_latency_us | 428.81 µs | 430.55 µs | 433.35 µs | 443.82 µs |
| baseline | average_latency_us | 46.57 µs | 49.26 µs | 50.69 µs | 72.20 µs |
| baseline | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| baseline | minor_page_faults | 102.00 | 107.00 | 110.00 | 118.00 |
| range_interior | prefetch_elapsed_us | 4809.00 µs | 4817.00 µs | 4828.00 µs | 35737.00 µs |
| range_interior | first_query_latency_us | 234.12 µs | 245.94 µs | 266.76 µs | 275.14 µs |
| range_interior | effective_first_query_latency_us | 5043.12 µs | 5073.94 µs | 5083.76 µs | 36012.14 µs |
| range_interior | average_latency_us | 41.87 µs | 43.86 µs | 44.03 µs | 75.45 µs |
| range_interior | major_page_faults | 220.00 | 234.00 | 239.00 | 239.00 |
| range_interior | minor_page_faults | 147.00 | 152.00 | 154.00 | 154.00 |
| range_interior | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| range_interior | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | prefetch_elapsed_us | 129.00 µs | 129.00 µs | 315.00 µs | 581.00 µs |
| offset_topk_interior_n5 | first_query_latency_us | 367.59 µs | 368.45 µs | 376.79 µs | 896.09 µs |
| offset_topk_interior_n5 | effective_first_query_latency_us | 497.45 µs | 505.79 µs | 682.59 µs | 1477.09 µs |
| offset_topk_interior_n5 | average_latency_us | 46.30 µs | 49.67 µs | 50.73 µs | 100.12 µs |
| offset_topk_interior_n5 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| offset_topk_interior_n5 | minor_page_faults | 104.00 | 109.00 | 111.00 | 119.00 |
| offset_topk_interior_n5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | prefetch_elapsed_us | 134.00 µs | 135.00 µs | 294.00 µs | 512.00 µs |
| residency_topk_interior5_leaf0_i5_l0 | first_query_latency_us | 378.94 µs | 432.32 µs | 447.08 µs | 1075.68 µs |
| residency_topk_interior5_leaf0_i5_l0 | effective_first_query_latency_us | 512.94 µs | 565.32 µs | 582.08 µs | 1587.68 µs |
| residency_topk_interior5_leaf0_i5_l0 | average_latency_us | 48.25 µs | 50.94 µs | 102.22 µs | 111.61 µs |
| residency_topk_interior5_leaf0_i5_l0 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| residency_topk_interior5_leaf0_i5_l0 | minor_page_faults | 105.00 | 109.00 | 110.00 | 118.00 |
| residency_topk_interior5_leaf0_i5_l0 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | prefetch_elapsed_us | 132.00 µs | 134.00 µs | 154.00 µs | 289.00 µs |
| residency_topk_interior5_leaf5_i5_l5 | first_query_latency_us | 361.43 µs | 371.42 µs | 422.43 µs | 428.16 µs |
| residency_topk_interior5_leaf5_i5_l5 | effective_first_query_latency_us | 493.43 µs | 562.16 µs | 576.43 µs | 660.42 µs |
| residency_topk_interior5_leaf5_i5_l5 | average_latency_us | 46.91 µs | 49.12 µs | 49.91 µs | 52.88 µs |
| residency_topk_interior5_leaf5_i5_l5 | major_page_faults | 252.00 | 264.00 | 274.00 | 281.00 |
| residency_topk_interior5_leaf5_i5_l5 | minor_page_faults | 104.00 | 110.00 | 110.00 | 118.00 |
| residency_topk_interior5_leaf5_i5_l5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |

##### original / unlimited：Backend 比較

`madvise` prefetch cost為非同步request submission時間；`pread` prefetch cost為同步read完成時間。

| Backend | Strategy key | Prefetch median | Prefetch P25–P75 | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | baseline | — | — | 430.55 µs | 0.00% | 430.55 µs | 0.00% | 49.26 µs | 0.00% | — | — |
| madvise | range_interior | 118.00 µs | 112.00 µs–141.00 µs | 251.54 µs | 29.08% | 377.01 µs | -0.12% | 43.59 µs | -2.01% | 1.0000 | 1.0000 |
| madvise | offset_topk_interior_n5 | 7.00 µs | 6.00 µs–7.00 µs | 402.92 µs | -26.80% | 408.92 µs | -28.66% | 51.23 µs | -41.58% | 1.0000 | 1.0000 |
| madvise | residency_topk_interior5_leaf0_i5_l0 | 5.00 µs | 5.00 µs–5.00 µs | 378.22 µs | -22.08% | 383.22 µs | -23.34% | 47.96 µs | -13.49% | 1.0000 | 1.0000 |
| madvise | residency_topk_interior5_leaf5_i5_l5 | 7.00 µs | 6.00 µs–7.00 µs | 387.46 µs | 15.11% | 394.46 µs | 13.57% | 50.42 µs | -13.64% | 1.0000 | 1.0000 |
| pread | range_interior | 4817.00 µs | 4809.00 µs–4828.00 µs | 245.94 µs | 42.02% | 5073.94 µs | -2525.36% | 43.86 µs | 4.60% | 1.0000 | 1.0000 |
| pread | offset_topk_interior_n5 | 129.00 µs | 129.00 µs–315.00 µs | 368.45 µs | -3.59% | 505.79 µs | -63.00% | 49.67 µs | -7.49% | 1.0000 | 1.0000 |
| pread | residency_topk_interior5_leaf0_i5_l0 | 135.00 µs | 134.00 µs–294.00 µs | 432.32 µs | -18.30% | 565.32 µs | -75.18% | 50.94 µs | -42.35% | 1.0000 | 1.0000 |
| pread | residency_topk_interior5_leaf5_i5_l5 | 134.00 µs | 132.00 µs–154.00 µs | 371.42 µs | 15.29% | 562.16 µs | -23.66% | 49.12 µs | 5.85% | 1.0000 | 1.0000 |

## Prefetch cost 與 first-query improvement trade-off

### madvise

![madvise prefetch trade-off](plots/tradeoff_madvise.png)

| Workload type | Layout | Memory condition | Strategy key | Prefetch median（P25–P75） | First-query improvement median（P25–P75） |
| --- | --- | --- | --- | --- | --- |
| scan_zipf_full | original | unlimited | range_interior | 118.00 µs（112.00–141.00） | 41.64%（41.34–42.24） |
| scan_zipf_full | original | unlimited | offset_topk_interior_n5 | 7.00 µs（6.00–7.00） | 6.42%（-68.83–6.55） |
| scan_zipf_full | original | unlimited | residency_topk_interior5_leaf0_i5_l0 | 5.00 µs（5.00–5.00） | 11.80%（-2.42–16.46） |
| scan_zipf_full | original | unlimited | residency_topk_interior5_leaf5_i5_l5 | 7.00 µs（6.00–7.00） | 9.64%（9.21–13.89） |
### pread

![pread prefetch trade-off](plots/tradeoff_pread.png)

| Workload type | Layout | Memory condition | Strategy key | Prefetch median（P25–P75） | First-query improvement median（P25–P75） |
| --- | --- | --- | --- | --- | --- |
| scan_zipf_full | original | unlimited | range_interior | 4817.00 µs（4809.00–4828.00） | 42.04%（38.44–44.59） |
| scan_zipf_full | original | unlimited | offset_topk_interior_n5 | 129.00 µs（129.00–315.00） | 14.08%（12.49–17.18） |
| scan_zipf_full | original | unlimited | residency_topk_interior5_leaf0_i5_l0 | 135.00 µs（134.00–294.00） | -0.41%（-0.73–12.56） |
| scan_zipf_full | original | unlimited | residency_topk_interior5_leaf5_i5_l5 | 134.00 µs（132.00–154.00） | 15.71%（1.89–16.31） |

## Cell 狀態

| Status | 數量 |
| --- | --- |
| completed | 45 |
| failed | 0 |
| timeout | 0 |
| invalid | 0 |

## Training 與 measurement workload 清單

### scan_zipf_full

| 用途 | 抽樣順序 | Index | 檔名 | SHA-256 | Repetitions |
| --- | --- | --- | --- | --- | --- |
| training | 1 | 010 | scan_zipf_full_010.txt | 38ec3b6beec09316de8d294b1600dd3122e37332ec07060d524b46c1b2a04240 | 1 |
| training | 2 | 022 | scan_zipf_full_022.txt | 1357d901c2884842130e2c06f2827a017c79745499215307c73e1cc8d73a35d3 | 1 |
| training | 3 | 024 | scan_zipf_full_024.txt | 1d7282f0f1a7a8007fd2b3bb3e0ebb82034550a770feffaace83e726da0d5743 | 1 |
| training | 4 | 006 | scan_zipf_full_006.txt | e9a6727dfc13cf1abe627f1fc433488b12cf1f183602166af405246f5fb6b84c | 1 |
| training | 5 | 025 | scan_zipf_full_025.txt | 61af772d6a262b693926fe7bc7972ede84b4499e844f65aeba87ad6e70e5bded | 1 |
| measurement | 1 | 034 | scan_zipf_full_034.txt | b354d72d395f5fb4949c7679fd7763dae1926d6b48de1b73c67d61615d3847c8 | 1 |
| measurement | 2 | 046 | scan_zipf_full_046.txt | 81bf9b29ca448f3d4650d2e6a8b720bc093b0a48436bc1b4ad2e2763cbcf7326 | 1 |
| measurement | 3 | 027 | scan_zipf_full_027.txt | ef4fb9a0cb8a5637490d251b4d850cbd822f2dc355de3b1e173e1db0470cb0f9 | 1 |
| measurement | 4 | 033 | scan_zipf_full_033.txt | a74dc7e540020291a6a19ab0fa029b88009adc0332e39cdeeca586113284097b | 1 |
| measurement | 5 | 036 | scan_zipf_full_036.txt | 5ff3fa5439556b92f4c1e6440c8c7c7bb906057727a2706da242e17381db2919 | 1 |

## Artifacts 連結

- [Experiment config](<config.json>)
- [Experiment manifest](<manifest.json>)
- [All raw results](<results/all_raw.csv>)
- [scan_zipf_full/unlimited layout comparison](<results/scan_zipf_full/layout_comparisons/unlimited.csv>)
- [scan_zipf_full/original/unlimited/madvise strategy comparison](<results/scan_zipf_full/original/memory_conditions/unlimited/backends/madvise/strategy_comparison.csv>)
- [scan_zipf_full/original/unlimited/pread strategy comparison](<results/scan_zipf_full/original/memory_conditions/unlimited/backends/pread/strategy_comparison.csv>)
- [scan_zipf_full/original/unlimited backend comparison](<results/scan_zipf_full/original/memory_conditions/unlimited/backend_comparison.csv>)
- [scan_zipf_full/original memory comparison](<results/scan_zipf_full/original/memory_comparison.csv>)
- [Trade-off data](<plots/tradeoff_points.csv>)

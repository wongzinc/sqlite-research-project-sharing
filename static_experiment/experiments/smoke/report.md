# 實驗報告：smoke

## 實驗摘要

| 項目 | 值 |
| --- | --- |
| Experiment ID | smoke |
| Prefetch backends | madvise → pread |
| Enabled layouts | original |
| Workload types | read_zipf_full |
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

### read_zipf_full

#### Memory condition：unlimited

##### Layout 比較

| Layout | First-query median | First-query P25–P75 | First-query P99 | 改善 vs original | Average-query median | Average-query改善 vs original |
| --- | --- | --- | --- | --- | --- | --- |
| original | 218.82 µs | 191.71 µs–224.05 µs | 384.27 µs | 0.00% | 44.35 µs | 0.00% |

##### original / unlimited / madvise：Strategy 比較

`Effective first-query latency = prefetch elapsed + first-query latency`；其改善率使用相同measurement file與repetition的baseline first-query latency配對計算。

| Strategy key | Prefetch median | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio | Major faults | Minor faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 218.82 µs | 0.00% | 218.82 µs | 0.00% | 44.35 µs | 0.00% | — | — | 254.00 | 64.00 |
| range_interior | 125.00 µs | 19.47 µs | 79.91% | 150.47 µs | 23.77% | 37.80 µs | 16.61% | 1.0000 | 1.0000 | 218.00 | 105.00 |
| offset_topk_interior_n5 | 8.00 µs | 30.92 µs | 69.03% | 38.92 µs | 65.07% | 43.99 µs | 1.88% | 1.0000 | 1.0000 | 254.00 | 65.00 |
| residency_topk_interior5_leaf0_i5_l0 | 6.00 µs | 22.05 µs | 71.16% | 28.05 µs | 68.59% | 43.92 µs | 2.00% | 1.0000 | 1.0000 | 254.00 | 64.00 |
| residency_topk_interior5_leaf5_i5_l5 | 7.00 µs | 24.13 µs | 71.62% | 30.13 µs | 68.53% | 43.54 µs | -2.68% | 1.0000 | 1.0000 | 254.00 | 65.00 |

Distribution 詳細：

| Strategy key | Metric | P25 | Median | P75 | P99 |
| --- | --- | --- | --- | --- | --- |
| baseline | first_query_latency_us | 191.71 µs | 218.82 µs | 224.05 µs | 384.27 µs |
| baseline | effective_first_query_latency_us | 191.71 µs | 218.82 µs | 224.05 µs | 384.27 µs |
| baseline | average_latency_us | 42.73 µs | 44.35 µs | 47.88 µs | 48.85 µs |
| baseline | major_page_faults | 245.00 | 254.00 | 257.00 | 279.00 |
| baseline | minor_page_faults | 61.00 | 64.00 | 69.00 | 71.00 |
| range_interior | prefetch_elapsed_us | 124.00 µs | 125.00 µs | 131.00 µs | 131.00 µs |
| range_interior | first_query_latency_us | 19.00 µs | 19.47 µs | 34.33 µs | 213.80 µs |
| range_interior | effective_first_query_latency_us | 144.00 µs | 150.47 µs | 165.33 µs | 337.80 µs |
| range_interior | average_latency_us | 35.91 µs | 37.80 µs | 38.38 µs | 41.06 µs |
| range_interior | major_page_faults | 209.00 | 218.00 | 220.00 | 240.00 |
| range_interior | minor_page_faults | 104.00 | 105.00 | 108.00 | 111.00 |
| range_interior | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| range_interior | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | prefetch_elapsed_us | 6.00 µs | 8.00 µs | 8.00 µs | 16.00 µs |
| offset_topk_interior_n5 | first_query_latency_us | 25.79 µs | 30.92 µs | 44.99 µs | 362.02 µs |
| offset_topk_interior_n5 | effective_first_query_latency_us | 37.28 µs | 38.92 µs | 52.99 µs | 368.02 µs |
| offset_topk_interior_n5 | average_latency_us | 42.65 µs | 43.99 µs | 44.62 µs | 47.85 µs |
| offset_topk_interior_n5 | major_page_faults | 245.00 | 254.00 | 256.00 | 280.00 |
| offset_topk_interior_n5 | minor_page_faults | 62.00 | 65.00 | 70.00 | 72.00 |
| offset_topk_interior_n5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | prefetch_elapsed_us | 5.00 µs | 6.00 µs | 6.00 µs | 8.00 µs |
| residency_topk_interior5_leaf0_i5_l0 | first_query_latency_us | 19.83 µs | 22.05 µs | 44.41 µs | 363.13 µs |
| residency_topk_interior5_leaf0_i5_l0 | effective_first_query_latency_us | 24.83 µs | 28.05 µs | 50.41 µs | 371.13 µs |
| residency_topk_interior5_leaf0_i5_l0 | average_latency_us | 42.27 µs | 43.92 µs | 44.12 µs | 49.17 µs |
| residency_topk_interior5_leaf0_i5_l0 | major_page_faults | 245.00 | 254.00 | 256.00 | 280.00 |
| residency_topk_interior5_leaf0_i5_l0 | minor_page_faults | 63.00 | 64.00 | 70.00 | 72.00 |
| residency_topk_interior5_leaf0_i5_l0 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | prefetch_elapsed_us | 6.00 µs | 7.00 µs | 8.00 µs | 9.00 µs |
| residency_topk_interior5_leaf5_i5_l5 | first_query_latency_us | 21.96 µs | 24.13 µs | 24.78 µs | 380.75 µs |
| residency_topk_interior5_leaf5_i5_l5 | effective_first_query_latency_us | 27.96 µs | 30.13 µs | 32.78 µs | 389.75 µs |
| residency_topk_interior5_leaf5_i5_l5 | average_latency_us | 43.19 µs | 43.54 µs | 46.68 µs | 56.04 µs |
| residency_topk_interior5_leaf5_i5_l5 | major_page_faults | 245.00 | 254.00 | 256.00 | 280.00 |
| residency_topk_interior5_leaf5_i5_l5 | minor_page_faults | 63.00 | 65.00 | 70.00 | 72.00 |
| residency_topk_interior5_leaf5_i5_l5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |

##### original / unlimited / pread：Strategy 比較

`Effective first-query latency = prefetch elapsed + first-query latency`；其改善率使用相同measurement file與repetition的baseline first-query latency配對計算。

| Strategy key | Prefetch median | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio | Major faults | Minor faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 218.82 µs | 0.00% | 218.82 µs | 0.00% | 44.35 µs | 0.00% | — | — | 254.00 | 64.00 |
| range_interior | 4828.00 µs | 21.76 µs | 80.85% | 4848.88 µs | -2055.32% | 38.46 µs | 11.44% | 1.0000 | 1.0000 | 218.00 | 105.00 |
| offset_topk_interior_n5 | 314.00 µs | 41.75 µs | 68.66% | 366.35 µs | -44.71% | 43.92 µs | 1.71% | 1.0000 | 1.0000 | 253.00 | 64.00 |
| residency_topk_interior5_leaf0_i5_l0 | 134.00 µs | 36.07 µs | 64.34% | 180.07 µs | -9.82% | 44.26 µs | 0.98% | 1.0000 | 1.0000 | 253.00 | 64.00 |
| residency_topk_interior5_leaf5_i5_l5 | 291.00 µs | 19.77 µs | 73.71% | 313.97 µs | -34.96% | 44.21 µs | 0.21% | 1.0000 | 1.0000 | 253.00 | 64.00 |

Distribution 詳細：

| Strategy key | Metric | P25 | Median | P75 | P99 |
| --- | --- | --- | --- | --- | --- |
| baseline | first_query_latency_us | 191.71 µs | 218.82 µs | 224.05 µs | 384.27 µs |
| baseline | effective_first_query_latency_us | 191.71 µs | 218.82 µs | 224.05 µs | 384.27 µs |
| baseline | average_latency_us | 42.73 µs | 44.35 µs | 47.88 µs | 48.85 µs |
| baseline | major_page_faults | 245.00 | 254.00 | 257.00 | 279.00 |
| baseline | minor_page_faults | 61.00 | 64.00 | 69.00 | 71.00 |
| range_interior | prefetch_elapsed_us | 4820.00 µs | 4828.00 µs | 4829.00 µs | 4845.00 µs |
| range_interior | first_query_latency_us | 20.88 µs | 21.76 µs | 35.58 µs | 184.22 µs |
| range_interior | effective_first_query_latency_us | 4838.57 µs | 4848.88 µs | 4850.76 µs | 5029.22 µs |
| range_interior | average_latency_us | 36.95 µs | 38.46 µs | 39.11 µs | 50.26 µs |
| range_interior | major_page_faults | 209.00 | 218.00 | 220.00 | 240.00 |
| range_interior | minor_page_faults | 104.00 | 105.00 | 108.00 | 111.00 |
| range_interior | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| range_interior | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | prefetch_elapsed_us | 129.00 µs | 314.00 µs | 326.00 µs | 338.00 µs |
| offset_topk_interior_n5 | first_query_latency_us | 28.35 µs | 41.75 µs | 41.92 µs | 357.20 µs |
| offset_topk_interior_n5 | effective_first_query_latency_us | 355.92 µs | 366.35 µs | 367.75 µs | 486.20 µs |
| offset_topk_interior_n5 | average_latency_us | 42.52 µs | 43.92 µs | 45.25 µs | 48.61 µs |
| offset_topk_interior_n5 | major_page_faults | 245.00 | 253.00 | 256.00 | 280.00 |
| offset_topk_interior_n5 | minor_page_faults | 62.00 | 64.00 | 70.00 | 72.00 |
| offset_topk_interior_n5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| offset_topk_interior_n5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | prefetch_elapsed_us | 133.00 µs | 134.00 µs | 144.00 µs | 292.00 µs |
| residency_topk_interior5_leaf0_i5_l0 | first_query_latency_us | 35.39 µs | 36.07 µs | 36.29 µs | 433.94 µs |
| residency_topk_interior5_leaf0_i5_l0 | effective_first_query_latency_us | 170.29 µs | 180.07 µs | 316.96 µs | 562.94 µs |
| residency_topk_interior5_leaf0_i5_l0 | average_latency_us | 42.93 µs | 44.26 µs | 46.02 µs | 48.94 µs |
| residency_topk_interior5_leaf0_i5_l0 | major_page_faults | 245.00 | 253.00 | 256.00 | 280.00 |
| residency_topk_interior5_leaf0_i5_l0 | minor_page_faults | 62.00 | 64.00 | 70.00 | 72.00 |
| residency_topk_interior5_leaf0_i5_l0 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf0_i5_l0 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | prefetch_elapsed_us | 137.00 µs | 291.00 µs | 294.00 µs | 308.00 µs |
| residency_topk_interior5_leaf5_i5_l5 | first_query_latency_us | 18.21 µs | 19.77 µs | 19.97 µs | 363.16 µs |
| residency_topk_interior5_leaf5_i5_l5 | effective_first_query_latency_us | 310.77 µs | 313.97 µs | 325.32 µs | 500.16 µs |
| residency_topk_interior5_leaf5_i5_l5 | average_latency_us | 43.54 µs | 44.21 µs | 45.26 µs | 49.37 µs |
| residency_topk_interior5_leaf5_i5_l5 | major_page_faults | 245.00 | 253.00 | 256.00 | 280.00 |
| residency_topk_interior5_leaf5_i5_l5 | minor_page_faults | 63.00 | 64.00 | 70.00 | 72.00 |
| residency_topk_interior5_leaf5_i5_l5 | requested_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |
| residency_topk_interior5_leaf5_i5_l5 | successful_selected_resident_ratio | 1.00 | 1.00 | 1.00 | 1.00 |

##### original / unlimited：Backend 比較

`madvise` prefetch cost為非同步request submission時間；`pread` prefetch cost為同步read完成時間。

| Backend | Strategy key | Prefetch median | Prefetch P25–P75 | First-query median | First-query改善 | Effective first-query median | Effective first-query改善 | Average-query median | Average-query改善 | Requested resident ratio | Successful resident ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | baseline | — | — | 218.82 µs | 0.00% | 218.82 µs | 0.00% | 44.35 µs | 0.00% | — | — |
| madvise | range_interior | 125.00 µs | 124.00 µs–131.00 µs | 19.47 µs | 79.91% | 150.47 µs | 23.77% | 37.80 µs | 16.61% | 1.0000 | 1.0000 |
| madvise | offset_topk_interior_n5 | 8.00 µs | 6.00 µs–8.00 µs | 30.92 µs | 69.03% | 38.92 µs | 65.07% | 43.99 µs | 1.88% | 1.0000 | 1.0000 |
| madvise | residency_topk_interior5_leaf0_i5_l0 | 6.00 µs | 5.00 µs–6.00 µs | 22.05 µs | 71.16% | 28.05 µs | 68.59% | 43.92 µs | 2.00% | 1.0000 | 1.0000 |
| madvise | residency_topk_interior5_leaf5_i5_l5 | 7.00 µs | 6.00 µs–8.00 µs | 24.13 µs | 71.62% | 30.13 µs | 68.53% | 43.54 µs | -2.68% | 1.0000 | 1.0000 |
| pread | range_interior | 4828.00 µs | 4820.00 µs–4829.00 µs | 21.76 µs | 80.85% | 4848.88 µs | -2055.32% | 38.46 µs | 11.44% | 1.0000 | 1.0000 |
| pread | offset_topk_interior_n5 | 314.00 µs | 129.00 µs–326.00 µs | 41.75 µs | 68.66% | 366.35 µs | -44.71% | 43.92 µs | 1.71% | 1.0000 | 1.0000 |
| pread | residency_topk_interior5_leaf0_i5_l0 | 134.00 µs | 133.00 µs–144.00 µs | 36.07 µs | 64.34% | 180.07 µs | -9.82% | 44.26 µs | 0.98% | 1.0000 | 1.0000 |
| pread | residency_topk_interior5_leaf5_i5_l5 | 291.00 µs | 137.00 µs–294.00 µs | 19.77 µs | 73.71% | 313.97 µs | -34.96% | 44.21 µs | 0.21% | 1.0000 | 1.0000 |

## Prefetch cost 與 first-query improvement trade-off

### madvise

![madvise prefetch trade-off](plots/tradeoff_madvise.png)

| Workload type | Layout | Memory condition | Strategy key | Prefetch median（P25–P75） | First-query improvement median（P25–P75） |
| --- | --- | --- | --- | --- | --- |
| read_zipf_full | original | unlimited | range_interior | 125.00 µs（124.00–131.00） | 89.93%（82.09–91.10） |
| read_zipf_full | original | unlimited | offset_topk_interior_n5 | 8.00 µs（6.00–8.00） | 86.20%（76.53–86.33） |
| read_zipf_full | original | unlimited | residency_topk_interior5_leaf0_i5_l0 | 6.00 µs（5.00–6.00） | 88.50%（79.70–90.94） |
| read_zipf_full | original | unlimited | residency_topk_interior5_leaf5_i5_l5 | 7.00 µs（6.00–8.00） | 88.94%（88.36–88.97） |
### pread

![pread prefetch trade-off](plots/tradeoff_pread.png)

| Workload type | Layout | Memory condition | Strategy key | Prefetch median（P25–P75） | First-query improvement median（P25–P75） |
| --- | --- | --- | --- | --- | --- |
| read_zipf_full | original | unlimited | range_interior | 4828.00 µs（4820.00–4829.00） | 88.93%（81.44–90.29） |
| read_zipf_full | original | unlimited | offset_topk_interior_n5 | 314.00 µs（129.00–326.00） | 81.29%（80.92–85.21） |
| read_zipf_full | original | unlimited | residency_topk_interior5_leaf0_i5_l0 | 134.00 µs（133.00–144.00） | 81.19%（80.77–83.83） |
| read_zipf_full | original | unlimited | residency_topk_interior5_leaf5_i5_l5 | 291.00 µs（137.00–294.00） | 89.69%（89.42–91.87） |

## Cell 狀態

| Status | 數量 |
| --- | --- |
| completed | 45 |
| failed | 0 |
| timeout | 0 |
| invalid | 0 |

## Training 與 measurement workload 清單

### read_zipf_full

| 用途 | 抽樣順序 | Index | 檔名 | SHA-256 | Repetitions |
| --- | --- | --- | --- | --- | --- |
| training | 1 | 010 | read_zipf_full_010.txt | 4ba56bb0a25bf4f246379b35ac3d274e690fa03b623d96002a860afe666c6863 | 1 |
| training | 2 | 022 | read_zipf_full_022.txt | 9e5f291e74aaf2164385a4b7feb6aab96846420cf940e873bb32965f45beef08 | 1 |
| training | 3 | 024 | read_zipf_full_024.txt | 268ead0667fe965b8eaba427dd0722bb25a96b884747d1d499ab3663040fa2c6 | 1 |
| training | 4 | 006 | read_zipf_full_006.txt | 0b476cd40c31d16f0da65b7e057b3c9d14dc2f9f820a761166b089877f517af6 | 1 |
| training | 5 | 025 | read_zipf_full_025.txt | 9faa76bdb3003ddc0c1ab540ceb0370c627cbf70bd59de9ae9813a9523b972b6 | 1 |
| measurement | 1 | 034 | read_zipf_full_034.txt | a0689409c9d30226b06d2c28df69640447b566363966caed3fcb2c62592972d3 | 1 |
| measurement | 2 | 046 | read_zipf_full_046.txt | e722a11f77e2e687e5ede4221243af879bfa38bf630e90cd2d85738f07ce12d6 | 1 |
| measurement | 3 | 027 | read_zipf_full_027.txt | abc214374e3a259d57bc15d11d1942f07faa5e278e136dce715fef9c0b4050a5 | 1 |
| measurement | 4 | 033 | read_zipf_full_033.txt | ba3af72ec57ec0f276746dc84e3cd93be25d0e07f5b5e4df6d0bcea66854c884 | 1 |
| measurement | 5 | 036 | read_zipf_full_036.txt | c9a5f97bc1259d977d3289dcb8777bb21ae1b2bc5aec1c10231c3f71552164d0 | 1 |

## Artifacts 連結

- [Experiment config](<config.json>)
- [Experiment manifest](<manifest.json>)
- [All raw results](<results/all_raw.csv>)
- [read_zipf_full/unlimited layout comparison](<results/read_zipf_full/layout_comparisons/unlimited.csv>)
- [read_zipf_full/original/unlimited/madvise strategy comparison](<results/read_zipf_full/original/memory_conditions/unlimited/backends/madvise/strategy_comparison.csv>)
- [read_zipf_full/original/unlimited/pread strategy comparison](<results/read_zipf_full/original/memory_conditions/unlimited/backends/pread/strategy_comparison.csv>)
- [read_zipf_full/original/unlimited backend comparison](<results/read_zipf_full/original/memory_conditions/unlimited/backend_comparison.csv>)
- [read_zipf_full/original memory comparison](<results/read_zipf_full/original/memory_comparison.csv>)
- [Trade-off data](<plots/tradeoff_points.csv>)

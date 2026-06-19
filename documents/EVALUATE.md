# Bao cao thiet ke metrics danh gia RAG

Tai lieu nay mo ta bo metrics hien tai cua ChatVNS sau khi rut gon ve mot flow duy nhat. Dashboard va report chi hien thi mot bo evaluation chung.

## Evaluation Updated

### A. Retrieval

- `Recall@5`
- `Precision@5`
- `Hit Rate@5`
- `MRR`

### B. DeepEval

- `Faithfulness`
- `Answer Relevancy`

### C. Finance-specific

- `Numerical Accuracy`
- `Citation Accuracy`

| Nhom       | Metric             |
| ---------- | ------------------ |
| Retrieval  | Recall@5           |
| Retrieval  | Precision@5        |
| Retrieval  | Hit Rate@5         |
| Retrieval  | MRR                |
| Generation | Faithfulness       |
| Generation | Answer Relevancy   |
| Finance    | Numerical Accuracy |
| Finance    | Citation Accuracy  |

## Cach tinh

`Recall@5` do ty le expected evidence xuat hien trong top-5 retrieved chunks. Metric nay dang tin nhat khi eval case co `expected_chunks`.

`Precision@5` do ty le chunk lien quan trong cac ket qua duoc tra ve o top-5.

`Hit Rate@5` bang 1 neu co it nhat mot chunk lien quan trong top-5, nguoc lai bang 0.

`MRR` do thu hang cua chunk lien quan dau tien. Chunk lien quan dung cang cao thi MRR cang cao.

`Faithfulness` va `Answer Relevancy` duoc cham trong cung mot lenh `python -m app.evaluate`. Day la hai metric LLM-as-a-Judge cua DeepEval cho phan generation. Neu DeepEval loi quota/API, report dung fallback cuc bo va ghi ro trong `fallback_metrics` cua tung case.

`Numerical Accuracy` so khop cac so lieu trong cau tra loi voi `expected_numbers` neu eval case khai bao truong nay. Neu khong co `expected_numbers`, metric fallback sang cac so lieu trich tu `expected_output`, `expected_answer`, `reference_answer` hoac expected context. Neu case auto-generated chua co reference so lieu, metric van tra ve score fallback va ghi `fallback_metrics`.

`Citation Accuracy` so khop source tra ve voi `expected_source_keywords`; neu thieu truong nay thi fallback sang `expected_chunks` va source metadata. Khi eval case auto-generated chua co reference source, metric van tra ve score fallback dua tren viec answer co source va ghi `fallback_metrics`.

## Cach chay

Chay evaluation day du:

```powershell
.\.venv\Scripts\python.exe -m app.evaluate
```

Tuy chinh top-k, so lan do latency va luu reason cua DeepEval:

```powershell
.\.venv\Scripts\python.exe -m app.evaluate --top-k 5 --repeats 1 --include-reason
```

Khi `.env` co `GEMINI_API_KEY`, DeepEval mac dinh dung `GEMINI_MODEL`. Co the ep model bang `--eval-model`, vi du:

```powershell
.\.venv\Scripts\python.exe -m app.evaluate --eval-model gemini-1.5-flash
```

## Cach doc Dashboard

Dashboard chi hien thi report moi nhat trong `data/evaluation/reports` va gom metrics thanh mot khu vuc Evaluation:

- Retrieval: `Recall@5`, `Precision@5`, `Hit Rate@5`, `MRR`
- Generation: `Faithfulness`, `Answer Relevancy`
- Finance: `Numerical Accuracy`, `Citation Accuracy`
- Performance: `Retrieval p95 ms`, `Answer p95 ms`

Neu metric dung fallback, xem cot `fallback_metrics` trong JSON report de biet ly do.

## Ket qua chay gan nhat

Report duoc doc tu:

```text
data/evaluation/reports/evaluation_report_20260601T101548Z.json
```

Thong tin run:

| Truong | Gia tri |
| ------ | ------- |
| Thoi gian tao | 2026-06-01T10:15:48.627873+00:00 |
| Eval model | gemini-2.5-flash |
| Top-k | 5 |
| Repeats | 3 |
| So cases | 9 |
| Cases path | D:/LAB/chatvns/data/evaluation/eval_cases.json |

### Summary metrics

| Nhom | Metric | Ket qua |
| ---- | ------ | ------- |
| Retrieval | Recall@5 | 1.0 |
| Retrieval | MRR | 1.0 |
| Generation | Faithfulness | 0.893 |
| Generation | Answer Relevancy | 0.883 |
| Finance | Numerical Accuracy | 1.0 |
| Finance | Citation Accuracy | 1.0 |

### Performance

| Metric | Count | Avg ms | P95 ms | Min ms | Max ms |
| ------ | ----- | ------ | ------ | ------ | ------ |
| Retrieval latency | 27 | 138.4 | 165.4 | 104.83 | 175.28 |
| Answer latency | 27 | 772.8 | 1624.95 | 606.06 | 1638.61 |

Latency theo tung evaluation case trong phan retrieval/generation summary:

| Stage | Count | Avg ms | P95 ms | Min ms | Max ms |
| ----- | ----- | ------ | ------ | ------ | ------ |
| Retrieval cases | 9 | 1828.95 | 9295.31 | 109.8 | 15358.89 |
| Generation cases | 9 | 2372.13 | 7434.62 | 619.69 | 8550.49 |

### Luu y ve fallback

Run nay co du 8 metrics tren Dashboard, nhung cac metric generation/finance dang dung fallback cuc bo:

| Fallback | So cases |
| -------- | -------- |
| faithfulness: lexical_context_grounding | 9 |
| answer_relevancy: question_answer_token_overlap | 9 |
| numerical_accuracy: no_expected_numbers | 9 |
| citation_accuracy: sources_present_without_expected_citations | 9 |

Ly do:

- DeepEval bi loi quota voi Gemini `gemini-2.5-flash`: `429 RESOURCE_EXHAUSTED` cho ca `faithfulness` va `answer_relevancy` tren 9/9 cases.
- Eval cases hien tai la auto-generated starter cases, chua co `expected_numbers`, `expected_source_keywords` hoac `expected_chunks`, nen finance metrics phai dung fallback.

### Ket qua tung case

| Case | Ticker | Faithfulness | Answer Relevancy | Numerical Accuracy | Citation Accuracy |
| ---- | ------ | ------------ | ---------------- | ------------------ | ----------------- |
| auto_001 | HPG | 0.812 | 0.857 | 1.0 | 1.0 |
| auto_002 | FPT | 0.833 | 0.857 | 1.0 | 1.0 |
| auto_003 | VCB | 0.797 | 0.857 | 1.0 | 1.0 |
| auto_004 | HPG | 0.912 | 0.667 | 1.0 | 1.0 |
| auto_005 | FPT | 0.948 | 1.0 | 1.0 | 1.0 |
| auto_006 | VCB | 0.958 | 1.0 | 1.0 | 1.0 |
| auto_007 | HPG | 0.92 | 0.909 | 1.0 | 1.0 |
| auto_008 | FPT | 0.935 | 1.0 | 1.0 | 1.0 |
| auto_009 | VCB | 0.921 | 0.8 | 1.0 | 1.0 |

### Nhan xet

Retrieval dang dat diem tuyet doi tren bo case hien tai (`Recall@5 = 1.0`, `MRR = 1.0`). Tuy nhien, do `eval_cases.json` hien tai chua co expected evidence/source/number reference, ket qua nay nen duoc xem la smoke test cho pipeline hon la ket luan chat luong RAG cuoi cung.

Generation va finance metrics da hien thi du tren Dashboard sau khi co fallback, nhung can bo sung eval cases co reference ro rang de cac diem `Numerical Accuracy` va `Citation Accuracy` co y nghia hon. Khi quota/API DeepEval on dinh, chay lai `python -m app.evaluate` de thay fallback bang diem LLM-as-a-Judge cho `Faithfulness` va `Answer Relevancy`.

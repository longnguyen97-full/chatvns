# Tổng kết project ChatVNS

## 1. Dataset, tech stack và bộ tiêu chí đánh giá

### Dataset

Dataset của project là dữ liệu tài chính/chứng khoán Việt Nam được crawl tự động theo từng mã cổ phiếu, hiện tập trung vào các mã như `HPG`, `FPT`, `VCB`.

Nguồn dữ liệu chính:

- Trang tổng quan cổ phiếu từ 24HMoney.
- Tin tức và sự kiện doanh nghiệp từ 24HMoney/Vietstock.
- Báo cáo phân tích dạng HTML/PDF.
- Báo cáo tài chính dạng PDF hoặc tài liệu liên quan.
- Ảnh chart TradingView.
- CSV market snapshot/timeseries.

Dữ liệu được lưu theo dạng raw artifacts trong `data/raw`, gồm:

- `html`
- `text`
- `csv`
- `pdf`
- `images`
- `metadata`

Sau đó pipeline xử lý thành:

- `data/processed/text`: text đã đọc/làm sạch.
- `data/processed/chunks`: chunks dùng cho retrieval.
- `data/processed/metadata`: metadata tổng hợp.
- Qdrant collection: vector index cho dense retrieval.

### Tech stack

Backend/RAG:

- Python 3.11.
- Streamlit cho UI chatbot và dashboard.
- Qdrant làm vector database.
- `sentence-transformers` cho embedding local.
- Hugging Face Inference API nếu bật embedding qua API.
- `rank-bm25` cho keyword/BM25 retrieval.
- Gemini làm LLM trả lời.
- DeepEval cho LLM-as-a-Judge evaluation.

Data processing:

- PyMuPDF để extract text từ PDF có text layer.
- Custom structure parser/chunker trong `app/processing`.

Retrieval hiện tại:

- Dense retrieval bằng BGE-M3 embedding.
- Keyword retrieval bằng BM25.
- Hybrid score để merge candidates.
- BGE-Reranker để rerank candidates trước khi đưa vào answer.
- Extractive context compression để rút gọn context trước khi gọi LLM.

Model chính:

- Embedding model mặc định: `BAAI/bge-m3`.
- Embedding dimension: `1024`.
- Reranker mặc định: `BAAI/bge-reranker-v2-m3`.
- LLM mặc định: Gemini, đọc từ `GEMINI_MODEL`.

Embedding có 2 chế độ:

- Local: tải/chạy `BAAI/bge-m3` qua `sentence-transformers`.
- API: đặt `EMBEDDING_PROVIDER=hf_api` và `HF_API_KEY` để gọi Hugging Face API, tránh tải model local lần đầu.

### Bộ tiêu chí đánh giá

Project hiện dùng một flow evaluation duy nhất:

```powershell
.\.venv\Scripts\python.exe -m app.evaluate
```

Bộ metrics đã rút gọn còn 6 metric chính:

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Retrieval | Recall@5 | Tỷ lệ expected evidence xuất hiện trong top-5 chunks |
| Retrieval | MRR | Thứ hạng của chunk liên quan đầu tiên |
| Generation | Faithfulness | Câu trả lời có được hỗ trợ bởi context hay không |
| Generation | Answer Relevancy | Câu trả lời có đúng trọng tâm câu hỏi hay không |
| Finance | Numerical Accuracy | Số liệu trong answer có khớp reference không |
| Finance | Citation Accuracy | Source/citation có khớp reference không |

Kết quả chạy gần nhất trong `data/evaluation/reports/evaluation_report_20260601T101548Z.json`:

| Metric | Kết quả |
| --- | --- |
| Recall@5 | 1.0 |
| MRR | 1.0 |
| Faithfulness | 0.893 |
| Answer Relevancy | 0.883 |
| Numerical Accuracy | 1.0 |
| Citation Accuracy | 1.0 |

Lưu ý: run này có fallback vì Gemini/DeepEval bị quota `429 RESOURCE_EXHAUSTED`, và eval cases hiện tại là auto-generated nên chưa có đủ `expected_numbers`, `expected_source_keywords`, `expected_chunks`. Vì vậy kết quả nên được xem là smoke test cho pipeline, chưa phải benchmark chất lượng cuối cùng.

## 2. Pipeline và code

### Pipeline tổng thể

Luồng xử lý chính:

```text
Collect raw data
-> Read/parse raw artifacts
-> Clean text
-> Parse structure blocks
-> Chunk theo token
-> Embed chunks bằng BGE-M3
-> Upsert vào Qdrant
-> Hybrid retrieval: dense + BM25
-> Rerank bằng BGE-Reranker
-> Extractive context compression
-> Prompt Gemini
-> Trả lời kèm sources
-> Log interaction + dashboard/evaluation
```

### Các module chính

Collector:

- `bot-collect-data/crawl_raw_data.py`: crawl HTML/text/CSV/PDF/image/metadata.

Pipeline:

- `app/pipeline.py`: điều phối collect, process, index, launch Streamlit.

Processing:

- `app/processing/documents.py`: load raw artifacts thành `RawDocument`.
- `app/processing/readers.py`: đọc CSV/PDF/text/image. PDF dùng PyMuPDF để extract text.
- `app/processing/structures.py`: suy đoán block/table/widget structure.
- `app/processing/chunking.py`: chunk theo token, giữ metadata.
- `app/processing/outputs.py`: ghi processed text/chunks/metadata.

Embedding/index:

- `app/embeddings.py`: embedding bằng local BGE-M3 hoặc Hugging Face API.
- `app/vector_store.py`: tạo/rebuild Qdrant collection, upsert vectors, dense retrieve.

Retrieval:

- `app/keyword_search.py`: BM25 keyword retrieval.
- `app/retriever.py`: hybrid dense + BM25, merge candidates.
- `app/reranker.py`: BGE-Reranker rerank candidates.

Answer generation:

- `app/context_compression.py`: extractive context compression.
- `app/rag.py`: build prompt, gọi Gemini, trả answer + sources.
- `app/prompts/rag_system.md`: system prompt yêu cầu chỉ trả lời dựa trên context.
- `app/market_snapshot.py`: ưu tiên market snapshot cho câu hỏi giá hiện tại/khối lượng.
- `app/technical_analysis.py`: bổ sung technical context nếu câu hỏi liên quan kỹ thuật.

UI/observability:

- `app/streamlit_app.py`: giao diện chatbot.
- `app/pages/1_Dashboard.py`: dashboard inventory, logs, evaluation.
- `app/observability.py`: log interactions.

Evaluation:

- `app/evaluate.py`: chạy retrieval/generation/finance/performance evaluation và xuất JSON/Markdown report.

### Các kỹ thuật xử lý code đặc biệt

1. Đọc PDF bằng PyMuPDF thay cho `pypdf`.

   File: `app/processing/readers.py`

   ```python
   def read_pdf_text(path: Path) -> str:
       try:
           import fitz

           document = fitz.open(str(path))
           try:
               text = "\n".join(page.get_text("text") or "" for page in document)
           finally:
               document.close()
       except Exception as exc:
           return f"[PDF artifact without extracted text] {path.name} | pymupdf_error={exc}"
       if text.strip():
           return text
       return f"[PDF artifact without extracted text] {path.name}"
   ```

   Ý nghĩa: PDF có text layer được extract trực tiếp bằng PyMuPDF. Project hiện không dùng OCR, nên PDF scan/ảnh không có text layer sẽ không trích được chữ.

2. Structure-aware token chunking.

   File: `app/processing/chunking.py`

   ```python
   def split_block_by_tokens(block: StructureBlock, max_tokens: int, overlap: int) -> list[StructureBlock]:
       tokens = tokenize(block.text)
       if len(tokens) <= max_tokens:
           return [block]

       blocks = []
       start = 0
       part_index = 0
       while start < len(tokens):
           end = min(start + max_tokens, len(tokens))
           text = detokenize(tokens[start:end])
           blocks.append(
               StructureBlock(
                   text=text,
                   structure_type=block.structure_type,
                   heading_path=block.heading_path,
                   metadata={**block.metadata, "split_part": part_index},
               )
           )
           if end >= len(tokens):
               break
           start = max(end - overlap, start + 1)
           part_index += 1
       return blocks
   ```

   Ý nghĩa: block dài được cắt theo token budget nhưng vẫn giữ `structure_type`, `heading_path` và metadata. Điều này tốt hơn cắt phẳng toàn bộ text.

3. Gom nhiều block nhỏ thành một chunk có metadata.

   File: `app/processing/chunking.py`

   ```python
   def flush() -> None:
       text = "\n\n".join(block.text for block in current_blocks)
       structure_types = [block.structure_type for block in current_blocks]
       heading_path = current_blocks[-1].heading_path
       metadata = {
           "structure_types": structure_types,
           "primary_structure_type": structure_types[0],
           "block_count": len(current_blocks),
           "block_metadata": [block.metadata for block in current_blocks],
       }
       chunks.append((text, structure_types[0], heading_path, token_count(text), metadata))
   ```

   Ý nghĩa: chunk không chỉ có text mà còn biết nó đến từ heading/table/widget/paragraph nào. Metadata này đi tiếp vào Qdrant payload.

4. BGE-M3 embedding local hoặc Hugging Face API.

   File: `app/embeddings.py`

   ```python
   def encode(self, texts: list[str]) -> list[list[float]]:
       if self.provider == "hf_api":
           return self._api_embedding(texts)
       if self._model is not None:
           vectors = self._model.encode(texts, normalize_embeddings=True)
           return [vector.tolist() for vector in vectors]
       return [self._hash_embedding(text) for text in texts]
   ```

   Ý nghĩa: mặc định có thể chạy local bằng `sentence-transformers`; nếu bật `EMBEDDING_PROVIDER=hf_api` thì gọi API để tránh tải BGE-M3 local lần đầu.

5. Validate và normalize embedding từ API.

   File: `app/embeddings.py`

   ```python
   vectors = self._coerce_api_vectors(payload, expected_count=len(texts))
   return [self._normalize_vector(vector) for vector in vectors]
   ```

   Ý nghĩa: API embedding có thể trả về vector hoặc token vectors. Code ép shape về đúng số lượng embeddings, fit dimension 1024 và normalize trước khi upsert Qdrant.

6. Hybrid retrieval dense + BM25 bằng RRF.

   File: `app/retriever.py`

   ```python
   dense_hits = dense_retrieve(query, top_k=dense_limit, ticker=ticker)
   keyword_hits = keyword_search(query, top_k=keyword_limit, ticker=ticker)

   for rank, hit in enumerate(dense_hits, start=1):
       merged[hit.id] = hit
       scores[hit.id] = scores.get(hit.id, 0.0) + dense_weight / (rrf_k + rank)

   for rank, hit in enumerate(keyword_hits, start=1):
       merged.setdefault(hit.id, hit)
       scores[hit.id] = scores.get(hit.id, 0.0) + keyword_weight / (rrf_k + rank)
   ```

   Ý nghĩa: dense retrieval bắt ngữ nghĩa, BM25 giữ keyword/số liệu/ticker. Hai nguồn được merge bằng Reciprocal Rank Fusion, tức ưu tiên tài liệu có rank cao ở từng nguồn thay vì phụ thuộc trực tiếp vào raw score khác thang đo.

7. BGE-Reranker sau hybrid retrieval.

   File: `app/reranker.py`

   ```python
   pairs = [(query, chunk.text) for chunk in chunks]
   raw_scores = self._model.predict(pairs, batch_size=RERANK_BATCH_SIZE)
   ranked = sorted(
       zip(chunks, [float(score) for score in raw_scores]),
       key=lambda item: item[1],
       reverse=True,
   )
   ```

   Ý nghĩa: hybrid retrieval lấy candidates rộng, còn BGE-Reranker sắp xếp lại candidates theo mức liên quan query-document chính xác hơn.

8. Extractive context compression.

   File: `app/context_compression.py`

   ```python
   ranked = sorted(
       enumerate(sentences),
       key=lambda item: sentence_score(item[1], query_tokens, chunk.ticker),
       reverse=True,
   )
   selected_indexes = sorted(
       index
       for index, sentence in ranked[:CONTEXT_MAX_SENTENCES_PER_CHUNK]
       if sentence_score(sentence, query_tokens, chunk.ticker) > 0
   )
   ```

   Ý nghĩa: trước khi gọi Gemini, mỗi chunk được rút còn các câu liên quan nhất với query/ticker/từ khóa tài chính/số liệu. Đây là compression kiểu extractive, an toàn hơn LLM summarization vì không tự viết lại số.

9. Build prompt chỉ từ context đã nén và metadata nguồn.

   File: `app/rag.py`

   ```python
   blocks.append(
       "\n".join(
           [
               f"[{index}] ticker={chunk.ticker} modality={chunk.modality} structure={chunk.structure_type} score={chunk.score:.4f}",
               f"source={chunk.source_path}",
               f"heading={' > '.join(chunk.heading_path)}",
               compress_chunk_text(question, chunk),
           ]
       )
   )
   ```

   Ý nghĩa: prompt vẫn có citation metadata (`source`, `heading`, `ticker`) nhưng phần text được nén để giảm nhiễu và giảm token.

10. Evaluation fallback khi DeepEval/quota/reference thiếu.

    File: `app/evaluate.py`

    ```python
    fallback_scores = {
        "faithfulness": round(context_grounding_score(str(result.get("answer", "")), retrieval_chunks), 3),
        "answer_relevancy": round(
            lexical_answer_relevancy_score(case["question"], str(result.get("answer", ""))),
            3,
        ),
    }
    ```

    Ý nghĩa: nếu DeepEval lỗi quota/API, dashboard vẫn có số theo heuristic fallback và ghi lý do trong `fallback_metrics`, tránh report bị trống.

### Các điểm đã cải thiện

- Đổi embedding sang BGE-M3.
- Có thể gọi embedding qua Hugging Face API để tránh tải model local.
- Thêm BGE-Reranker.
- Chuyển đọc PDF sang PyMuPDF.
- Thêm extractive context compression cho answer chính.
- Rút gọn evaluation thành một lệnh duy nhất.
- Dashboard hiển thị một bộ metrics thống nhất.

## 3. Prompt cho ChatGPT tạo hình kiến trúc tổng thể

Dùng prompt sau để tạo hình kiến trúc hệ thống:

```text
Create a clean architecture diagram for a Vietnamese stock RAG chatbot named ChatVNS.

Style:
- Professional software architecture diagram.
- White or light background.
- Clear boxes and arrows.
- Use Vietnamese labels.
- Avoid decorative illustrations.

Main flow:
1. Data Sources:
   - 24HMoney stock overview
   - Vietstock news/events
   - Analyst reports HTML/PDF
   - Financial statements PDF
   - TradingView chart screenshots
   - CSV market snapshots

2. Raw Data Storage:
   - data/raw/html
   - data/raw/text
   - data/raw/csv
   - data/raw/pdf
   - data/raw/images
   - data/raw/metadata

3. Processing Pipeline:
   - Read raw artifacts
   - PDF text extraction with PyMuPDF
   - Clean text
   - Structure parsing
   - Token-based chunking
   - Write processed chunks and metadata

4. Indexing:
   - BGE-M3 embedding, dimension 1024
   - Qdrant vector database
   - BM25 keyword index from processed chunks

5. Retrieval:
   - Dense retrieval from Qdrant
   - BM25 keyword retrieval
   - Hybrid candidate merge
   - BGE-Reranker reranking
   - Extractive context compression

6. Answer Generation:
   - Gemini LLM
   - RAG system prompt
   - Market snapshot guard for current price questions
   - Answer with citations/sources

7. UI and Monitoring:
   - Streamlit Chatbot
   - Dashboard
   - Interaction logs
   - Evaluation reports

8. Evaluation:
   - Recall@5
   - MRR
   - Faithfulness
   - Answer Relevancy
   - Numerical Accuracy
   - Citation Accuracy

Show arrows from data sources to raw storage, processing, indexing, retrieval, generation, UI, and evaluation.
Emphasize that the system is a finance-focused RAG pipeline with source-grounded answers.
```

## 4. Khó khăn

### 4.1. Dataset có vấn đề gì không? Đã xử lý như thế nào?

Có. Dataset có một số vấn đề đặc thù:

1. Dữ liệu đến từ nhiều nguồn và nhiều format.

   Cùng một mã cổ phiếu có HTML, PDF, CSV, ảnh chart, metadata. Cách xử lý là chuẩn hóa thành `RawDocument`, sau đó parse/chunk theo cùng một schema.

2. PDF có thể có text layer hoặc là scan/ảnh.

   Project hiện dùng PyMuPDF để extract text từ PDF có text layer. PDF scan/ảnh không có text layer sẽ không trích được chữ vì project đã bỏ OCR.

3. Ảnh chart chưa có text thật.

   Ảnh TradingView hiện vẫn được lưu để hiển thị/truy vết, nhưng chưa image embedding và không OCR ảnh rời. Với ảnh, pipeline hiện tạo placeholder text.

4. HTML web có nhiều nhiễu.

   Trang crawl có script, menu, layout, quảng cáo hoặc text không liên quan. Pipeline xử lý bằng clean text, structure parser, chunking theo block và metadata.

5. Dữ liệu tài chính có nhiều số liệu dễ nhầm.

   Project thêm market snapshot guard để câu hỏi giá hiện tại ưu tiên snapshot, tránh nhầm với giá mục tiêu trong báo cáo phân tích.

6. Eval cases hiện còn yếu.

   `eval_cases.json` hiện là auto-generated starter cases, thiếu `expected_numbers`, `expected_source_keywords`, `expected_chunks`. Vì vậy evaluation hiện là smoke test, chưa phải benchmark cuối cùng.

### 4.2. Còn những hạn chế nào?

Các hạn chế hiện tại:

1. PDF scan không có text layer chưa được đọc nội dung chữ.

   Vì project đã bỏ OCR, PyMuPDF chỉ extract được text layer có sẵn trong PDF.

2. Ảnh rời chưa image embedding.

   Chart screenshot vẫn chủ yếu để UI hiển thị, chưa đưa tín hiệu hình ảnh thật vào retrieval.

3. BGE-M3 và BGE-Reranker có thể cần tải model local.

   Có thể dùng `EMBEDDING_PROVIDER=hf_api` cho embedding, nhưng reranker hiện vẫn chạy local qua `CrossEncoder`.

4. Context compression là extractive, chưa semantic compression.

   Cách hiện tại an toàn vì không tự viết lại số liệu, nhưng có thể bỏ sót câu quan trọng nếu câu không overlap nhiều với query.

5. Hallucination protection chưa hoàn chỉnh.

   Project đã có prompt guard, source grounding, market snapshot guard, rerank, context compression và evaluation faithfulness. Tuy nhiên chưa có runtime validator chặt để kiểm tra từng số liệu/claim trong answer trước khi trả về.

6. Evaluation còn phụ thuộc quota DeepEval/Gemini.

   Khi quota lỗi, report dùng fallback cục bộ. Điều này giúp dashboard không trống, nhưng điểm fallback không thay thế hoàn toàn LLM-as-a-Judge.

7. Cần rebuild index khi đổi embedding model/dimension.

   Vì BGE-M3 dùng vector dimension 1024, Qdrant collection cũ 384 chiều phải được rebuild bằng:

   ```powershell
   .\.venv\Scripts\python.exe -m app.pipeline index
   ```

8. Dataset hiện chưa đủ reference ground truth.

   Để đánh giá nghiêm túc hơn, cần bổ sung eval cases có:

   - `expected_chunks`
   - `expected_numbers`
   - `expected_source_keywords`
   - `expected_output`

## Kết luận ngắn

ChatVNS hiện là một hệ thống RAG cho chứng khoán Việt Nam với pipeline khá đầy đủ: crawl dữ liệu tài chính, xử lý đa định dạng, đọc PDF bằng PyMuPDF, chunking, BGE-M3 embedding, Qdrant, hybrid retrieval, BGE-Reranker, context compression, Gemini answer và dashboard/evaluation.

Điểm mạnh hiện tại là kiến trúc có đủ các lớp chính của một RAG thực tế. Điểm cần cải thiện tiếp theo là ground-truth eval cases, image understanding cho ảnh chart/PDF scan, và hallucination validator ở runtime.

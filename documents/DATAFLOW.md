# Data Flow

Tài liệu này mô tả luồng đi của dữ liệu trong project, từ lúc bot crawl dữ liệu từ website cho đến khi dữ liệu được xử lý, chunking, embedding và đưa vào vector database.

## 1. Luồng Tổng Quan

```text
Website nguồn
  |
  v
Bot crawl raw data
  |
  +--> data/raw/html      : HTML page gốc tải về
  +--> data/raw/text      : text dump bóc ra từ HTML
  +--> data/raw/csv       : bảng CSV tách từ HTML hoặc timeseries tổng quan
  +--> data/raw/pdf       : PDF tải theo link follow-up
  +--> data/raw/images    : screenshot chart TradingView
  +--> data/raw/metadata  : metadata kỹ thuật cho từng artifact
  |
  v
Processing
  |
  +--> đọc raw artifact
  +--> chuẩn hóa text
  +--> parse cấu trúc (heading / table / widget / paragraph)
  +--> chunk theo token
  |
  v
data/processed
  |
  +--> text/{ticker}         : text sạch sau xử lý
  +--> chunks/{ticker}       : chunks.jsonl cho retrieval
  +--> metadata/manifest.json: tổng kết processed run
  +--> q&a.json              : câu hỏi sidebar được sync từ documents/Q&A.md
  |
  v
Embeddings + Qdrant
  |
  +--> mỗi chunk text được encode thành vector
  +--> upsert vào collection Qdrant
  +--> payload giữ text + metadata để truy vết ngược về source
```

## 2. Dữ Liệu Đi Xuống Từ Website Như Thế Nào

Crawler chính nằm ở [bot-collect-data/crawl_raw_data.py](/d:/LAB/May%20Hoc%20Nang%20Cao/bot-collect-data/crawl_raw_data.py).

Các nguồn hiện tại:

- `24hmoney stock page`: trang tổng quan cổ phiếu.
- `24hmoney analysis listing`: trang liệt kê báo cáo phân tích.
- `24hmoney ticker news`: trang tin tức theo mã, nếu bật `--include-news`.
- `Vietstock financial documents`: trang tài liệu tài chính.
- `Vietstock news/events`: tin tức và sự kiện doanh nghiệp.
- `TradingView`: chụp screenshot biểu đồ, nếu bật `--include-charts`.

Khi crawler gọi `build_targets()` và `crawl_targets()`, mỗi URL sẽ được tải về và lưu thành artifact trong `data/raw`.

## 3. Trong `data/raw` Có Gì Và Sinh Ra Từ Đâu

### 3.1 `data/raw/html`

Đây là file HTML gốc tải trực tiếp từ website.

Ví dụ:

```text
data/raw/html/FPT/20260525T032247Z__24hmoney__ticker_news.html
data/raw/html/FPT/20260525T032245Z__vietstock__ticker_news_events.html
```

Ý nghĩa:

- giữ bản gốc gần như nguyên trạng từ website
- phục vụ debug khi cần xem bot thực sự crawl được gì
- là nguồn để bóc thêm text và bảng

### 3.2 `data/raw/text`

Đây không phải file tải trực tiếp từ website, mà là text dump được crawler bóc ra từ HTML bằng `extract_text_from_html()`.

Ví dụ:

```text
data/raw/text/FPT/20260525T021741Z__24hmoney__stock_overview.txt
```

Ý nghĩa:

- dùng như bản text gần-raw để processing đọc lại
- tránh phải parse HTML lại nhiều lần ở bước sau
- với file `.html`, processing thường ưu tiên dùng `.txt` dump tương ứng thay vì đọc HTML lần nữa

### 3.3 `data/raw/csv`

CSV trong raw đến từ 2 nguồn:

- bảng HTML được tách ra bằng `extract_tables_from_html()` rồi ghi bằng `write_table_csvs()`
- file `stock_overview_timeseries.csv` được crawler tự dựng từ snapshot 24hmoney qua `append_24hmoney_overview_timeseries_csv()`

Nghĩa là:

- có CSV “bóc từ bảng HTML”
- có CSV “timeseries tổng quan” do bot tự chuẩn hóa từ dữ liệu trên page

Sau lần cải thiện gần đây, crawler đã lọc bớt các bảng rỗng hoặc bảng layout bằng `is_meaningful_table()` trước khi ghi CSV.

### 3.4 `data/raw/pdf`

PDF được tải theo link follow-up, không phải lúc nào cũng nằm ngay ở page đầu tiên.

Ví dụ:

- từ trang báo cáo 24hmoney, bot vào detail page rồi tìm `url_file`
- từ trang tài liệu Vietstock, bot quét các link tài liệu như `pdf/xls/xlsx/doc/docx`

### 3.5 `data/raw/images`

Ảnh hiện tại chủ yếu là screenshot chart TradingView do Playwright chụp.

Ví dụ:

```text
data/raw/images/FPT/20260525T....__tradingview__chart_screenshot.png
```

### 3.6 `data/raw/metadata`

Đây là metadata kỹ thuật do pipeline tự sinh cho từng artifact raw, không phải dữ liệu tải nguyên bản từ website.

Ví dụ metadata thường có:

- `source`
- `ticker`
- `url`
- `crawl_method`
- `artifact_path`
- `text_path`
- `csv_paths`
- `content_type`
- `crawled_at_utc`
- `text_length`
- `table_candidates`
- `tables_saved`
- `tables_skipped`

Nó giúp trả lời các câu hỏi như:

- file này đến từ URL nào
- bot crawl lúc nào
- page này có bao nhiêu bảng và lưu được bao nhiêu CSV
- HTML này có text dump nào đi kèm

## 4. Từ `data/raw` Sang `data/processed` Diễn Ra Ra Sao

Bước này được chạy bởi [app/pipeline.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/pipeline.py) khi dùng lệnh:

```bash
python -m app.pipeline index
```

hoặc:

```bash
python -m app.pipeline all --tickers tickers --include-news --include-charts
```

Trong code, `run_index()` gọi:

1. `export_suggested_questions_json()`
2. `process_raw_data_with_summary()`
3. `index_chunks()`

Phần xử lý chính nằm trong package [app/processing](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing).

## 5. Processing Đọc Và Chuyển Đổi Dữ Liệu Như Thế Nào

### 5.1 Chọn các raw artifact để xử lý

Hàm `iter_raw_documents()` trong [app/processing/documents.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing/documents.py) quét toàn bộ `data/raw` rồi tạo danh sách `RawDocument`.

Các điểm quan trọng:

- bỏ qua thư mục `metadata`
- chỉ nhận các loại file được hỗ trợ như `.txt`, `.csv`, `.pdf`, ảnh
- nếu một file `.html` đã có text dump tương ứng trong `data/raw/text`, processing sẽ bỏ qua file HTML đó để tránh xử lý trùng

Vì vậy, với nhiều page HTML, dữ liệu đi vào processing thực tế là:

```text
website HTML
-> data/raw/html/*.html
-> crawler bóc text
-> data/raw/text/*.txt
-> processing đọc file .txt đó
```

### 5.2 Đọc nội dung theo từng loại file

Hàm `read_raw_file()` trong [app/processing/readers.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing/readers.py) xử lý theo loại artifact:

- `.csv` -> đọc rows rồi chuyển sang table text
- `.pdf` -> dùng PyMuPDF extract text từ text layer có sẵn
- `image` -> tạo placeholder text kiểu `[Image artifact] ...`
- các file text còn lại -> đọc UTF-8 trực tiếp

Sau đó text được:

- `normalize_text()`
- `clean_document_text()`

để bỏ bớt nhiễu, chuẩn hóa khoảng trắng và làm sạch trước khi chunking.

### 5.3 Gắn metadata raw vào document

Mỗi `RawDocument` còn được nạp thêm metadata từ `data/raw/metadata/...` bằng `load_metadata_for_artifact()`.

Điểm này quan trọng vì về sau chunk sẽ kế thừa lại metadata như:

- `url`
- `artifact_path`
- `source`
- `crawl_method`

để chatbot có thể hiển thị nguồn và truy ngược về raw source.

## 6. Từ Document Text Sang Structured Blocks

Sau khi có `RawDocument`, pipeline gọi `parse_document_structures()` trong [app/processing/structures.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing/structures.py).

Mục tiêu của bước này là biến một document dài thành các block có ý nghĩa hơn:

- `heading`
- `table`
- `widget`
- `paragraph`

Tùy loại file:

- `html` -> parse theo tag HTML, nhận diện heading, paragraph, table
- `csv` -> coi cả file là một `table`
- `image` -> tạo `widget block`
- text thường / pdf text -> suy đoán block bằng heuristic trên từng dòng

Nghĩa là trước khi chunk, dữ liệu đã được “có cấu trúc sơ bộ”, chứ không cắt thẳng từ một chuỗi text phẳng.

## 7. Từ Structured Blocks Sang Chunks

Hàm `chunk_documents()` trong [app/processing/chunking.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing/chunking.py) làm việc này.

Luồng nội bộ:

```text
RawDocument
  -> parse_document_structures()
  -> list[StructureBlock]
  -> chunk_blocks()
  -> list[Chunk]
```

Nguyên tắc:

- chunk theo token
- có `chunk_size` và `overlap`
- nếu block quá dài thì `split_block_by_tokens()`
- giữ lại `heading_path`, `structure_type`, `token_count`

Mỗi chunk sinh ra có các trường chính:

```json
{
  "id": "stable_chunk_id",
  "text": "noi dung chunk",
  "ticker": "FPT",
  "modality": "text|table|pdf|image",
  "source_path": "data/raw/...",
  "chunk_index": 0,
  "structure_type": "heading|table|widget|paragraph",
  "heading_path": ["..."],
  "token_count": 123,
  "metadata": {
    "url": "https://...",
    "artifact_path": "data/raw/...",
    "document_id": "...",
    "parser": "structure-aware-token-chunker"
  }
}
```

## 8. `data/processed` Chứa Gì Sau Bước Processing

`write_processed_outputs()` trong [app/processing/outputs.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/processing/outputs.py) ghi kết quả ra `data/processed`.

### 8.1 `data/processed/text/{ticker}`

Đây là text sau xử lý, sạch hơn raw text.

Nó khác `data/raw/text` ở chỗ:

- `raw/text` là text dump gần nguyên trạng do crawler bóc ra
- `processed/text` là text đã normalize và clean để dùng downstream

### 8.2 `data/processed/chunks/{ticker}/chunks.jsonl`

Đây là artifact quan trọng nhất cho retrieval.

Mỗi dòng là một `Chunk` hoàn chỉnh, đã có:

- text
- ticker
- modality
- source path
- structure type
- heading path
- token count
- metadata kế thừa từ raw

### 8.3 `data/processed/metadata/manifest.json`

Đây là metadata tổng hợp của cả processed run, ví dụ:

- `document_count`
- `chunk_count`
- `tickers`
- chiến lược chunking

Lưu ý: file này là báo cáo tổng kết, không phải nguồn để tạo chunks.

### 8.4 `data/processed/q&a.json`

File này không đi vào vector DB.

Nó được sync từ [documents/Q&A.md](/d:/LAB/May%20Hoc%20Nang%20Cao/documents/Q&A.md) để Streamlit sidebar có danh sách câu hỏi gợi ý.

## 9. Dữ Liệu Vào Vector DB Như Thế Nào

Bước này nằm ở [app/vector_store.py](/d:/LAB/May%20Hoc%20Nang%20Cao/app/vector_store.py).

Hàm `index_chunks()` nhận `list[Chunk]` rồi làm:

```text
chunks
  -> lấy text của từng chunk
  -> embedding_model.encode(...)
  -> tạo PointStruct cho từng chunk
  -> upsert vào Qdrant
```

Mỗi point trong Qdrant gồm 2 phần:

1. `vector`
   là embedding của `chunk.text`

2. `payload`
   là metadata đi kèm để truy xuất và hiển thị

Payload hiện tại gồm:

- `text`
- `ticker`
- `modality`
- `source_path`
- `chunk_index`
- `structure_type`
- `heading_path`
- `token_count`
- `metadata`

Nghĩa là vector DB không chỉ giữ vector, mà còn giữ đủ context để:

- hiển thị nguồn trong chatbot
- lọc theo ticker
- biết chunk đến từ PDF, table hay text
- truy ngược về file raw tương ứng

## 10. Sơ Đồ Cuối Cùng Theo Từng Loại Dữ Liệu

### 10.1 HTML page

```text
Website HTML
-> data/raw/html/*.html
-> crawler bóc text -> data/raw/text/*.txt
-> crawler bóc table -> data/raw/csv/*.csv
-> crawler sinh metadata -> data/raw/metadata/*.json
-> processing đọc .txt / .csv
-> structured blocks
-> chunks.jsonl
-> embeddings
-> Qdrant
```

### 10.2 PDF

```text
Website detail page
-> follow-up PDF link
-> data/raw/pdf/*.pdf
-> metadata raw
-> processing đọc PDF text bằng PyMuPDF
-> clean text
-> chunks.jsonl
-> embeddings
-> Qdrant
```

### 10.3 Image chart

```text
TradingView page
-> screenshot PNG
-> data/raw/images/*.png
-> metadata raw
-> processing tạo placeholder text cho image artifact
-> widget chunk
-> embeddings/payload
-> Qdrant
```

Lưu ý: project hiện không dùng OCR. PDF scan/ảnh không có text layer và ảnh rời trong `data/raw/images` vẫn mới đi theo placeholder text, chưa có image embedding thực sự.

## 11. Kết Luận Ngắn

Nếu tóm lại theo đúng flow của project hiện tại thì:

1. Bot crawl dữ liệu web và lưu thành nhiều artifact gốc trong `data/raw`.
2. Từ raw artifact, pipeline đọc lại nội dung, làm sạch text và gắn metadata kỹ thuật.
3. Dữ liệu được parse thành block có cấu trúc rồi chunk theo token.
4. Chunks được ghi ra `data/processed/chunks/*.jsonl`.
5. Mỗi chunk text được embedding và upsert vào Qdrant cùng payload metadata.
6. Khi chatbot hỏi đáp, retrieval lấy lại các chunk phù hợp từ Qdrant để làm context cho generation.

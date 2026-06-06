# Collect Raw Data

Module `bot-collect-data` chỉ chịu trách nhiệm fetch, download, snapshot và lưu raw data.

Module này không làm NLP preprocessing, không chunking, không embedding. Các bước đó nằm ở `app/processing.py` và pipeline index.

## Data Sources

Tickers mặc định:

```python
tickers = ["HPG", "VCB", "FPT"]
```

### 24HMoney Stock Page

Link chính:

```text
https://24hmoney.vn/stock/{ticker}
```

Data:

- Stock overview HTML/text.
- Snapshot các bảng/chỉ số tìm được trong HTML.
- CSV `stock_overview_timeseries.csv` nếu extract được dữ liệu dạng bảng.
- Link báo cáo phân tích được lần theo từ chính trang stock theo cấu trúc HTML.

### 24HMoney Analysis Report Listing

Link:

```text
https://24hmoney.vn/bao-cao-phan-tich?k={ticker}
```

Data:

- Listing báo cáo phân tích.
- Follow-up detail page theo link report trong HTML.
- PDF báo cáo nếu detail page có `url_file`.

Lưu ý: crawler hiện không dùng trực tiếp các link sau:

```text
https://24hmoney.vn/stock/{ticker}/technical-analysis
https://24hmoney.vn/stock/{ticker}/financial-indicators
```

### 24HMoney News

Link:

```text
https://24hmoney.vn/stock/{ticker}/news
```

Data:

- News HTML/text liên quan ticker.

Nguồn này chỉ crawl khi thêm `--include-news`.

### 24HMoney World

Link:

```text
https://24hmoney.vn/world
```

Data:

- Snapshot HTML/text thị trường thế giới.
- Lưu dưới scope `market`, không gắn với ticker cụ thể.

### Vietstock Financial Documents

Link:

```text
https://finance.vietstock.vn/{ticker}/tai-tai-lieu.htm?doctype=1
```

Data:

- HTML snapshot trang tài liệu.
- Link tài liệu gốc.
- PDF/ZIP/DOC/DOCX/XLS/XLSX nếu tìm thấy trong HTML.

### Vietstock News & Events

Link:

```text
https://finance.vietstock.vn/{ticker}/tin-tuc-su-kien.htm
```

Data:

- HTML/text tin tức và sự kiện doanh nghiệp theo ticker.

### TradingView Chart Screenshot

Link:

```text
https://vn.tradingview.com/chart/?symbol=HOSE%3A{ticker}
```

Data:

- Screenshot chart PNG.

Nguồn này chỉ chạy khi thêm `--include-charts`.

## HTML Structures

Folder `bot-collect-data/html-structures/` chứa HTML mẫu để tham chiếu cấu trúc khi crawl.

Crawler nên ưu tiên:

- Vào `https://24hmoney.vn/stock/{ticker}`.
- Tìm link báo cáo phân tích từ HTML của trang này.
- Vào `https://24hmoney.vn/bao-cao-phan-tich?k={ticker}`.
- Tìm thêm link báo cáo phân tích từ trang listing.
- Vào detail page của báo cáo.
- Tải PDF nếu detail page có `url_file`.
- Vào `https://finance.vietstock.vn/{ticker}/tai-tai-lieu.htm?doctype=1`.
- Tìm và tải tài liệu báo cáo tài chính theo link/file trong HTML.
- Vào `https://finance.vietstock.vn/{ticker}/tin-tuc-su-kien.htm`.
- Vào `https://24hmoney.vn/world` một lần mỗi crawl run.

## Tech Stack

- Python >= 3.12
- requests
- Playwright
- Celery Beat
- Redis
- Local filesystem: `data/raw`

## Pipeline

```text
Scheduler -> Collector -> Storage (data/raw)
```

Collector làm các việc:

- Crawl HTML pages.
- Download raw PDF/ZIP/DOC/DOCX/XLS/XLSX nếu có link.
- Capture screenshot nếu bật chart crawl.
- Lưu raw artifact.
- Lưu metadata traceability.
- Ghi logs.

## Folder Structure

```text
data/
  raw/
    html/{ticker}/
    csv/{ticker}/
    text/{ticker}/
    pdf/{ticker}/
    images/{ticker}/
    metadata/{ticker}/
  logs/
    crawl_logs/
    error_logs/
    scheduler_logs/
```

Tên file có dạng:

```text
{timestamp}__{source}__{name}.{ext}
```

Ví dụ:

```text
data/raw/html/HPG/20260523T010000Z__24hmoney__stock_overview.html
data/raw/pdf/HPG/20260523T010100Z__vietstock__financial_document_01.pdf
data/raw/images/HPG/20260523T010200Z__tradingview__chart_screenshot.png
data/raw/metadata/HPG/20260523T010000Z__24hmoney__stock_overview.metadata.json
```

## Output

Module tạo raw artifacts:

- Raw HTML
- Raw CSV extracted từ HTML tables
- Plain text dump từ HTML
- PDF/ZIP/DOC/DOCX/XLS/XLSX reports
- Chart screenshots
- Metadata JSON
- Crawl logs

Metadata gồm:

- `source`
- `category`
- `ticker`
- `name`
- `url`
- `crawl_method`
- `crawled_at_utc`
- `artifact_path`
- `text_path`
- `csv_paths`
- `content_type`

## Bot Implementation

Bot chính:

```text
bot-collect-data/crawl_raw_data.py
```

Bot hiện tại:

- Crawl 24HMoney stock overview.
- Crawl 24HMoney analysis report listing.
- Follow-up report detail pages từ link tìm được trên stock overview và analysis report listing.
- Tải PDF từ report detail nếu HTML có `url_file`.
- Crawl Vietstock financial document page và tải file tài liệu nếu HTML có link.
- Crawl Vietstock ticker news/events.
- Crawl 24HMoney world market page.
- Crawl 24HMoney ticker news khi bật `--include-news`.
- Chụp TradingView chart khi bật `--include-charts`.
- Lưu raw HTML/text/CSV/PDF/image/metadata theo folder structure ở trên.

## Cách Chạy

Cài dependency:

```bash
pip install -r requirements.txt
playwright install chromium
```

Chạy với ticker mặc định:

```bash
python bot-collect-data/crawl_raw_data.py
```

Chạy với ticker cụ thể:

```bash
python bot-collect-data/crawl_raw_data.py --tickers tickers
```

Giới hạn số report analysis follow-up mỗi ticker:

```bash
python bot-collect-data/crawl_raw_data.py --tickers tickers --max-reports 3
```

Chạy thêm ticker news:

```bash
python bot-collect-data/crawl_raw_data.py --tickers tickers --include-news
```

Chụp thêm chart TradingView:

```bash
python bot-collect-data/crawl_raw_data.py --tickers tickers --include-charts
```

Tùy chỉnh timeout/delay:

```bash
python bot-collect-data/crawl_raw_data.py --tickers tickers --include-news --include-charts --delay-seconds 2 --timeout 45
```

## Scheduler

Chạy scheduler bằng Celery Beat + Redis:

```bash
redis-server
cd bot-collect-data
celery -A celery_app worker --loglevel=info
celery -A celery_app beat --loglevel=info
```

Gọi task crawl theo ticker:

```bash
cd bot-collect-data
celery -A celery_app call tasks.crawl_tickers --args='[["HPG", "FPT", "VNM", "VCB", "MBB", "VPB", "HDB", "DXG", "GEE", "GEX", "GEL", "VIX", "VIC", "VHM", "VPL", "VRE", "VJC", "GAS", "PLX", "BSR"], true, false, 3, 1.5, 30]'
```

Thứ tự args của `tasks.crawl_tickers`:

```text
tickers, include_news, include_charts, max_reports, delay_seconds, timeout
```

## Cleanup Empty Data

Kiểm tra file rỗng trong `data/raw`:

```bash
python bot-collect-data/cleanup_empty_data.py
```

Xóa thật file rỗng và folder rỗng:

```bash
python bot-collect-data/cleanup_empty_data.py --apply --remove-empty-dirs
```

Xóa thêm metadata mồ côi, tức `.metadata.json` trỏ tới artifact không còn tồn tại:

```bash
python bot-collect-data/cleanup_empty_data.py --apply --remove-empty-dirs --remove-orphan-metadata
```

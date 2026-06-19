## 1. Nhóm Tính Năng Dữ Liệu & Phân Tích Thị Trường
- Cập nhật dữ liệu thời gian thực (Real-time data): Chatbot phải kết nối trực tiếp với các API chứng khoán (như FireAnt hoặc TradingView) để truy xuất giá, khối lượng, và bảng điện ngay lập tức.
- Phân tích kỹ thuật (Technical Analysis): Hỗ trợ trả lời các câu hỏi về chỉ báo như RSI, MACD, Bollinger Bands, đường MA (Moving Average) và phân tích biểu đồ.
- Phân tích cơ bản (Fundamental Analysis): Cung cấp dữ liệu doanh nghiệp, báo cáo tài chính (Doanh thu, Lợi nhuận, EPS, P/E, P/B) và tin tức vĩ mô liên quan.
- Phân tích tâm lý thị trường (Sentiment Analysis): Quét và tóm tắt tin tức, bài báo, hoặc các cuộc thảo luận trên diễn đàn mạng xã hội để đánh giá tâm lý nhà đầu tư đối với một mã cổ phiếu.

## 2. Nhóm Tính Năng Trải Nghiệm & Cá Nhân Hóa
- Hiểu ngôn ngữ tự nhiên (NLP) chuyên sâu: Người dùng có thể hỏi bằng giọng văn thông thường, ví dụ: "Mã VCB hôm nay tăng hay giảm?", "Top 3 cổ phiếu ngành thép có chỉ số tốt nhất là gì?".Cảnh báo thông minh (Smart Alerts): Cho phép người dùng thiết lập lệnh nhắc nhở thông qua khung chat. Ví dụ: "Nhắc tôi khi mã HPG vượt đỉnh cũ" hoặc "Cảnh báo nếu giá giảm quá 5%".
- Tư vấn danh mục đầu tư (Portfolio Advisory): Phân tích rủi ro danh mục hiện tại và đưa ra các gợi ý tái cơ cấu (tỉ trọng phân bổ, mức độ đa dạng hóa) dựa trên khẩu vị rủi ro của người dùng.
- Hỗ trợ nghiệp vụ môi giới (eKYC): Tích hợp quy trình tự động hỗ trợ người dùng mở tài khoản, nạp/rút tiền, tra cứu phí giao dịch hay tỷ lệ ký quỹ (margin).

## 3. Nhóm Tính Năng Giao Dịch & Quản Trị Rủi Ro
- Giao dịch tự động hoặc bán tự động (Auto-trading): Dựa trên các tín hiệu AI đưa ra hoặc chiến lược lập trình sẵn, chatbot có thể hỗ trợ người dùng đặt lệnh (Mua/Bán/Stop-Loss/Take-Profit) ngay trong giao diện chat thông qua API của các công ty chứng khoán.
- Backtest chiến lược (Kiểm thử lại): Cho phép hỏi AI để chạy thử một chiến lược đầu tư trong quá khứ nhằm đánh giá tỷ lệ thành công.

## 4. Nhóm Tính Năng Bảo Mật & Tuân Thủ (Compliance)
- Xử lý sai số (Hallucination Control): Các LLM thông thường (như ChatGPT, Gemini) rất dễ bịa số liệu tài chính. Chatbot AI chuyên ngành bắt buộc phải có hệ thống kiểm tra chéo, trích xuất nguồn tin đáng tin cậy để tránh đưa ra lời khuyên sai lầm.
- Bảo mật dữ liệu: Mã hóa cấp ngân hàng đối với các thông tin tài khoản, danh mục đầu tư và dữ liệu cá nhân của người dùng.
- Tuyên bố miễn trừ trách nhiệm (Disclaimer): Mọi phân tích hoặc gợi ý của AI đều phải kèm theo thông báo rõ ràng rằng đây không phải là lời khuyên đầu tư tài chính cuối cùng, người dùng phải tự chịu trách nhiệm với vốn của mình.

## 5. Đối chiếu hiện trạng ChatVNS

Cập nhật ngày 19/06/2026. Trạng thái "Một phần" nghĩa là backend đã có năng lực liên quan nhưng chưa đáp ứng đầy đủ mô tả sản phẩm.

| Tính năng mong muốn | Trạng thái | ChatVNS hiện có | Khoảng trống chính |
| --- | --- | --- | --- |
| Dữ liệu realtime | Một phần | Crawler theo lịch, market snapshot timeseries, guard cho câu hỏi giá hiện tại | Chưa kết nối API streaming/realtime; dữ liệu có thể trễ |
| Phân tích kỹ thuật | Một phần | SMA, RSI, MACD, Bollinger nếu có OHLCV; hiển thị chart artifact | Phụ thuộc file OHLCV; chưa nhận diện mô hình biểu đồ |
| Phân tích cơ bản | Đã có | RAG trên báo cáo tài chính, báo cáo phân tích, tin doanh nghiệp | Chỉ trả lời được chỉ số có trong nguồn đã crawl |
| Sentiment analysis | Chưa có | Có retrieval/tóm tắt tin và intermarket context | Chưa có sentiment model, score, trend theo thời gian hay social feed |
| NLP hỏi đáp tự nhiên | Đã có | Hybrid retrieval, reranker, context compression, Gemini generation | Cần bộ benchmark tiếng Việt tài chính tốt hơn |
| Smart alerts | Chưa có | Có scheduler cho crawl/index | Chưa có rule store, user subscription và notification channel |
| Portfolio advisory | Chưa có | Có thể so sánh nhiều ticker từ context | Chưa có portfolio model, risk profile, allocation optimizer |
| eKYC/nghiệp vụ môi giới | Chưa có | Không | Cần tích hợp hệ thống công ty chứng khoán và compliance riêng |
| Auto-trading | Chưa có | Không | Cần broker API, authentication, confirmation và risk controls |
| Backtest | Chưa có | Có các hàm chỉ báo cơ bản | Chưa có strategy engine, historical price store và performance report |
| Hallucination control | Đã có, cần tăng cường | Citation, source grounding, market snapshot guard, faithfulness/numerical/citation evaluation | Chưa có runtime claim-by-claim validator |
| Bảo mật dữ liệu cá nhân | Chưa áp dụng | Project chưa lưu tài khoản hay danh mục người dùng | Cần auth, encryption, secrets management và audit log khi thêm user data |
| Disclaimer | Đã có | Hiển thị cảnh báo trên Chatbot và Dashboard | Nên review pháp lý trước khi public |

### Bổ sung trong lần cập nhật này

- Giao diện mascot theo trạng thái: chào mừng, chat, processing, insight và trust/source.
- Hiển thị độ mới của market snapshot, tránh gọi dữ liệu có độ trễ là realtime.
- Disclaimer cố định về rủi ro đầu tư và độ trễ dữ liệu.
- Khu vực nguồn được nhấn mạnh rõ hơn trong UI.

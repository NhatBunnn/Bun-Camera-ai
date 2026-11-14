# Bun Camera AI

> Một trợ lý AI thử nghiệm tại nhà, có thể trò chuyện bằng giọng nói và
> sử dụng hình ảnh từ camera để hiểu môi trường xung quanh.

**Trạng thái:** Ý tưởng / chuẩn bị triển khai\
**Mục tiêu:** Làm một prototype nhỏ để gia đình trải nghiệm, ưu tiên đơn
giản và chi phí thấp.

---

## 1. Giới thiệu

Bun Camera AI kết hợp camera IP, microphone, loa và Gemini API để tạo
một trợ lý AI có thể:

- Trò chuyện bằng tiếng Việt.
- Nghe câu hỏi qua microphone.
- Chụp ảnh từ camera khi câu hỏi cần thông tin hình ảnh.
- Phân tích ảnh và trả lời những gì camera đang nhìn thấy.
- Đọc câu trả lời thành tiếng qua loa.
- Duy trì ngữ cảnh hội thoại trong phiên trò chuyện.

Ở phiên bản đầu tiên, hệ thống **không phân tích video liên tục**.
Camera chỉ được chụp khi người dùng hỏi hoặc khi ứng dụng cần một hình
ảnh mới. Cách này giúp giảm số lần gọi API và phù hợp với mục đích thử
nghiệm.

## 2. Workflow tổng thể

```mermaid
flowchart TD
    A[Người dùng nói chuyện] --> B[Microphone]
    B --> C[Speech-to-Text]
    C --> D[Nhận nội dung câu hỏi]
    D --> E{Có cần hình ảnh từ camera?}
    E -- Không --> G[Chuẩn bị prompt và lịch sử hội thoại]
    E -- Có --> F[Chụp frame mới từ camera]
    F --> G
    G --> H[Gemini API]
    H --> I[Câu trả lời dạng văn bản]
    I --> J[Text-to-Speech]
    J --> K[Loa phát câu trả lời]
    K --> L[Cập nhật lịch sử hội thoại]
```

### Ví dụ tương tác

**Người dùng:** "Mày thấy cái gì đây?"

1.  Microphone thu giọng nói.
2.  Speech-to-Text chuyển giọng nói thành văn bản.
3.  Backend nhận ra câu hỏi cần thông tin hình ảnh.
4.  Camera chụp một frame mới.
5.  Backend gửi câu hỏi, ảnh và ngữ cảnh hội thoại đến Gemini.
6.  Gemini mô tả hình ảnh và trả lời.
7.  Text-to-Speech chuyển câu trả lời thành âm thanh.
8.  Loa phát câu trả lời.

**Người dùng:** "Thế cái cốc màu gì?"

Nếu hình ảnh trước đó vẫn còn phù hợp, backend có thể tiếp tục dùng ngữ
cảnh ảnh trong phiên hội thoại. Nếu camera đã thay đổi góc nhìn hoặc đã
lâu, backend nên chụp ảnh mới để tránh trả lời dựa trên hình ảnh cũ.

## 3. Kiến trúc hệ thống

```text
bun-camera-ai/
├── camera/
│   ├── camera.py          # Kết nối camera và đọc luồng RTSP
│   └── snapshot.py        # Chụp và lưu frame khi được yêu cầu
│
├── ai/
│   ├── gemini.py          # Gửi prompt, ảnh và nhận phản hồi từ Gemini
│   └── prompts.py         # System instruction và prompt mẫu
│
├── audio/
│   ├── speech_to_text.py  # Chuyển giọng nói thành văn bản
│   └── text_to_speech.py  # Chuyển văn bản thành giọng nói
│
├── conversation/
│   └── memory.py          # Quản lý lịch sử hội thoại
│
├── config/
│   └── settings.py        # Đọc cấu hình và biến môi trường
│
├── data/
│   └── .gitkeep           # Dữ liệu thử nghiệm (không commit ảnh riêng tư)
│
├── .env.example           # Mẫu biến môi trường
├── .gitignore
├── requirements.txt
├── main.py                # Điểm khởi chạy ứng dụng
└── README.md
```

Đây là cấu trúc dự kiến. Có thể thay đổi trong quá trình triển khai để
giữ project gọn và dễ hiểu.

## 4. Công nghệ dự kiến

---

Thành phần Công nghệ Vai trò

---

Ngôn ngữ Python Điều phối các thành
phần

Camera RTSP Lấy luồng video từ
camera IP

Xử lý ảnh/video OpenCV, FFmpeg Đọc luồng và trích xuất
frame

AI đa phương thức Gemini API Hiểu câu hỏi, phân tích
ảnh và tạo câu trả lời

Speech-to-Text Whisper local hoặc giải Chuyển giọng nói thành
pháp STT phù hợp văn bản

Text-to-Speech Piper local hoặc giải Đọc câu trả lời thành
pháp TTS phù hợp tiếng

Lưu hội thoại SQLite hoặc bộ nhớ Lưu ngữ cảnh trò chuyện
trong phiên

Cấu hình python-dotenv Quản lý API key và
thông tin camera

---

> Các lựa chọn STT/TTS là phương án dự kiến, chưa phải quyết định cố
> định. Có thể thay thế sau khi thử nghiệm thiết bị thực tế.

## 5. Cách các thành phần hoạt động

### 5.1. Camera

- Kết nối camera qua RTSP nếu thiết bị hỗ trợ.
- Đọc frame mới từ luồng camera.
- Chỉ chụp ảnh khi cần trả lời câu hỏi liên quan đến hình ảnh.
- Không lưu video hoặc ảnh lâu dài nếu không cần thiết.

Ví dụ địa chỉ RTSP (chỉ là định dạng minh họa):

```text
rtsp://USERNAME:PASSWORD@CAMERA_IP:554/STREAM_PATH
```

Đường dẫn RTSP thực tế phụ thuộc hãng và model camera.

### 5.2. Gemini

Gemini là thành phần AI chính trong phiên bản đầu:

- Nhận câu hỏi dạng văn bản.
- Nhận ảnh camera khi câu hỏi cần quan sát.
- Trả lời bằng tiếng Việt.
- Sử dụng lịch sử hội thoại do ứng dụng quản lý để giữ ngữ cảnh.

Không cần gọi AI Vision riêng và AI chat riêng ở phiên bản đầu. Một
model Gemini có hỗ trợ đầu vào hình ảnh có thể xử lý cả hai nhiệm vụ.

### 5.3. Âm thanh

Luồng âm thanh dự kiến:

```text
Microphone
    |
    v
Speech-to-Text
    |
    v
Text question
    |
    v
Gemini
    |
    v
Text answer
    |
    v
Text-to-Speech
    |
    v
Speaker
```

Phiên bản đầu có thể kiểm tra Gemini bằng câu hỏi nhập từ bàn phím
trước, sau đó mới tích hợp microphone và loa.

### 5.4. Lịch sử hội thoại

Backend quản lý lịch sử hội thoại và gửi một lượng ngữ cảnh phù hợp
trong mỗi request.

Ví dụ:

```text
User: Mày thấy cái gì trên bàn?
Assistant: Tao thấy một chiếc cốc và một chiếc điện thoại.
User: Cái cốc màu gì?
Assistant: Cái cốc có màu trắng.
```

Lịch sử hội thoại không đồng nghĩa với việc AI có thể nhớ mọi thứ mãi
mãi. Nếu muốn hỏi về sự kiện từ những ngày trước, cần xây dựng chức năng
lưu sự kiện riêng ở phiên bản sau.

## 6. Lộ trình triển khai

### Phase 1 --- Camera Vision

- [ ] Xác định hãng và model camera.
- [ ] Kiểm tra camera có hỗ trợ RTSP hay không.
- [ ] Kết nối camera bằng Python/OpenCV.
- [ ] Chụp một frame thành ảnh.
- [ ] Tạo Gemini API key và cấu hình môi trường.
- [ ] Gửi ảnh cùng câu hỏi đến Gemini.
- [ ] In câu trả lời tiếng Việt ra terminal.

**Kết quả mong đợi:** Có thể hỏi "Camera đang nhìn thấy gì?" và nhận
được mô tả từ Gemini.

### Phase 2 --- Text Chat

- [ ] Nhập câu hỏi bằng bàn phím.
- [ ] Duy trì lịch sử hội thoại.
- [ ] Phân biệt câu hỏi cần ảnh và câu hỏi chỉ cần văn bản.
- [ ] Chụp ảnh mới khi cần.
- [ ] Xử lý lỗi API và giới hạn quota.

**Kết quả mong đợi:** Trò chuyện nhiều lượt và hỏi tiếp về nội dung
trong ảnh.

### Phase 3 --- Voice Interaction

- [ ] Kết nối microphone.
- [ ] Tích hợp Speech-to-Text.
- [ ] Tích hợp Text-to-Speech.
- [ ] Phát câu trả lời qua loa.
- [ ] Xử lý trường hợp người dùng nói khi AI đang phản hồi.

**Kết quả mong đợi:** Có thể nói chuyện với trợ lý mà không cần gõ bàn
phím.

### Phase 4 --- Optional Improvements

- [ ] Phát hiện chuyển động hoặc người bằng xử lý local.
- [ ] Chủ động thông báo khi có sự kiện được chọn.
- [ ] Lưu lịch sử sự kiện trong SQLite.
- [ ] Tích hợp điều khiển camera nếu thiết bị hỗ trợ.
- [ ] Tối ưu thời gian phản hồi và lượng API sử dụng.

Các tính năng ở Phase 4 không bắt buộc đối với prototype ban đầu.

## 7. Cấu hình môi trường

Tạo file `.env` từ `.env.example`:

```env
GEMINI_API_KEY=your_gemini_api_key

CAMERA_RTSP_URL=rtsp://username:password@camera-ip:554/stream-path
```

Không commit file `.env` hoặc API key lên GitHub.

Cài đặt thư viện:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Cài dependencies:

```bash
pip install -r requirements.txt
```

Chạy ứng dụng (sau khi triển khai `main.py`):

```bash
python main.py
```

## 8. Chi phí và giới hạn

Dự án ưu tiên các dịch vụ miễn phí hoặc chạy local:

- Gemini API: sử dụng Free Tier nếu model và tài khoản đủ điều kiện.
- OpenCV/FFmpeg: xử lý camera local.
- STT/TTS: ưu tiên giải pháp chạy local để hạn chế chi phí.
- SQLite: lưu dữ liệu local.

Free Tier có giới hạn sử dụng theo model và project. Quota, giá và điều
khoản có thể thay đổi; cần kiểm tra trong Google AI Studio và tài liệu
chính thức trước khi triển khai.

Tài liệu: - [Google AI Studio](https://aistudio.google.com/) - [Gemini
API Documentation](https://ai.google.dev/gemini-api/docs) - [Gemini API
Pricing](https://ai.google.dev/gemini-api/docs/pricing) - [OpenCV
Documentation](https://docs.opencv.org/) - [FFmpeg
Documentation](https://ffmpeg.org/documentation.html)

## 9. Quyền riêng tư và an toàn

Vì hệ thống sử dụng camera trong nhà, cần lưu ý:

- Chỉ bật microphone/camera khi người dùng biết và đồng ý.
- Không ghi âm hoặc gửi hình ảnh liên tục khi không cần thiết.
- Hạn chế gửi hình ảnh riêng tư lên dịch vụ AI bên ngoài.
- Không commit RTSP URL có mật khẩu, API key, ảnh hoặc video cá nhân.
- Đặt giới hạn kích thước và thời gian lưu ảnh.
- Không dùng hệ thống làm thiết bị giám sát bí mật.
- Nếu trẻ em sử dụng, nên có người lớn hướng dẫn và giám sát.

---

## 10. Mục tiêu phiên bản đầu tiên

Phiên bản đầu tiên chỉ cần hoàn thành một luồng đơn giản:

**Người dùng hỏi → Camera chụp ảnh → Gemini phân tích và trả lời →
Terminal hiển thị câu trả lời.**

Khi luồng này hoạt động ổn định, mới bổ sung microphone và loa để biến
nó thành một trợ lý AI có thể trò chuyện bằng giọng nói.

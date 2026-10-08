<div align="center">
  <img src="./docs/images/logo.png" alt="VideoCaptioner Logo" width="100">
  <h1>VideoCaptioner</h1>
  <p>Công cụ xử lý phụ đề video dựa trên mô hình ngôn ngữ lớn (LLM) — Nhận dạng giọng nói, tối ưu hóa phụ đề, dịch thuật, lồng tiếng và ghép video tất cả trong một</p>

  [Tài liệu trực tuyến](https://weifeng2333.github.io/VideoCaptioner/) · [Sử dụng CLI](#cli-dong-lenh) · [Giao diện GUI Desktop](#gui-desktop) · [Claude Code Skill](#claude-code-skill)
</div>

## Cài đặt

```bash
pip install videocaptioner          # Cài đặt CLI + GUI Desktop
```

Các tính năng miễn phí (nhận dạng giọng nói Bcut/BiJian, dịch Bing/Google) **không cần bất kỳ cấu hình nào, cài đặt là dùng được ngay**.

## CLI (Dòng lệnh)

```bash
# Chuyển đổi giọng nói thành phụ đề (miễn phí, không cần API Key)
videocaptioner transcribe video.mp4 --asr bijian

# Dịch phụ đề (sử dụng dịch Bing miễn phí)
videocaptioner subtitle input.srt --translator bing --target-language en

# Quy trình hoàn chỉnh: Nhận dạng → Tối ưu hóa → Dịch thuật → Ghép video
videocaptioner process video.mp4 --target-language ja

# Gắn phụ đề trực tiếp vào video (Burn-in)
videocaptioner synthesize video.mp4 -s subtitle.srt

# Tải video trực tuyến (YouTube, Bilibili, ...)
videocaptioner download "https://youtube.com/watch?v=xxx"
```

Khi cần sử dụng các tính năng LLM (tối ưu hóa ngắt câu phụ đề, dịch bằng mô hình ngôn ngữ lớn), hãy cấu hình API Key:

```bash
videocaptioner config set llm.api_key <your-key>
videocaptioner config set llm.api_base https://api.openai.com/v1
videocaptioner config set llm.model gpt-4o-mini
```

Thứ tự ưu tiên cấu hình: `Tham số dòng lệnh > Biến môi trường (VIDEOCAPTIONER_*) > Tệp cấu hình > Giá trị mặc định`. Chạy `videocaptioner config show` để xem cấu hình hiện tại.

<details>
<summary>Danh sách tất cả các lệnh CLI</summary>

| Lệnh | Mô tả |
|------|-------|
| `gui` | Mở phiên bản Desktop. Bạn cũng có thể chạy trực tiếp lệnh `videocaptioner-gui` |
| `transcribe` | Chuyển đổi giọng nói thành phụ đề. Các engine hỗ trợ: `faster-whisper`, `whisper-api`, `bijian` (miễn phí), `jianying` (miễn phí), `whisper-cpp` |
| `subtitle` | Tối ưu hóa / Dịch phụ đề. Các dịch vụ dịch: `llm`, `bing` (miễn phí), `google` (miễn phí) |
| `dub` | Tạo âm thanh lồng tiếng hoặc video lồng tiếng theo phụ đề |
| `synthesize` | Gắn phụ đề vào video (phụ đề mềm / phụ đề cứng hardsub) |
| `process` | Xử lý toàn bộ quy trình tự động từ đầu đến cuối |
| `download` | Tải video từ YouTube, Bilibili và nhiều nền tảng trực tuyến |
| `config` | Quản lý cấu hình (`show`, `set`, `get`, `path`, `init`) |

Chạy `videocaptioner <lệnh> --help` để xem đầy đủ các tham số. Tài liệu CLI chi tiết xem tại [docs/cli.md](docs/cli.md).

</details>

## GUI Desktop

```bash
pip install videocaptioner
videocaptioner-gui                  # Mở trực tiếp giao diện Desktop
videocaptioner gui                  # Lệnh tương đương
videocaptioner                      # Khi không truyền tham số cũng sẽ mở giao diện Desktop
```

<details>
<summary>Các cách cài đặt khác: Bộ cài Windows / Script một dòng cho macOS</summary>

**Windows**: Tải bộ cài đặt từ [Releases](https://github.com/quangvinh1102/VideoCaptioner/releases)

**macOS**:
```bash
curl -fsSL https://raw.githubusercontent.com/WEIFENG2333/VideoCaptioner/master/scripts/run.sh | bash
```

</details>


<!-- <div align="center">
  <img src="https://h1.appinn.me/file/1731487405884_main.png" alt="Xem trước giao diện" width="90%" style="border-radius: 5px;">
</div> -->

![Xem trước giao diện](https://h1.appinn.me/file/1731487410170_preview1.png)
![Xem trước giao diện](https://h1.appinn.me/file/1731487410832_preview2.png)

## Cấu hình LLM API

LLM chỉ được sử dụng cho việc tối ưu hóa ngắt câu phụ đề và dịch thuật bằng mô hình lớn. Các tính năng miễn phí (nhận dạng giọng nói BiJian, dịch Bing) hoàn toàn không cần cấu hình.

Hỗ trợ tất cả các nhà cung cấp tương thích với OpenAI API:

| Nhà cung cấp | Trang chủ | Ghi chú |
|--------------|-----------|---------|
| **VideoCaptioner Relay** | [api.videocaptioner.cn](https://api.videocaptioner.cn) | Xử lý đồng thời cao, chi phí tối ưu, hỗ trợ GPT/Claude/Gemini... |
| SiliconCloud | [cloud.siliconflow.cn](https://cloud.siliconflow.cn/i/HF95kaoz) | Nền tảng SiliconFlow |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com) | Nền tảng DeepSeek |

Bạn chỉ cần nhập API Base URL và API Key trong phần Cài đặt phần mềm hoặc qua CLI. [Xem hướng dẫn cấu hình chi tiết](https://weifeng2333.github.io/VideoCaptioner/config/llm)

## Claude Code Skill

Dự án này cung cấp [Claude Code Skill](https://code.claude.com/docs/en/skills.md), cho phép trợ lý AI có thể gọi trực tiếp VideoCaptioner để xử lý video.

Cài đặt vào Claude Code:

```bash
mkdir -p ~/.claude/skills/videocaptioner
cp skills/SKILL.md ~/.claude/skills/videocaptioner/SKILL.md
```

Sau đó trong Claude Code chỉ cần gõ `/videocaptioner transcribe video.mp4 --asr bijian` là có thể sử dụng ngay.

## Cơ chế hoạt động

```
Đầu vào âm thanh/video → Nhận dạng giọng nói (ASR) → Ngắt câu phụ đề → Tối ưu hóa LLM → Dịch thuật → Ghép / Xuất video
```

- Dấu thời gian cấp từ (Word-level timestamps) + Phát hiện hoạt động giọng nói (VAD), độ chính xác nhận dạng cao
- Hiểu ngữ nghĩa bằng LLM để ngắt câu, giúp trải nghiệm đọc phụ đề tự nhiên và mạch lạc
- Dịch thuật hiểu ngữ cảnh sâu, hỗ trợ cơ chế phản tư tối ưu (reflection)
- Xử lý hàng loạt đa luồng đồng thời, tối ưu hiệu suất

## Phát triển & Đóng góp mã nguồn

```bash
git clone https://github.com/quangvinh1102/VideoCaptioner.git
cd VideoCaptioner
uv sync && uv run videocaptioner     # Chạy giao diện GUI
uv run videocaptioner --help          # Xem trợ giúp CLI
uv run pyright                        # Kiểm tra kiểu dữ liệu (Type check)
uv run pytest tests/test_cli/ -q      # Chạy bộ kiểm thử (Tests)
```

## Giấy phép

[GPL-3.0](LICENSE)

[![Star History Chart](https://api.star-history.com/svg?repos=quangvinh1102/VideoCaptioner&type=Date)](https://star-history.com/#quangvinh1102/VideoCaptioner&Date)


本项目提供了 [Claude Code Skill](https://code.claude.com/docs/en/skills.md)，让 AI 编程助手可以直接调用 VideoCaptioner 处理视频。

安装到 Claude Code：

```bash
mkdir -p ~/.claude/skills/videocaptioner
cp skills/SKILL.md ~/.claude/skills/videocaptioner/SKILL.md
```

然后在 Claude Code 中输入 `/videocaptioner transcribe video.mp4 --asr bijian` 即可使用。

## 工作原理

```
音视频输入 → 语音识别 → 字幕断句 → LLM 优化 → 翻译 → 视频合成
```

- 词级时间戳 + VAD 语音活动检测，识别准确率高
- LLM 语义理解断句，字幕阅读体验自然流畅
- 上下文感知翻译，支持反思优化机制
- 批量并发处理，效率高

## 开发

```bash
git clone https://github.com/WEIFENG2333/VideoCaptioner.git
cd VideoCaptioner
uv sync && uv run videocaptioner     # 运行 GUI
uv run videocaptioner --help          # 运行 CLI
uv run pyright                        # 类型检查
uv run pytest tests/test_cli/ -q      # 运行测试
```

## 许可证

[GPL-3.0](LICENSE)

[![Star History Chart](https://api.star-history.com/svg?repos=WEIFENG2333/VideoCaptioner&type=Date)](https://star-history.com/#WEIFENG2333/VideoCaptioner&Date)

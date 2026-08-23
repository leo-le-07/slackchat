# slackchat — Design Spec

Ngày: 2026-08-22
Trạng thái: đã duyệt, sẵn sàng lập implementation plan

## 1. Mục tiêu

Một công cụ xử lý text cá nhân, chạy local, làm đúng hai việc:

- **Correction mode** — nhận text tiếng Anh, chỉ sửa lỗi ngữ pháp, chính tả, dùng từ sai. Không viết lại câu đã đúng.
- **Translation mode** — nhận text tiếng Việt, dịch sang tiếng Anh tự nhiên theo voice constraint có sẵn.

Người dùng không phải chỉ định ngôn ngữ. Tool tự chọn mode.

Phase 1 là CLI. Phase 2 là browser extension. Cả hai là hai lớp gọi **cùng một** core service.

### Ràng buộc sản phẩm quan trọng nhất

Correction mode **không được over-edit**. Xu hướng tự nhiên của LLM là viết lại cho trang trọng hơn, làm mất giọng người viết. Câu đã đúng ngữ pháp phải được trả về nguyên vẹn. Đây là ràng buộc số một, và mọi quyết định thiết kế bên dưới phục vụ việc đo được và cưỡng chế được nó.

### Ràng buộc output (cả hai mode)

- Không emoji
- Không em dash do AI sinh ra
- Không dấu `;` do AI sinh ra
- Giữ tone và độ dài tương đối so với input
- Translation không được thêm ý hoặc ngữ cảnh không có trong bản gốc

## 2. Non-goals

- Không hỗ trợ cặp ngôn ngữ nào ngoài Việt → Anh và sửa lỗi tiếng Anh
- Không hỗ trợ đa người dùng, không có tài khoản, không có sync
- Không viết lại theo phong cách (rewrite/paraphrase/tone shifting)
- Không giải thích lỗi ngữ pháp trong Phase 1
- Không LLM-as-judge trong Phase 1 (xem §8.3)

## 3. Quyết định kiến trúc

| Quyết định | Chọn | Lý do |
|---|---|---|
| Extension ↔ core | Local HTTP daemon trên `127.0.0.1` | API key ở lại trên máy, không tốn hosting, contract giống hệt remote nếu sau này muốn đổi |
| Language detection | Heuristic thuần, deterministic | Người dùng cam kết luôn gõ tiếng Việt có dấu, nên không cần LLM fallback |
| Output | Plain text + diff tính local bằng `difflib` | Miễn phí, không hallucinate; diff chính là thước đo over-edit |
| Chống over-edit | 3 lớp: prompt → sanitize → validate + retry | Prompt một mình sẽ trôi; cờ trong log là nguyên liệu cho eval |
| Log storage | SQLite | Query được bằng SQL, cần cho replay eval; `sqlite3` có sẵn trong stdlib |
| Eval | Deterministic assertions + rubric người chấm | Assertion đo được ràng buộc số một; rubric phủ phần chất lượng dịch mà assertion mù |
| Repo | Single Python package, boundary cưỡng chế bằng `import-linter` | Đạt yêu cầu "no duplicate logic" với ceremony thấp hơn uv workspace |

## 4. Cấu trúc

```
pyproject.toml
AGENTS.md
src/slackchat/
  config.py
  core/
    detect.py        # phát hiện ngôn ngữ
    pipeline.py      # process() — điểm vào duy nhất
    diffing.py       # diff word-level bằng difflib
    validate.py      # cổng over-edit + ký tự cấm
    types.py         # Result, Change, Mode
  providers/
    base.py          # Provider protocol
    anthropic.py
    pricing.py       # bảng giá theo model id
  prompts/
    correction.md
    translation.md
    voice.md
  store/
    schema.sql
    sqlite.py
  eval/
    runner.py
    assertions.py
    rubric.md
    cases/*.yaml
  cli/main.py
  server/app.py
tests/
extension/           # Phase 2, để trống ở Phase 1
docs/superpowers/specs/
```

**Luật import (cưỡng chế bằng `import-linter` trong CI):**
`core/` và `providers/` không được import `cli/`, `server/`, `eval/`, `store/`.
`core/` phụ thuộc `providers/` qua Protocol, không phụ thuộc implementation cụ thể.
Việc ghi log do lớp gọi (CLI/server/eval) thực hiện sau khi nhận `Result`, không nằm trong `core/`.

## 5. Core pipeline

Toàn hệ thống quy về một hàm:

```python
def process(text: str, mode: Mode | None = None) -> Result
```

CLI render `Result`. Server serialise `Result` thành JSON. Eval assert lên `Result`. Không tồn tại code path thứ hai.

Input rỗng hoặc chỉ có khoảng trắng bị từ chối trước khi gọi provider: không tốn tiền, không ghi vào `runs`, CLI thoát với mã khác 0.

```
input text
  ├─ detect(text)            pure, deterministic, không gọi API
  ├─ load_prompt(mode)       template + voice.md, kèm version và hash
  ├─ provider.complete(...)  Anthropic Haiku mặc định
  ├─ sanitize(output, input) xoá emoji
  ├─ diff(input, output)     difflib word-level
  ├─ validate(...)           over-edit gate + ký tự cấm → retry tối đa 1 lần
  └─ Result
```

### 5.1 Detection

Quy tắc: nếu text chứa ký tự thuộc **tập ký tự riêng của tiếng Việt** thì là tiếng Việt → translation mode. Ngược lại → correction mode.

Tập ký tự riêng: `ă â đ ê ô ơ ư` cùng mọi biến thể mang dấu thanh của chúng, cộng các nguyên âm mang dấu thanh tiếng Việt (`á à ả ã ạ` và tương tự cho `e i o u y`).

**Xử lý loanword tiếng Anh có dấu.** Các từ như `café`, `résumé`, `naïve`, `fiancé` chứa ký tự có dấu nhưng không phải tiếng Việt. Giải pháp: một allowlist nhỏ các loanword phổ biến được loại trừ trước khi chấm. Ngoài ra, `đ ơ ư ă` là ký tự chỉ có trong tiếng Việt và không xuất hiện trong loanword nào — sự hiện diện của chúng là bằng chứng đủ mạnh, quyết định ngay. Chỉ khi tín hiệu duy nhất là nguyên âm mang dấu thanh mới cần đối chiếu allowlist.

Không có vùng xám và không có prompt hỏi lại. `--mode` là escape hatch duy nhất.

Hàm này thuần túy, không gọi mạng, và được unit-test bằng một bảng mẫu cố định.

### 5.2 Diff

Word-level bằng `difflib.SequenceMatcher` trên token đã tách. Sinh ra `list[Change]` và `changed_ratio` = số token bị thêm/xoá/thay chia tổng token input.

### 5.3 Sanitize và validate

**Sanitize** chỉ làm một việc an toàn: xoá emoji. Không đụng đến `;` và em dash, vì mọi cách thay thế máy móc đều đoán mò — đổi `;` thành `.` cần viết hoa từ kế tiếp và sẽ làm hỏng danh sách.

**Validate** kiểm ba điều:

1. **Ký tự cấm.** `;` và em dash chỉ tính là vi phạm khi **có trong output mà không có trong input**. Nếu người viết tự dùng em dash trong câu tiếng Anh của họ, correction mode giữ nguyên — xoá đi chính là over-edit. Translation mode cấm vô điều kiện, vì output hoàn toàn do AI sinh.
2. **Over-edit.** `changed_ratio` vượt `max_changed_ratio` (mặc định 0.25) là dấu hiệu trôi. Chỉ áp dụng cho correction mode.
3. **Output rỗng.**

Vi phạm bất kỳ → retry một lần với chỉ dẫn bổ sung nêu đúng vi phạm. Vẫn vi phạm → trả kết quả kèm cờ, và với ký tự cấm thì áp dụng thay thế máy móc như phương án cuối, gắn cờ `mechanical_fallback`.

Cờ có thể xuất hiện: `over_edit_suspected`, `banned_char_introduced`, `retried`, `mechanical_fallback`, `unknown_pricing`.

### 5.4 Kiểu dữ liệu

```python
Mode = Literal["correction", "translation"]

@dataclass(frozen=True)
class Result:
    run_id: str
    original: str
    output: str
    mode: Mode
    forced: bool              # True nếu do --mode chỉ định
    changes: list[Change]
    changed_ratio: float
    flags: list[str]
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    created_at: str           # ISO8601 UTC
    error: str | None
```

## 6. Prompts và versioning

Ba file markdown trong `prompts/`. Mỗi file có frontmatter `version:`.

`voice.md` là ràng buộc giọng văn dùng chung, được chèn vào cả hai prompt qua placeholder `{{VOICE}}`. Nội dung do người dùng cung cấp (2026-08-22) và được ghi nguyên văn, không diễn giải lại: quy tắc định dạng, danh sách từ/cụm cần cắt bỏ, bảng thay thế, mẫu cấu trúc, và non-goals.

Prompt "resolved" là template đã chèn `voice.md`. Mỗi lần chạy log **cả hai**:

- `prompt_version` — số bạn tự bump, dùng để group khi so sánh eval
- `prompt_hash` — sha256 12 ký tự của prompt đã resolve

Cần cả hai vì hash bắt được trường hợp sửa file mà quên bump version. Eval runner cảnh báo khi thấy cùng một `prompt_version` ứng với hai `prompt_hash` khác nhau. Không có kiểm tra này thì mọi so sánh giữa các version đều có thể là dối trá.

## 7. Logging

SQLite tại `~/.local/share/slackchat/runs.db`, bật WAL để daemon và CLI ghi song song an toàn.

```sql
CREATE TABLE runs (
  run_id         TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,        -- ISO8601 UTC
  client         TEXT NOT NULL,        -- cli | server | eval
  mode           TEXT NOT NULL,        -- correction | translation
  forced         INTEGER NOT NULL,
  input          TEXT NOT NULL,
  output         TEXT NOT NULL,
  provider       TEXT NOT NULL,
  model          TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  prompt_hash    TEXT NOT NULL,
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  cost_usd       REAL,
  latency_ms     INTEGER,
  changed_ratio  REAL,
  flags          TEXT,                 -- JSON array
  error          TEXT
);

CREATE INDEX idx_runs_mode_version ON runs(mode, prompt_version);
CREATE INDEX idx_runs_created ON runs(created_at);

CREATE TABLE reviews (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  dimension  TEXT NOT NULL,
  score      INTEGER NOT NULL CHECK (score IN (0,1,2)),
  reviewer   TEXT NOT NULL,            -- 'human' hoặc model id
  note       TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, dimension, reviewer)
);
```

`changed_ratio` được lưu sẵn để query xu hướng over-edit mà không phải diff lại.
`client` tách run thật khỏi run eval.
`reviewer` nằm trong primary key ngay từ đầu, nên khi Phase 2 thêm LLM judge, việc tính agreement giữa judge và người chỉ là một câu JOIN.

`cost_usd` là `NULL` khi model không có trong bảng giá, kèm cờ `unknown_pricing`. Không bao giờ ghi `0.0`, vì đó là nói dối trong chính dữ liệu dùng để eval.

Log lưu text nguyên văn ở local. Không có tính năng xoá tự động ở Phase 1; `runs.db` là file thường, người dùng tự xoá khi muốn.

## 8. Eval

### 8.1 Assertion deterministic

Case định nghĩa trong `eval/cases/*.yaml`:

```yaml
- id: noop-001
  mode: correction
  input: "The deployment failed because the config was missing."
  assert: { unchanged: true }

- id: fix-001
  mode: correction
  input: "I has finish the task yesterday."
  assert:
    output_contains_any: ["I finished", "I have finished"]
    max_changed_ratio: 0.4
```

Assertion khả dụng: `unchanged`, `output_contains_any`, `output_excludes`, `max_changed_ratio`, `max_words`.

Bốn assertion **áp dụng tự động cho mọi case**, không cần khai báo:

1. Không emoji trong output
2. Không em dash hoặc `;` do AI thêm vào
3. Output không rỗng
4. Length ratio không vượt `max_length_ratio` (§9)

`unchanged: true` so sánh sau khi strip trailing whitespace, phần còn lại byte-for-byte. Pass rate của nhóm case `unchanged` là metric quan trọng nhất của dự án, vì nó đo trực tiếp ràng buộc số một.

Runner ghi kết quả vào bảng `runs` với `client='eval'`, nên `slackchat eval --compare 2 3` chỉ là một câu SQL so pass rate giữa hai prompt version. Cuối mỗi lần chạy in tổng cost thật.

### 8.2 Rubric

Assertion nhị phân mù với chất lượng dịch. Không có cách deterministic nào để đo "dịch tự nhiên, không word-by-word, giữ đúng voice". Rubric phủ khoảng trống đó.

Thang **0 / 1 / 2** — ba mức được chấm nhất quán hơn thang 1-5 nhiều.

**Translation**

| Chiều | Đo cái gì |
|---|---|
| Adequacy | Mọi ý bản gốc có mặt, không thêm ý nào không có |
| Naturalness | Đọc như người bản xứ viết, không lộ dấu vết dịch |
| Voice compliance | Khớp `voice.md`: ngắn gọn, không filler |
| Concision | Không dài hơn mức cần thiết |

**Correction** — chỉ dùng cho case *có* lỗi; case không lỗi đã được assertion `unchanged` lo.

| Chiều | Đo cái gì |
|---|---|
| Minimality | Chỉ chạm vào lỗi, không viết lại phần đúng |
| Correctness | Sửa đúng lỗi, không tạo lỗi mới |
| Voice preservation | Giọng người viết còn nguyên |

Rubric sống ở `eval/rubric.md`, có `version:` như prompt. **Mỗi mức 0/1/2 của mỗi chiều phải có anchor bằng văn bản kèm ví dụ cụ thể.** Rubric không có anchor thì chấm hai lần ra hai kết quả và trở nên vô dụng — viết anchor là phần việc thật của slice này, không phải liệt kê tên chiều.

### 8.3 Ai chấm

Phase 1: **người chấm**. `slackchat eval --review` lấy N case, hiện input và output, nhận điểm từng chiều qua terminal, ghi vào bảng `reviews` với `reviewer='human'`. Khoảng 20 case mất chừng 15 phút.

Điểm người là ground truth thật, và về sau chính là tập calibrate cho LLM judge.

Phase 2 (ngoài phạm vi spec này): thêm judge, cho judge chấm cùng những `run_id` mà người đã chấm, đo agreement. Agreement thấp thì judge bị vứt. Không chạy judge tự động khi chưa đo agreement, vì một con số không đối chiếu được là một con số vô nghĩa.

## 9. Model routing

```python
class Provider(Protocol):
    name: str
    def complete(self, system: str, user: str, *, model: str) -> Completion
```

`Completion` chứa `text`, `input_tokens`, `output_tokens`, `model`.

Phase 1 chỉ có `AnthropicProvider`. Local model về sau là một class khoảng 40 dòng gọi endpoint OpenAI-compatible của Ollama hoặc llama.cpp. Provider được chọn bằng config, không đụng vào `core/`.

Cost tính từ bảng giá trong `providers/pricing.py`, keyed theo model id. Đây là **dữ liệu**, không phải logic, để sửa được khi giá thay đổi.

**Giá trị đã tra cứu** (Anthropic docs, 2026-08-22):

| Mục | Giá trị |
|---|---|
| Model ID đầy đủ | `claude-haiku-4-5-20251001` |
| Alias | `claude-haiku-4-5` |
| Giá input | $1 / triệu token |
| Giá output | $5 / triệu token |

Config mặc định dùng **alias** cho ngắn gọn. Bảng giá trong `pricing.py` key theo **model id đầy đủ có ngày**, vì đó là giá trị Anthropic trả về trong field `model` của response — phải khớp đúng cái đó thì `cost_usd` mới đúng, không phải chuỗi người dùng gõ trong config.

### Config

`~/.config/slackchat/config.toml`:

```toml
[provider]
name  = "anthropic"
model = "claude-haiku-4-5"

[limits]
max_changed_ratio = 0.25   # correction: tỉ lệ token bị đổi tối đa
max_length_ratio  = 1.5    # len(output) / len(input) tối đa, tính theo từ
max_retries       = 1

[cli]
auto_copy = true           # chỉ áp dụng cho CLI, server không liên quan

[server]
port = 8765
```

API key đọc từ biến môi trường `ANTHROPIC_API_KEY`. Không bao giờ nằm trong file config.

## 10. Bề mặt CLI

```
slackchat "text"                  # one-shot: auto-detect, in diff màu, thoát
slackchat                         # tty  → REPL session; pipe → batch một lần
slackchat --mode translation ...  # ép mode
slackchat --raw                   # text trần, để | pbcopy
slackchat detect "text"           # chỉ in mode, không gọi API
slackchat log [--last N] [--mode M]
slackchat eval [--compare A B] [--review]
slackchat serve
```

### 10.1 Hai chế độ chạy

**One-shot** — `slackchat "text"`. Xử lý, in kết quả, thoát.

**Session (REPL)** — `slackchat` không đối số **và** `sys.stdin.isatty()` là true. Vào vòng lặp nhập/xuất liên tục.

Nếu không có đối số nhưng stdin bị pipe (`cat f.txt | slackchat`), giữ hành vi batch: đọc hết stdin, xử lý một lần, thoát. Không vào REPL vì không có ai ngồi gõ tiếp.

### 10.2 Hành vi REPL

- Banner ASCII wordmark `SLACKCHAT` in một lần khi vào, kèm một dòng hint dim gray `Ctrl+D or /exit to quit`. Font bitmap hardcode trong `cli/banner.py`, không thêm dependency.
- Prompt chính `> `. Sau dòng đầu, prompt các dòng tiếp là `... ` để báo đang ở giữa input nhiều dòng.
- **Dòng trống kết thúc một lượt nhập.** Toàn bộ các dòng đã gõ được nối bằng `\n` và gửi làm một input duy nhất. Điều này cho phép dán đoạn nhiều dòng mà không bị cắt nhỏ.
- Enter trên dòng trống khi chưa gõ gì → bỏ qua lặng lẽ, hiện lại prompt, không tạo `run`, không báo lỗi.
- `/exit` hoặc `/quit` rồi Enter, ở **bất kỳ lúc nào** kể cả giữa input đang gõ dở → thoát ngay, không chờ dòng trống.
- Ctrl+D (EOF) hoặc Ctrl+C → thoát ngay.
- Mỗi lượt là một dòng riêng trong `runs` với `client='cli'`. Không có khái niệm `session_id` ở Phase 1.

### 10.3 Clipboard

Sau khi in kết quả, nếu `sys.stdout.isatty()` là true **và** `cli.auto_copy` là true, copy `Result.output` (text sạch, không phải bản có mã màu diff) vào clipboard bằng `pbcopy`, rồi in dòng xác nhận `(copied to clipboard)`.

Khi stdout bị pipe hoặc redirect thì bỏ qua hoàn toàn cả việc copy lẫn dòng xác nhận, giữ nguyên pattern `slackchat "..." --raw | pbcopy` thủ công và không làm bẩn output.

Không có cờ `--copy`/`--no-copy`. Muốn tắt hẳn thì sửa `cli.auto_copy` trong config.

Đây là hành vi **chỉ của CLI**. `core/` không biết gì về clipboard; `cli/clipboard.py` gọi `pbcopy` qua `subprocess`. Phụ thuộc macOS, chấp nhận được cho Phase 1.

## 11. Server (Phase 1, chuẩn bị cho Phase 2)

FastAPI. `POST /process` nhận `{text, mode?}`, trả `Result` dạng JSON. `GET /health`.

Bind **chỉ** `127.0.0.1`.

**Bảo mật.** Bất kỳ trang web nào đang mở trong browser cũng có thể gọi `fetch('http://127.0.0.1:8765/...')` từ JS của nó. Vì vậy daemon yêu cầu shared-secret token trong header. Token sinh ra ở lần `serve` đầu tiên và lưu vào config; extension đọc token đó. Kèm CORS allowlist đúng origin của extension. Request thiếu token bị từ chối với 401.

Server **không chứa logic nào của riêng nó** — chỉ gọi `process()` rồi ghi log với `client='server'`. Đây là bằng chứng cho yêu cầu "một core service dùng chung".

## 12. Thứ tự vertical slices

Mỗi slice kết thúc bằng test xanh và một cách verify thủ công.

| # | Slice | Verify bằng |
|---|---|---|
| 1 | `detect` | Chạy trên bảng mẫu VN/EN có cả `café`, `résumé`. Không cần API key. |
| 2 | `correct` | `slackchat "I has finish"` trả text đã sửa |
| 3 | Diff render + `--raw` + auto-copy | Nhìn output màu; `--raw \| pbcopy`; redirect ra file thì không tự copy |
| 4 | REPL session + banner | `slackchat` hiện banner, gõ nhiều lượt, dán đoạn nhiều dòng, `/exit` thoát |
| 5 | `translate` + auto-route | Gõ hai câu hai thứ tiếng, đúng mode chạy |
| 6 | Validate + retry + flags | Dựng input cố tình phá, thấy cờ bật |
| 7 | Logging | Chạy 3 lệnh, query `runs.db` |
| 8 | Eval assertions | `slackchat eval` in pass rate |
| 9 | Rubric + `--review` | Chấm 5 case, query bảng `reviews` |
| 10 | `serve` | `curl` ra đúng JSON như CLI |

Slice 1 và 4 chạy được không cần API key (slice 4 verify được phần banner, prompt, multi-line, thoát — phần gọi model dùng mock).

## 13. Tech stack

- Python (bản mới nhất hỗ trợ được), quản lý bằng `uv`
- Stdlib cho SQLite và diff
- FastAPI cho server
- `pytest` cho test, `import-linter` cho ràng buộc kiến trúc
- Extension Phase 2 dùng JS, nằm trong `extension/` cùng repo

## 14. Phụ thuộc bên ngoài

Cả hai phụ thuộc đã được giải quyết trước khi lập implementation plan:

1. **Nội dung `voice.md`** — người dùng đã cung cấp 2026-08-22. Nội dung gốc được ghi nguyên văn vào `prompts/voice.md`.
2. **Model id và đơn giá Haiku** — đã tra tài liệu Anthropic, xem bảng ở §9.

## 15. Ngoài phạm vi Phase 1

Browser extension, LLM-as-judge và đo agreement, replay eval từ log thật, local model provider. Tất cả đã được chừa đường trong thiết kế: extension dùng HTTP contract có sẵn, judge dùng cột `reviewer`, replay dùng bảng `runs`, local model dùng `Provider` protocol.

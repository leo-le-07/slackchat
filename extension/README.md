# slackchat Edge extension

Nút nhỏ cạnh khung gõ tin nhắn Slack: gửi text trong khung sang daemon
`slackchat` chạy local, hiện diff inline, chỉ ghi vào khung khi bạn bấm
**Check**.
Manifest V3, vanilla JS, không build, không npm.
Thiết kế: `docs/superpowers/specs/2026-10-15-edge-extension-design.md`.

## Cài một lần

1. Chạy daemon, **từ repo root** (file token nằm ở `<cwd>/.config/server_token`):

   ```bash
   uv run slackchat serve
   ```

   Lệnh này in ra `X-Slackchat-Token: <token>`; token là phần sau dấu hai chấm.

2. Edge → `edge://extensions` → bật **Developer mode** → **Load unpacked** →
   chọn thư mục `extension/`.

3. **Options** của extension → dán token → **Save**. Port để trống (= 8765).

Sau đó mở `https://app.slack.com`, gõ vào khung chat, bấm **Fix**.

## Sau khi khởi động lại máy

Chỉ cần bước 1 ở trên. Edge vẫn giữ extension đã load, token nằm trong
`chrome.storage.local` nên không phải dán lại — trừ khi bạn xoá
`.config/server_token`, hoặc chạy `serve` từ thư mục khác (thư mục đó sẽ sinh
token mới).

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/health   # 200 = đang chạy, 000 = chưa chạy
```

## Sau khi sửa code extension

1. `edge://extensions` → card slackchat → **⟳ Reload**
2. **F5 lại tab Slack.** Bắt buộc: content script đã nằm trong tab đó vẫn chạy
   code cũ, nếu không F5 popup sẽ báo `Extension context invalidated`.

Chỉ sửa `options.html`/`options.js` → chỉ cần mở lại trang Options.
Chỉ sửa `background.js` → ⟳ là đủ.

## Khi có trục trặc

**Không thấy nút Fix.** Kiểm tra xem bạn đã F5 tab Slack sau lần reload gần
nhất chưa. Vẫn không thấy → F12 → Console ở tab Slack:

```js
const ed = document.querySelector('[contenteditable="true"]');
console.log(ed && ed.closest("[data-qa]") && ed.closest("[data-qa]").dataset.qa);
```

In ra `message_input` → gửi tôi lỗi trong Console. In ra giá trị khác (hoặc
`undefined`) → Slack đã đổi markup, cần cập nhật `INPUT_CONTAINER` trong
`content.js`.

**Lúc nào cũng báo lỗi generic.** `edge://extensions` → card slackchat →
**service worker** → Console:

```js
chrome.runtime.sendMessage({type:"process", text:"I has finish the task"}).then(console.log)
```

- `{ok: true, result: {...}}` → worker, daemon, token đều ổn; lỗi nằm ở
  `content.js`.
- `{ok: false}` → token sai, daemon chưa chạy, hoặc request bị chặn trước khi
  rời browser; cách cuối là thêm origin của extension vào
  `[server] allowed_origins` trong `.config/config.toml` rồi chạy lại `serve`.

**Bấm Check không thay đổi gì, hoặc mất mention / emoji / dấu xuống dòng.**
Đây là chỗ dễ vỡ nhất (đường ghi ngược vào editor) — ghi lại bạn gõ gì và nhận
lại gì, sửa được trong `content.js`.

**Request có tới daemon không?**

```bash
sqlite3 data/runs.db "select created_at, client, mode, substr(input,1,36) from runs order by created_at desc limit 5;"
```

Request từ extension được log với `client='server'`.

## Test

```bash
node --test "extension/test/*.test.js"
```

Phải dùng glob, không dùng `node --test extension/test/` (truyền cả thư mục sẽ
lỗi trên Node 22.21). `./scripts/check.sh` không bao gồm JS.

## Chưa xác nhận

- `@mention`, emoji và dấu xuống dòng (Shift+Enter) có sống sót qua vòng
  round trip không.
- Selector của Slack (`[data-qa="message_input"]`) và đường ghi ngược — mới là
  phỏng đoán.
- Nút **Fix** có đè lên nút Send của Slack không.

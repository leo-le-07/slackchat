---
name: prompt-change
description: Sửa prompt correction trong slackchat và kiểm tra output mới với golden set. Dùng mỗi khi src/slackchat/prompts/*.md thay đổi, hoặc khi Leo báo một output thực tế bị sai và muốn sửa prompt.
---

# Đổi prompt correction (slackchat)

Golden set là `evals/correction.yaml`. Các case `unchanged` phải trả về
nguyên byte; các case `needs_fix` có token `include`/`exclude` cứng và một
diff `reference` mềm. Cần `ANTHROPIC_API_KEY` (vài cent mỗi lần chạy).

## Các bước

1. **Baseline.** Ghi lại `version:` hiện tại trong prompt. Nếu
   `uv run slackchat eval --compare N N` báo không có eval run nào cho
   version đó, chạy `uv run slackchat eval` trước. Không có baseline thì
   không có gì để so sánh.
2. **Sửa prompt và tăng `version:`.** Không bao giờ nâng `max_changed_ratio`.
   Không bao giờ sửa hay nới lỏng case `unchanged` để run pass.
3. **Chạy** `uv run slackchat eval`. Nếu có `WARNING: ... bump version:` nghĩa
   là text đã đổi mà số version cũ vẫn giữ; sửa việc này trước khi đi tiếp.
4. **So sánh** `uv run slackchat eval --compare OLD NEW`. Exit 1 nghĩa là một
   case `unchanged` bị regress.
5. **Báo cáo cho Leo, theo thứ tự:** các regression của `unchanged` (chặn),
   các case bị đảo kết quả (▼/▲), các output khác nhau giữa hai version kèm
   diff. Đừng nói prompt mới "tốt hơn". Đưa bằng chứng và nhờ Leo đánh giá
   các diff. Mỗi case chỉ chạy một lần thì nhiễu: chạy lại trước khi đổ lỗi
   cho một case bị đảo.
6. **Xong** khi `./scripts/check.sh` exit 0. Commit bằng skill `git-commit`.

## Khi Leo báo output sai

Thêm nó vào `evals/correction.yaml` trước (`needs_fix` với token
`include`/`exclude` thể hiện chỗ cần sửa, và một `reference`), chạy
`uv run slackchat eval` và xem nó fail, rồi mới đổi prompt. Đổi prompt mà
không có case đã fail trước đó chỉ là đoán mò.

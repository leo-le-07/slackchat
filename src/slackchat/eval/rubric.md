---
version: 1
---
# Rubric

Scale: 0, 1, 2. Three levels, because three get scored consistently and five
do not. Score each dimension independently — do not let a good translation
carry a voice failure, or a voice win excuse a dropped fact.

If two levels both seem to fit, take the lower one.

## Translation

### Adequacy — is every idea in the source present, and nothing added?

- **0** — A fact, an ask, a name, a number, or a qualifier is missing, or
  something was invented.
  *Source:* "Em định nhờ Trường thu thập chi phí Claude và Novita cho dự án Dental trong tháng 7 và tháng 8."
  *Output:* "I want Truong to collect the project costs." — drops both
  vendors, the project name, and both months.
- **1** — Everything is present, but one qualifier or hedge shifted in
  strength, or a small detail is blurred.
  *Output:* "I will ask Truong to collect the Claude and Novita costs for the
  Dental project in July and August." — "em định nhờ" is an intention to ask,
  not a decision already taken; "I will ask" is firmer than the source.
- **2** — Every idea is present at the same strength, and nothing is added.
  *Output:* "I intend to ask Truong to collect the Claude and Novita costs for
  the Dental project for July and August."

### Naturalness — does it read as written by a fluent speaker, not translated?

- **0** — Word order, particles, or calques give the translation away.
  *Source:* "Anh xem giúp em cái này với, không gấp nên anh cứ từ từ."
  *Output:* "Brother please see help me this thing, not urgent so brother just
  slowly."
- **1** — Grammatical and understandable, but a native writer would not phrase
  it this way.
  *Output:* "Please help me to take a look at this. It is not urgent so you
  can take your time slowly."
- **2** — Reads like an ordinary work chat message.
  *Output:* "Could you take a look at this? It's not urgent, so no rush."

### Voice compliance — does it match `prompts/voice.md`?

- **0** — Contains something the voice constraint bans outright: an emoji, an
  em dash, a semicolon, or a phrase from the cut list.
  *Output:* "I hope this message finds you well — kindly review the attached
  at your earliest convenience."
- **1** — Nothing banned, but the register drifted formal, or an inflated
  adjective slipped in.
  *Output:* "I would like to request a comprehensive review of this item."
- **2** — Direct, unpadded, hedges kept where the source had them, "Hi a
  @name" preserved when addressing a senior.
  *Output:* "Hi a @Kenny Trinh, any concerns if I ask Truong to look into this?"

### Concision — is it as short as the meaning allows?

- **0** — Noticeably longer than the source with no gain in clarity; one idea
  spread across two sentences.
  *Source:* "Số liệu này chưa khớp, em kiểm tra lại rồi báo anh sau."
  *Output:* "I have noticed that the figures in this document do not appear to
  match up at the present time. I will conduct a further review of them and
  will then provide you with an update afterwards."
- **1** — Slightly padded: a redundant clause, or a filler opener.
  *Output:* "Just to let you know, these numbers don't match yet. I will check
  them again and update you later."
- **2** — No word could be removed without losing meaning.
  *Output:* "These numbers don't match yet. I'll check and update you."

## Correction

Score correction only on cases that *had* an error. A case with no error is
already covered by the `unchanged` assertion, which is binary and does not
need a human.

### Minimality — did it touch only the error?

- **0** — Rewrote correct text: reordered clauses, merged or split sentences,
  swapped in different words, or changed the register.
  *Input:* "Our current developers is using Claude Code plus Novita DeepSeek."
  *Output:* "At present, our development team leverages Claude Code in
  conjunction with Novita DeepSeek."
- **1** — Fixed the error, but also made one unnecessary edit — a synonym, an
  added article, a punctuation change nobody asked for.
  *Output:* "Our current developers are using Claude Code together with Novita
  DeepSeek."
- **2** — Exactly the error changed, nothing else.
  *Output:* "Our current developers are using Claude Code plus Novita DeepSeek."

### Correctness — is the error actually fixed, with no new error?

- **0** — The error survives, or a new one appeared.
  *Input:* "I has finish the task yesterday."
  *Output:* "I has finished the task yesterday."
- **1** — The error is fixed, but the fix is awkward, or it drags in a smaller
  new infelicity.
  *Output:* "I have finished the task yesterday." — grammatical, but the
  present perfect sits badly with "yesterday"; "I finished" is the natural fix.
- **2** — The error is fixed cleanly and nothing new is wrong.
  *Output:* "I finished the task yesterday."

### Voice preservation — does it still sound like the same writer?

- **0** — The writer disappeared: contractions expanded, hedges deleted,
  informality ironed out, or a greeting or closing added.
  *Input:* "In terms of scope, I guess around 1-2 hours."
  *Output:* "Regarding the scope of this work, the estimated duration is
  approximately one to two hours."
- **1** — Mostly intact, but one voice marker was lost — a hedge, a
  contraction, an abbreviation, or an @mention form.
  *Output:* "In terms of scope, it is around 1-2 hours." — "I guess" is gone.
- **2** — Every voice marker survives.
  *Output:* "In terms of scope, I guess around 1-2 hours."

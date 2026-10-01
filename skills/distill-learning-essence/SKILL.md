---
name: distill-learning-essence
description: 把已完成的学习材料整理成 900 字以内的笔记精华，并保存不可覆盖的 Markdown revision。用于“总结这一节”“给我笔记精华”或复用已有精华的写法。
---

# 学习笔记精华

把完整学习材料重组为一份自然、完整的短稿，供快速复习。交付精华正文，并在当前学习工作区保存一个新版本；知识卡由 `feynman-notes` 生成。

运行保存脚本需要 Python 3.10+ 和 PyYAML。脚本位于本技能的 `scripts/save_draft.py`，从实际安装位置解析该路径，保存位置由当前学习工作区决定。

## 写作

1. 读取本节主笔记和自测（同一文件只读一次），如有系列索引，只读与本节有关的段落；再用可用聊天记录补充用户原话、真实卡点、比喻、啊哈时刻和个人判断。
2. 冲突时采用已核实的成稿事实；材料缺失时不编造学习过程。
3. 围绕唯一主轴重组内容，讲清核心机制和易混概念。有证据才写实践、代价、踩坑或薄弱项。
4. 使用大白话和贴切比喻，技术词保留英文。标题写 `第 XX 集精华 · 主题`；用 `一句话：`钉住主轴，以 `收束：`结束。

### 默认费曼基线

除非用户另定风格，按 `直觉图景 → 术语映射 → 最小例子 → 易混边界 → 证据收口` 成稿：

- 保留必要术语，但首次出现时立刻翻成人话；解释对象之间怎样配合，不堆定义。
- 有清晰映射时使用一个贯穿全文的生活比喻，默认中等密度；没有合适比喻时改用具体场景，不硬套多个比喻。
- 用户要求复用某篇精华时，读取该参考稿，沿用解释密度与表达风格，换成本节机制和例子。
- 首稿目标为 700～850 个 Unicode code point。900 是硬上限，不是目标；自然讲完就停。

只有事实缺口、材料冲突或用户要求比较版本时，才继续读取知识卡或其他 revision。

## 留存

1. 把从标题到 `收束：` 的最终正文写入工作区内本次专用的 UTF-8 临时文件；正文不进入 shell 参数。
2. 用重复的 `--source` 记录实际读取的本地素材。正文和素材都必须是工作区内的相对路径；仅有聊天记录时可省略 `--source`。
3. 调用保存器。`--series` 使用小写 kebab-case，`--episode` 使用正整数；无集号的临时学习可用 `session-YYYYMMDD-HHMMSS`。

以下示例假定 `$skillDir` 指向实际安装的本技能目录，当前目录为学习工作区；正文先写入 `scratch/essence.md`。

```powershell
python (Join-Path $skillDir "scripts/save_draft.py") `
  --workspace-root "." `
  --series "cache-basics" `
  --episode "1" `
  --topic "Cache hit" `
  --body-file "scratch/essence.md" `
  --source "content/learning-notes/cache-basics/01.md"
```

保存器去掉正文首尾空白、将换行规范化为 LF，校验不超过 900 个 Unicode code point（包含标题、标点、空格和换行）。文件保存在 `artifacts/drafts/learning-essence/<series>/<episode>-rNNN.md`，用 `open(..., 'x')` 从 `r001` 起创建第一个可用 revision，保留历史版本。

stdout 为单个 JSON：成功时把 `logical_body` 原样交付，`saved_path` 是留存位置，metadata 包含来源路径和字数；失败时仍交付内存中的正文，另行说明未能留存。最后只删除本次创建的临时文件。

## 交付检查

- 正文自然完整且不超过 900 字，没有注水。
- 用户原话、数字和结论都能回到素材。
- helper 返回 `ok: true`，聊天正文与 `logical_body` 逐字一致。
- 最终只给精华正文；仅在留存失败时补充错误。

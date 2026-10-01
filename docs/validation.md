# 首版验收记录

日期：2026-10-01。示例和模拟对话用于验证工作流，不代表真实学习者已经理解。

## 已完成

- Windows、Python 3.13.2，干净 venv 从 `requirements.txt` 安装 PyYAML 6.0.3、jsonschema 4.26.0。
- 两个技能的 `quick_validate.py` 结构检查通过。
- `source.py` 自检通过，两次同输入只计算一次，规则更改后清除旧值。
- 精华保存器六项测试通过：900 字边界、非法输入、相对来源与 LF、版本不覆盖、CLI JSON。
- 渲染器五项测试通过：资源定位、无效显式目录、损坏 PNG 拒绝、卡组提交失败回滚、单文件替换失败保留旧清单。
- 缓存示例实际生成四张 2160×2880 PNG，布局预检通过，manifest 哈希和顺序验收通过。
- 已逐张查看大图并复核约 540px 阅读效果；相对 Markdown 链接检查通过。
- 示例精华实存为 r001，476 个 Unicode code point，正文与 helper 的 `logical_body` 一致。
- 字体 SHA-256 与固定 Google Fonts commit 中的文件一致，OFL 与来源记录随包。
- 公共渲染模板复制到独立临时目录后，显式指定技能资源目录，起步卡生成 3/3 PNG 并通过 manifest 校验。

## 浏览器限制

本次成功渲染使用 Chrome 154.0.8037.92。本机 Edge 154.0.4258.37 的无界面模式退出 0，却没有返回 DOM 预检结果，未通过验收。渲染器默认优先 Chrome，其次 Edge；可用 `FEYNMAN_NOTES_EDGE` 指定其他 Chromium 可执行文件。失败时保留旧产物并返回错误。

其他系统、Python 版本、Agent 与浏览器版本尚未验证。

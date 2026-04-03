# AutoFigure-Edit 工作流 · 用户体验审计记录

> 审计方法：`.codex/skills/ux-experience-audit`（用户旅程 → 断点 → P0/P1/P2 → 最小跨层修复）  
> 更新时间：2026-04-03

---

## 1. 用户问题重述（典型）

| 句式 | 实例 |
|------|------|
| 用户在 **配置页** 填好 API、上传图、选 local SAM 后点 **Confirm**，预期 **画布上出现进度/产物**，实际 **长时间无变化或白屏**。 |
| 用户在 **未区分「参考风格」与「已有成图」** 时上传图片，预期 **直接做切分/矢量化**，实际 **仍走步骤一文生图（OpenRouter）**，卡在远程、GPU 无占用。 |
| 用户已配置 **`.env` 的 HF_TOKEN**，预期 **立刻进入本地模型**，实际 **仍卡在步骤一 LLM 或步骤三前才用到 HF**。 |
| 用户 **中断/关闭** 长时间任务后，日志出现 `KeyboardInterrupt`，界面 **缺少「正在等待远程」的明确说明**。 |

---

## 2. 体验断点地图（主流程）

```
[配置页] method 文本 + Provider + API Key + SAM 后端 + 可选上传图
    → POST /api/run → 子进程 autofigure2.py
        → 步骤一：文生图（OpenRouter/Bianxie/Gemini）— 常耗时数分钟，原日志几乎无心跳
        → 步骤二：SAM3（local/API）
        → 步骤三：RMBG-2.0（HF_TOKEN / 缓存）
        → 步骤四～五：多模态 SVG + 替换
    → SSE /api/events → [画布页] 状态/日志/产物
```

| 节点 | 可见信号（原状） | 问题 |
|------|------------------|------|
| 步骤一进行中 | 仅一行「发送请求到…」 | **长时间无新日志**，用户以为死机；**GPU 无占用**属预期（生图在远端） |
| 参考图上传 | 仅作 **风格参考**，仍触发文生图 | **与「我已有成图」心智不符** |
| `.env` HF_TOKEN | 仅服务 **RMBG** 与 HF 缓存路径 | 用户易误以为 **解决步骤一**；文档需写清 |
| 画布页 | Status: Running | 失败时 **非 0 退出** 可能仍显示笼统状态，需看 Logs |
| 子进程被中断 | `KeyboardInterrupt` | 用户误以为 bug，实为 **等待过长手动中断** |

---

## 3. 根因与优先级（P0 / P1 / P2）

### P0（阻断或强烈误导）

- **P0-1**：用户有现成示意图时，**无法跳过步骤一**，必须走远程文生图 → 与本机 SAM/抠图诉求冲突。  
  - **处理**：CLI/Web 支持 **`--input_figure` / `input_figure_path`**，跳过文生图，直接写入 `figure.png` 进入下游。  
  - **状态**：后端 `server.py` + `autofigure2.py` 已接好；**Web 配置页需显式选项与 payload**，否则用户仍不知道。

### P1（高摩擦）

- **P1-1**：OpenRouter 文生图 **阻塞数分钟无心跳** → 误以为卡死。  
  - **处理**：`autofigure2.py` 已对 OpenRouter 请求增加 **约 30s 一次等待日志**（见历史改动）。  
- **P1-2**：`.env` 与 `HF_TOKEN` 作用域 **未在 UI 说明** → 配置后仍卡在步骤一。  
  - **处理**：部署文档与配置页 **hint** 区分「LLM API（页面）」与「HF（RMBG）」。

### P2（优化）

- **P2-1**：画布页 **步骤文案** 可更明确「当前在等远程还是本地」。  
- **P2-2**：`merge_threshold` 默认值在 CLI 与 server 不一致等 **文档一致性**（低优先级）。

---

## 4. 修复与改动文件（本轮）

| 文件 | 改动 |
|------|------|
| `web/index.html` | 增加「将上传图作为示意图（跳过步骤一文生图）」复选框与说明 |
| `web/app.js` | `input_figure_path` 与 `reference_image_path` 互斥；sessionStorage 记住选项；勾选「跳过」时校验已上传图与 API Key |
| `web/styles.css` | `.checkbox-row` 布局 |
| `doc/WINDOWS_DEPLOYMENT_ZH.md` | 补充「已有图跳过文生图」与 Web/CLI 说明 |
| `autofigure2.py` / `server.py` | `input_figure` / `input_figure_path`；后端在存在 `input_figure` 时不传 `reference_image_path` |

---

## 5. 验证命令与结果（记录用）

```powershell
cd E:\Development\AutoFigure-Edit
.\.venv\Scripts\python.exe -m py_compile autofigure2.py server.py
```

预期：`exit code 0`。

手动验证：

1. 配置页勾选「跳过文生图」、上传 PNG、**可不填 method**、填写 **SVG 所需 LLM API Key**；`run.log` 元数据行必须出现 **`--input_figure`** 且 **不得**出现 `--reference_image_path`；步骤一应打印 **「跳过文生图，使用本地输入图」**。  
2. 不勾选时行为与原先一致（参考图 + 文生图）。

---

## 6. 文档与 .debug 更新

- 本文档：`.debug/workflow-ux-audit.md`（本文件）  
- 用户向文档：`doc/WINDOWS_DEPLOYMENT_ZH.md`（同步补充）  
- 关联历史：`.debug/sam3-local-path-and-runtime.md`（HF / SAM / Python 版本）

---

## 7. 残留风险与下一步

- **步骤四～五仍依赖 LLM**：即使用户跳过文生图，**SVG 生成与优化**仍要 API Key；需在 UI 文案写清。  
- **仅跑切分/抠图**：可通过 CLI `--stop_after 3` 等实现，**Web 未暴露**；若需求多可再加「高级选项」。  
- **网络/代理**：若 OpenRouter 不可达，仅「跳过步骤一」模式可绕过步骤一，仍无法解决 **步骤四** 若需外网的问题。

---

## 8. 勾选 skip 仍走文生图 + Method 空文本（2026-04-03）

- **现象**：`run.log` 只有 `--reference_image_path`，步骤一仍为「参考图 + 文生图」；用户希望勾选 skip 后 **可不填 Method**。
- **根因**：仅依赖前端互斥 `input_figure_path` / `reference_image_path` 在部分情况下未按预期投递；且 **FastAPI / 前端** 原要求 `method_text` 非空，与「仅有成图」场景不符。
- **修复**：
  1. `RunRequest` 增加 **`skip_ai_image_generation`**；为 true 时服务端 **只传 `--input_figure`**（路径取自 `input_figure_path` 或 `reference_image_path`），**不传** `--reference_image_path`。
  2. **允许 method_text 为空**（skip 时）：服务端填入占位句以满足子进程参数；**步骤四 SVG 提示词本身不依赖 method 正文**。
  3. 前端固定发送 **`skip_ai_image_generation`** + **`reference_image_path`**（上传返回的相对路径）。
  4. CLI：`--input_figure` 且无 method 时不再报错（`--method_text` 可为空配合 `--input_figure`）。

## 9. 仍出现旧文案 “Please provide method text.”（2026-04-03）

- **根因**：浏览器 **强缓存** 旧版 `/app.js`，实际仍在跑 **仅判断 `!methodText`** 的老逻辑；与当前仓库源码不一致。
- **修复**：点击时用 **`skipFigureEl()`** 重新取复选框；**`GET /app.js`** 返回 **`Cache-Control: no-store`**；`index.html` 引用 **`/app.js?v=20260403`**；错误提示更新并建议 **Ctrl+F5**。

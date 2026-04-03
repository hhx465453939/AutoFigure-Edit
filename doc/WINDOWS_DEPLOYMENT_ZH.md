# AutoFigure-Edit 本地 Windows 部署指南

本文档面向在 **Windows 10/11** 上从零部署 **AutoFigure-Edit**（论文方法文本 → 可编辑 SVG 插图），并与仓库根目录 [README_ZH.md](../README_ZH.md) 互为补充。

---

## 1. 项目功能概览

**AutoFigure-Edit** 是 AutoFigure 的演进版本，核心能力是：

- **文本驱动插图**：根据论文「方法」段落（或类似说明文本），调用多模态大模型生成期刊风格的示意图草稿（光栅图）。
- **结构化解构**：用 **SAM3** 在图上检测图标/区域，输出带标签的框与元数据；各区域经 **RMBG-2.0** 抠图得到透明 PNG 素材。
- **可编辑 SVG**：再经多模态模型生成与标注图对齐的 **占位符式 SVG 模板**，把透明图标按标签替换进模板，得到 **`final.svg`**。
- **可选风格迁移**：提供参考图时，生成阶段可贴近参考风格。
- **Web 工作台**：内置静态页 + **SVG-Edit**，可在浏览器里打开结果并继续改矢量。

典型产物目录中会包含：`figure.png`、`samed.png`（或同类标注图）、`boxlib.json`、`icons/*.png`、`template.svg`、`final.svg` 等（具体以运行日志与 `outputs/` 为准）。

---

## 2. 内在机制（流水线）

整体可理解为 **「生成 → 分割 → 抠图 → 模板 → 合成」**：

| 阶段 | 作用 |
|------|------|
| 文生图 | 用法方法文本（+ 可选参考图）调用配置的 **image 模型**，得到初始示意图 `figure.png`。 |
| SAM3 | 按一个或多个文本提示（如 `icon,person,...`）做概念分割，合并重叠框（由 `merge_threshold` 等控制），得到标注可视化与 **`boxlib.json`**。选用 **本地** SAM（`--sam_backend local`）时，权重来自 Hugging Face **门禁** 仓库 **`facebook/sam3`**（须单独申请访问 + **HF_TOKEN**，与 RMBG **不是**同一页面；见 **6.4**）。 |
| RMBG-2.0 | 对每个框裁剪并去背景，得到 **`icons/`** 下透明素材。权重来自 Hugging Face **门禁** 仓库 **`briaai/RMBG-2.0`**（须单独申请访问 + **HF_TOKEN**，见 **6.4**）。 |
| SVG 模板 | 将原图、标注图、`boxlib` 等作为多模态输入，生成 **`template.svg`**（占位符与标签一致）；可选多轮 **LLM 优化**（`optimize_iterations`，为 0 则跳过）。 |
| 对齐与替换 | 比较原图与 SVG 画布尺寸做坐标缩放，按 **`<AF>01` 等标签** 把图标嵌入模板，输出 **`final.svg`**。 |

**后端编排**：`server.py`（FastAPI）在收到 `/api/run` 后，用子进程调用 **`autofigure2.py`**，并把 `outputs/<job_id>/` 作为单次任务目录；静态前端在 `web/`，根路径由 FastAPI 挂载。

**CLI**：可直接运行 `autofigure2.py`，适合脚本化与调试。

---

## 3. 系统与环境前提

- **操作系统**：Windows 10/11（本文场景）。
- **Python**：仓库标明 **3.10+**；若使用**本地 SAM3**，需遵循 [facebookresearch/sam3](https://github.com/facebookresearch/sam3) 官方要求（常见为更新 Python / PyTorch / CUDA）。
- **网络**：需能访问所选 LLM 供应商 API；使用 Roboflow / fal 时需能访问对应域名。
- **磁盘与内存**：PyTorch + Transformers + 模型缓存体积较大，建议预留数 GB 以上空间。

---

## 4. 部署方式选择

| 方式 | 适用情况 |
|------|----------|
| **Docker Desktop** | 希望环境可复现、少折腾本机 CUDA/Python 版本；详见根目录 `docker-compose.yml` 与 [README_ZH.md](../README_ZH.md)「选项 0」。 |
| **本机 Python** | 需要调试 `autofigure2.py`、已配好 GPU/CUDA，或不想用容器。 |

下面 **5** 为 Docker 要点；**6～7** 为本机 Windows 详细步骤。

---

## 5. 方案 A：Docker（Windows 简要）

1. 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（启用 WSL2 后端，按官方文档操作）。
2. 在项目根目录复制环境文件：

   ```powershell
   Copy-Item .env.example .env
   ```

3. 编辑 `.env`：至少配置 **`HF_TOKEN`**。完整本地流水线需对 Hugging Face 上 **`briaai/RMBG-2.0`**（RMBG）**与**（若不用 Roboflow 而跑本地 SAM）**`facebook/sam3`** **分别** 完成门禁申请（见 **6.4**）。使用默认 Roboflow SAM 时配置 **`ROBOFLOW_API_KEY`**，可不下载 `facebook/sam3`。
4. 启动：

   ```powershell
   docker compose up -d --build
   ```

5. 浏览器访问 `http://localhost:8000`，健康检查：`http://localhost:8000/healthz` 应返回 `{"status":"ok"}`。

受限网络、DNS 等问题见 [README_ZH.md](../README_ZH.md) 中 Docker 小节（镜像源、`DOCKER_DNS_*` 等）。

---

## 6. 方案 B：本机 Python（推荐用 uv 管理）

### 6.1 安装 Python 与 uv

- 从 [python.org](https://www.python.org/downloads/) 安装 Python。**如果你要使用本地 SAM3，强烈建议直接用 Python 3.12.x（不要用 3.13）**（安装时勾选 **Add python.exe to PATH**）。
- 安装 **uv**（任选其一）：

  ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```

  或使用 `pip install uv`。

### 6.2 获取代码并创建虚拟环境

```powershell
cd E:\Development\AutoFigure-Edit
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
```

若执行策略阻止激活脚本：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 6.3 安装依赖

**PyTorch（有 NVIDIA GPU 时）**：请按本机 CUDA 版本从 [PyTorch 官网](https://pytorch.org/get-started/locally/) 选择对应命令，例如 CUDA 12.4：

```powershell
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
```

```powershell
uv pip install -r requirements.txt
```

其中已包含本地 SAM3 常见依赖（如 `einops`、`scipy` 无 Triton 时的 EDT 回退、`pycocotools`、`psutil` 等）。若 `pycocotools` 在 Windows 上编译失败，可尝试预编译轮子或 conda，并确保 `pip install -r requirements.txt` 无报错。

**仅 CPU** 时可直接使用 `requirements.txt` 中的 `torch` 默认源，或显式安装 CPU 轮子（以 PyTorch 文档为准）。

### 6.4 Hugging Face：两套「本地化」权重（须分别申请）

本流程在 **本机** 跑通时，会从 Hugging Face Hub **下载两类模型**；二者均为 **Gated（门禁）仓库**，必须在网页上 **分别** 同意条款并等待授权（**只申请其中一个不能解锁另一个**）。配置 **同一个 `HF_TOKEN`（Read）** 即可用于两个仓库，但前提是 **两个模型页面对你的账号都已显示可下载**。

| Hugging Face 仓库 | 在流水线中的用途 | 何时需要 |
|-------------------|------------------|----------|
| [briaai/RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0) | **步骤三** RMBG 抠图 → `icons/*_nobg.png` | 执行到步骤三及以后（默认流程需要） |
| [facebook/sam3](https://huggingface.co/facebook/sam3) | **步骤二** 本地 SAM3 分割（权重由上游 `build_sam3_image_model` 拉取） | 仅当 **`--sam_backend local`**（Web 里选本地 SAM） |

**部署前请按顺序完成：**

1. 登录 Hugging Face，打开上表 **两个** 链接（若只用 Roboflow/fal 做 SAM，可跳过 `facebook/sam3` 一行）。
2. 在每个模型页分别点击 **「Agree and access」**（或等价入口），等待审核。**刚提交时** 常见状态为 **「awaiting review」**：在通过前 Hub 对文件请求会返回 **403** / `GatedRepoError`，**不会开始真正下载大文件**。
3. 在 [Access Tokens](https://huggingface.co/settings/tokens) 创建 **Read** 权限的 Token。
4. 准备本地 `.env`（本项目 `autofigure2.py` / 子进程会读取）：

   ```powershell
   Copy-Item .env.example .env
   ```

   在 `.env` 中设置 `HF_TOKEN=hf_xxx`（推荐）；或在当前 PowerShell 会话：`$env:HF_TOKEN = "hf_..."`。也可使用 `huggingface-cli login` / `hf auth login`（与 `.env` 二选一即可，勿把 Token 提交到 Git）。

5. **缓存目录**：若未设置 `HF_HOME`，权重会默认缓存在项目下 **`models/huggingface/`**（避免占满系统盘 `~/.cache`）。若要放到其他盘，在 `.env` 设置 `HF_HOME=D:\你的路径`。

**看起来像「下载卡住」时请先区分：**

- **权限未通过**：日志停在访问 `.../resolve/main/config.json`、报错 **`GatedRepoError` / 403**，或 HF 提示 **awaiting review** → 属于 **门禁未生效**，与带宽无关；需等审核通过后再跑。
- **已通过门禁、首次拉 checkpoint**：体积大，**数分钟甚至更久** 属正常；可看 `HF_HOME` 下是否出现 `models--facebook--sam3` / `models--briaai--RMBG-2.0` 等目录持续增长。

### 6.5 SAM3：三种用法（择一）

**SAM3 是什么：** 在 **AutoFigure-Edit** 里它负责对 **`figure.png` 这类示意图** 做**视觉分割**：按文字提示（如 icon、人物）找出多块区域并画框，不是对论文文本做「切分」。本质上是**图像上的区域/概念分割模型**。

1. **Roboflow（Web 默认、免本地 SAM）**（推荐上手）  
   - 注册 [Roboflow](https://roboflow.com/)，设置：

     ```powershell
     $env:ROBOFLOW_API_KEY = "你的密钥"
     ```

   - Web 界面或 CLI 使用 `--sam_backend roboflow`。

2. **fal.ai**  
   - 设置 `FAL_KEY`，CLI 示例：`--sam_backend fal`。

3. **本地 SAM3**（代码在 [facebookresearch/sam3](https://github.com/facebookresearch/sam3)）  
   - **装在哪都行：** `pip install -e` 只关心「磁盘上有一份源码 + 当前 venv」，**可以克隆在本仓库子目录里**，不必再在开发盘根目录多开一个平行文件夹。推荐路径示例：`AutoFigure-Edit\vendor\sam3`（需先建好 `vendor` 目录）。
   - **版本硬约束（上游要求）：** Python **3.12+**、PyTorch **2.7+**、支持 **CUDA 12.6+** 的 GPU 驱动环境。若本机 venv 仍是 3.10，需要**新建一个 3.12 的 venv** 专门跑本项目 + 本地 SAM，或继续用 Roboflow/fal 避免抬 Python 版本。
   - **在本项目内克隆并装进同一 venv：**

     ```powershell
     cd E:\Development\AutoFigure-Edit
     mkdir vendor -ErrorAction SilentlyContinue
     git clone https://github.com/facebookresearch/sam3.git vendor\sam3
     .\.venv\Scripts\Activate.ps1
     uv pip install -e .\vendor\sam3
     ```

     与 [官方安装步骤](https://github.com/facebookresearch/sam3#installation) 一致：再按官方说明安装对应 CUDA 的 `torch`/`torchvision`（示例见上游 README 中的 `cu128` 索引），需要跑 notebook 时再 `pip install -e ".[notebooks]"`（在 `vendor\sam3` 目录下执行）。

   - **Git：** 仓库根目录 `.gitignore` 已忽略 `vendor/sam3/`，避免把整份上游代码误提交；你本地照样用，只是默认不进 Git。
   - **权重与门禁：** 与 **6.4** 中 **`facebook/sam3`** 为同一项：须在该模型页单独申请通过，并配置 **`HF_TOKEN`**（可与 RMBG 共用同一 Token）。

---

## 7. 启动方式

### 7.1 Web 界面（FastAPI + 静态前端）

在项目根目录、已激活的虚拟环境中：

```powershell
python server.py
```

控制台会打印实际端口（默认从 **8000** 起若被占用则递增）。浏览器打开：

`http://127.0.0.1:8000`（端口以终端输出为准）。

**说明**：

- 产物默认在 **`outputs/`**，上传文件在 **`uploads/`**。
- 若希望 Web 子进程使用**指定 Python 解释器**，可设置环境变量 **`AUTOFIGURE_PYTHON`**（例如多 Python 共存时）。

**已有示意图、不想走步骤一文生图时：** 在配置页上传图片后，勾选 **「Use uploaded image as the figure (skip AI image generation…)」**。后端会设置 **`skip_ai_image_generation`**，强制走 **`--input_figure`**，**不会**再走「参考风格 + 文生图」。此时 **Method text 可留空**（步骤四 SVG 主要依据图像与 SAM 叠图）；**API Key 仍必填**（SVG 多模态调用）。**不勾选**时，上传图仅作**风格参考**，步骤一仍会调用文生图 API。

### 7.2 命令行（CLI）

将方法文本放在文件 `paper.txt`，示例：

```powershell
python autofigure2.py `
  --method_file paper.txt `
  --output_dir outputs\demo `
  --provider bianxie `
  --api_key "你的LLM密钥" `
  --sam_backend roboflow `
  --optimize_iterations 0
```

若本地已有示意图、要**跳过步骤一**：

```powershell
python autofigure2.py `
  --method_file paper.txt `
  --output_dir outputs\demo `
  --provider openrouter `
  --api_key "你的LLM密钥" `
  --input_figure .\my_figure.png `
  --sam_backend local `
  --optimize_iterations 0
```

也可用 `--method_text "多行文本..."` 直接传文本（以 `autofigure2.py --help` 为准）。

常用参数与供应商说明见 [README_ZH.md](../README_ZH.md)「配置」节：`--provider`、`--image_model`、`--svg_model`、`--sam_prompt`、`--placeholder_mode`、`--merge_threshold` 等。

---

## 8. 验证清单

- [ ] `python -c "import torch; print(torch.__version__)"` 无报错。
- [ ] `HF_TOKEN` 已设置；且已在 Hugging Face 上对 **`briaai/RMBG-2.0`** 完成门禁（步骤三需要）。
- [ ] 若使用 **本地 SAM3**：已对 **`facebook/sam3`** 单独完成门禁（与上一条无关）；仅用 Roboflow/fal 时可不勾选此项。
- [ ] 选用 Roboflow 时 `ROBOFLOW_API_KEY` 已设置。
- [ ] `python server.py` 启动后，`/healthz` 返回 `ok`。
- [ ] 在 Web 页提交一小段方法文本，能在 `outputs/<job_id>/` 看到日志与产物。

---

## 9. 常见问题（Windows）

- **`Activate.ps1` 无法执行**  
  使用 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，或改用 `cmd` 与 `.\.venv\Scripts\activate.bat`。

- **端口被占用**  
  `server.py` 会自动尝试 8001、8002…；或关闭占用 8000 的进程后再启。

- **Roboflow 解析失败 / 网络超时**  
  检查代理、防火墙；Docker 用户可参考 README 中的 `DOCKER_DNS_*`；本机可尝试更换 DNS 或使用系统代理。

- **画布页长时间停在 “Running”，日志只到「步骤一 / OpenRouter」**  
  说明 **HF_TOKEN 已通过**，当前卡在 **向 OpenRouter 请求文生图**（含参考图时请求体大、服务端排队时，**等 5～15 分钟都常见**）。请打开 **Logs** 看 `outputs/<job_id>/run.log`：若出现 `KeyboardInterrupt`，多半是等待过久被手动中断。新版本会在等待期间每 30s 打一行提示；请保持页面与终端不要关，并检查代理能否稳定访问 `openrouter.ai`。

- **上传图片后“下一步没反应 / 卡在 local SAM3”**  
  常见是 Python 与依赖组合不兼容（尤其是 Windows 下 Python 3.13 + `sam3` 触发 `numpy<2` 兼容问题）。典型日志会出现 `Numpy built with MINGW-W64 ... CRASHES ARE TO BE EXPECTED`，随后子进程直接退出。建议：
  1) 使用 **Python 3.12** 重建 `.venv`；
  2) 重新安装 `torch/torchvision`（匹配 CUDA）与 `requirements.txt`；
  3) 重新 `pip install -e .\vendor\sam3`；
  4) 若仍需先跑通流程，可临时改 `--sam_backend roboflow`。

- **`ModuleNotFoundError: No module named 'pycocotools'`（本地 SAM）**  
  上游 `sam3` 在导入链中会加载 COCO 相关模块。执行 `uv pip install pycocotools`（或确保 `requirements.txt` 已完整安装）。Windows 若无 MSVC 导致编译失败，需安装 [Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) 或使用带 wheel 的环境。

- **`ModuleNotFoundError: No module named 'psutil'`（本地 SAM）**  
  `sam3_video_predictor` 等模块会 `import psutil`。执行 `uv pip install psutil` 或重装 `requirements.txt`。

- **本地 SAM 报 `GatedRepoError` / 403（`facebook/sam3`），或日志显示 `awaiting a review`**  
  **`facebook/sam3` 与 `briaai/RMBG-2.0` 是两处独立门禁**，须分别在模型页申请；同一 `HF_TOKEN` 即可，但两个页面都需已通过审核。刚提交申请时不会下载权重，见 **6.4**。

- **uvicorn 报错 `Response content longer than Content-Length`（拉取 `/api/artifacts/...`）**  
  任务运行中子进程仍在写入 `figure.png` 等文件时，旧版 `FileResponse` 可能按「打开瞬间」的文件长度声明 `Content-Length`，与传输中变大的文件不一致。当前 `server.py` 已改为整文件读入后再响应；若你仍用旧代码，请更新仓库后重启 `python server.py`。

- **仅 CPU 运行很慢**  
  文生图与多模态调用主要耗时在网络 API；本地 RMBG/SAM 在 CPU 上会明显变慢，有条件建议 GPU + 正确 CUDA 版 PyTorch。

- **与 README 不一致时**  
  以仓库内 **`requirements.txt`、`server.py`、`autofigure2.py`** 及根目录 **README_ZH.md** 为最新事实来源；本文件随仓库维护，如有变更请以代码为准。

---

## 10. 相关文件路径

| 路径 | 说明 |
|------|------|
| `autofigure2.py` | 主流程脚本（CLI 入口） |
| `server.py` | FastAPI 服务与静态资源挂载 |
| `web/` | 前端页面与 SVG-Edit |
| `requirements.txt` | Python 依赖 |
| `.env.example` | Docker/环境变量示例 |
| `README_ZH.md` | 完整功能说明、Docker 细节、引用信息 |

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
| SAM3 | 按一个或多个文本提示（如 `icon,person,...`）做概念分割，合并重叠框（由 `merge_threshold` 等控制），得到标注可视化与 **`boxlib.json`**（框、置信度、来源 prompt）。 |
| RMBG-2.0 | 对每个框裁剪并去背景，得到 **`icons/`** 下透明素材（需 **HuggingFace Token** 且对 `briaai/RMBG-2.0` 有访问权限）。 |
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

3. 编辑 `.env`：至少配置 **`HF_TOKEN`**（RMBG-2.0）；使用默认 Roboflow SAM 时配置 **`ROBOFLOW_API_KEY`**。
4. 启动：

   ```powershell
   docker compose up -d --build
   ```

5. 浏览器访问 `http://localhost:8000`，健康检查：`http://localhost:8000/healthz` 应返回 `{"status":"ok"}`。

受限网络、DNS 等问题见 [README_ZH.md](../README_ZH.md) 中 Docker 小节（镜像源、`DOCKER_DNS_*` 等）。

---

## 6. 方案 B：本机 Python（推荐用 uv 管理）

### 6.1 安装 Python 与 uv

- 从 [python.org](https://www.python.org/downloads/) 安装 Python 3.10+（安装时勾选 **Add python.exe to PATH**）。
- 安装 **uv**（任选其一）：

  ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```

  或使用 `pip install uv`。

### 6.2 获取代码并创建虚拟环境

```powershell
cd E:\Development\AutoFigure-Edit
uv venv
.\.venv\Scripts\Activate.ps1
```

若执行策略阻止激活脚本：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 6.3 安装依赖

```powershell
uv pip install -r requirements.txt
```

**PyTorch（有 NVIDIA GPU 时）**：请按本机 CUDA 版本从 [PyTorch 官网](https://pytorch.org/get-started/locally/) 选择对应命令，例如 CUDA 12.4：

```powershell
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
```

**仅 CPU** 时可直接使用 `requirements.txt` 中的 `torch` 默认源，或显式安装 CPU 轮子（以 PyTorch 文档为准）。

### 6.4 HuggingFace 与 RMBG-2.0

1. 在 [briaai/RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0) 申请访问权限。
2. 在 HuggingFace 创建 **Read Token**。
3. 在 PowerShell 当前用户会话或「系统环境变量」中设置：

   ```powershell
   $env:HF_TOKEN = "hf_你的令牌"
   ```

   持久化可在「系统属性 → 环境变量」中添加用户变量 `HF_TOKEN`。

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
   - **权重：** HuggingFace `facebook/sam3`，需先申请访问再 `hf auth login`（或 `huggingface-cli login`）。

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

也可用 `--method_text "多行文本..."` 直接传文本（以 `autofigure2.py --help` 为准）。

常用参数与供应商说明见 [README_ZH.md](../README_ZH.md)「配置」节：`--provider`、`--image_model`、`--svg_model`、`--sam_prompt`、`--placeholder_mode`、`--merge_threshold` 等。

---

## 8. 验证清单

- [ ] `python -c "import torch; print(torch.__version__)"` 无报错。
- [ ] `HF_TOKEN` 已设置且 RMBG 模型可下载（首次运行会拉取权重）。
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

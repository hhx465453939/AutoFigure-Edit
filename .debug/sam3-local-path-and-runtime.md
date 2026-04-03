# SAM3 Local Backend 排障记录（Windows）

## 运行上下文

- 环境：本机 Windows，项目路径 `E:\Development\AutoFigure-Edit`
- Web 服务：`python server.py`
- 目标：排查 `sam_backend=local` 上传参考图后无进度问题

## 结论

- 不是 `sam3` 路径问题。
- `sam3` 已正确安装并可从项目内路径解析（`vendor/sam3`）。
- 根因是当前 `.venv` 使用 Python 3.13，和 `sam3` 依赖链（`numpy<2`）在 Windows 下出现崩溃，子进程提前退出。

## 证据

- `outputs/*/run.log` 仅出现如下信息后退出：
  - `Numpy built with MINGW-W64 on Windows 64 bits is experimental`
  - `CRASHES ARE TO BE EXPECTED`
- 直接执行最小测试同样复现崩溃（退出码 `-1073741819`）。
- 当前 Python 版本：`3.13.5`（Anaconda 打包）。
- `sam3` 的 `pyproject.toml` 依赖为 `numpy>=1.26,<2`，且工程目标版本到 `py312`。

## 修复建议

1. 使用 Python 3.12 重建项目 venv（建议 `uv venv --python 3.12`）。
2. 安装匹配 CUDA 的 `torch/torchvision/torchaudio`，再装 `requirements.txt`。
3. 在同一 venv 重新安装本地 `sam3`：`pip install -e .\vendor\sam3`。
4. 如需先快速可用，临时改用 `sam_backend=roboflow`。

## 二次排查（白屏 + 无 GPU 占用）

- 复现到新的根因：任务在步骤三前即退出，报错为缺少 `briaai/RMBG-2.0` 访问凭据。
- 本机检查结果：
  - 项目根目录无 `.env`（`env_file=NOT_FOUND`）。
  - 本地 HuggingFace 缓存无 `models--briaai--RMBG-2.0`（`RMBG_cache=NOT_FOUND`）。
- 结论：当前“白屏/无 GPU”主要因为流程未进入真正推理阶段（提前因 `HF_TOKEN` 缺失退出），并非 SAM3 路径问题。
- 代码修复：`autofigure2.py` 已增加本地 `.env` 自动加载逻辑（best-effort），便于 Web/CLI 本地运行读取 `HF_TOKEN`。
- 模型缓存：`HF_HOME` 未设置时默认使用 `<repo>/models/huggingface`，可用 `.env` 中 `HF_HOME` 覆盖。

## 三次排查（配置 HF 后仍「无反应」）

- 样例日志：`outputs/20260403_111812_267850a1/run.log`
- 现象：已进入 **步骤一**（OpenRouter 文生图），卡在 `requests.post(https://openrouter.ai/api/v1)` 读响应，最终以 **`KeyboardInterrupt`** 结束。
- 结论：**HF_TOKEN 已不是问题**；瓶颈在 **OpenRouter 侧耗时**（或网络极慢），用户误以为卡死而中断进程。
- 代码改进：`autofigure2.py` 在 OpenRouter 文生图请求期间每 30s 打印等待提示，避免「日志完全不动」。

## 四次排查（uvicorn: Response content longer than Content-Length）

- 现象：访问 `/api/artifacts/{job_id}/figure.png` 等时 ASGI 抛 `RuntimeError: Response content longer than Content-Length`。
- 原因：`FileResponse` 用 `stat().st_size` 作为 `Content-Length`，子进程仍在写入同一文件时，传输过程中文件变大，实际 body 长于声明长度。
- 修复：`server.py` 的 `GET /api/artifacts/...` 改为 `path.read_bytes()` 后一次性 `Response(content=body, ...)`，长度与内容一致。

## 五次排查（SAM3 local：ModuleNotFoundError: pycocotools）

- 样例：`outputs/20260403_114039_03d4b46c/run.log` — 导入 `sam3.model_builder` 时经 `sam3/train/data/coco_json_loaders.py` 依赖 `pycocotools`。
- 修复：`requirements.txt` 增加 `pycocotools`；在 venv 内执行 `pip install pycocotools`（Windows 若无预编译轮需 VS Build Tools 或改用 conda）。

## 六次排查（SAM3 local：ModuleNotFoundError: psutil）

- 样例：`outputs/20260403_114348_811d1709/run.log` — `sam3.model.sam3_video_predictor` 顶层 `import psutil`。
- 修复：`requirements.txt` 增加 `psutil`；`uv pip install psutil`。
- **冒烟测试（仅步骤一+二、不需 LLM key）**：`python autofigure2.py --method_text "." --input_figure <path/to/figure.png> --output_dir outputs/_smoke_sam2 --sam_backend local --stop_after 2`（`method_text` 仅占位；有 `input_figure` 时 `stop_after=2` 不调用步骤 4+）。
- **本机验证（2026-04-03）**：`psutil` 装好后已能完成 `sam3` 导入并进入 `build_sam3_image_model`；随后 HuggingFace 拉取 `facebook/sam3` 时若账号未授权会出现 **`GatedRepoError` / 403**，需在 [facebook/sam3](https://huggingface.co/facebook/sam3) 申请访问并在 `.env` 配置 **`HF_TOKEN`**（与 RMBG 相同机制）。

## 七次排查（本地 `SAM3_CHECKPOINT` + 1038lab 权重：`BFloat16` vs `Float`）

- 冒烟：`segment_with_sam3` 在 `processor.set_image` → ViT MLP `fc2` 报 **`mat1 and mat2 must have the same dtype, but got BFloat16 and Float`**。
- 根因：**`sam3.perflib.fused.addmm_act`** 在推理时把 **fc1 的 matmul 输入/权重 cast 成 bfloat16**，输出 bf16 激活；**fc2** 仍是 **float32** `Linear`，dtype 不一致。与 checkpoint 是否第三方无关（1038lab 的 `.pt` 抽样为全 float32）。
- 修复：`autofigure2.py` 在本地 SAM 分支 import `build_sam3_image_model` 后调用 **`_ensure_sam3_vit_mlp_fp32_activations()`**，把 **`sam3.model.vitdet.addmm_act`** 替换为 **`_sam3_addmm_act_fp32`**（标准 `linear` + `F.gelu`，全 float32）。


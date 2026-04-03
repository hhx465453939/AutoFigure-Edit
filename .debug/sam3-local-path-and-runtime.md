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


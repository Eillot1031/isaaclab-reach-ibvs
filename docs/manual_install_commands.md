# Manual Isaac Sim Install Commands

## Purpose

当 `pip install isaacsim[...]` 在大 wheel 下载阶段反复断流时，先手动下载核心 wheel，再交给 `pip` 安装。

## Preconditions

- 当前环境：`env_isaaclab`
- Python 版本：`3.11`
- Workspace：`/home/krz/isaaclab_ws`

## Step 1 - Prepare folders

```bash
mkdir -p /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels
mkdir -p /home/krz/isaaclab_ws/outputs/pip_cache
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels
```

## Step 2 - Download the first blocking wheel with resume support

Preferred `wget` command:

```bash
wget -c \
  --tries=100 \
  --timeout=120 \
  --read-timeout=120 \
  https://pypi.nvidia.com/isaacsim-kernel/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

Fallback `curl` command:

```bash
curl -L -C - \
  --retry 100 \
  --retry-delay 5 \
  --max-time 0 \
  -o isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl \
  https://pypi.nvidia.com/isaacsim-kernel/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

## Step 3 - Optional additional core wheels

如果后续 `pip` 继续卡在别的 Isaac Sim wheel，可按同样模式单独下载：

```bash
wget -c https://pypi.nvidia.com/isaacsim/isaacsim-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-app/isaacsim_app-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-gui/isaacsim_gui-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-ros2/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-storage/isaacsim_storage-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-utils/isaacsim_utils-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-test/isaacsim_test-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-benchmark/isaacsim_benchmark-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
wget -c https://pypi.nvidia.com/isaacsim-asset/isaacsim_asset-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

## Step 3B - Batch-download common large Isaac Sim wheels

如果你已经确认网络对大 wheel 普遍不稳定，更高效的办法是先批量续传下载一批常见大包：

```bash
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels

BASE_URLS=(
  "https://pypi.nvidia.com/isaacsim-kernel/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-ros2/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-asset/isaacsim_asset-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-app/isaacsim_app-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-gui/isaacsim_gui-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-storage/isaacsim_storage-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-utils/isaacsim_utils-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-test/isaacsim_test-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-benchmark/isaacsim_benchmark-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
)

for url in "${BASE_URLS[@]}"; do
  echo "Downloading: $url"
  wget -c --tries=100 --timeout=120 --read-timeout=120 "$url"
done
```

如果你更想用 `curl`：

```bash
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels

BASE_URLS=(
  "https://pypi.nvidia.com/isaacsim-kernel/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-ros2/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-asset/isaacsim_asset-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-app/isaacsim_app-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-gui/isaacsim_gui-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-storage/isaacsim_storage-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-utils/isaacsim_utils-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-test/isaacsim_test-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
  "https://pypi.nvidia.com/isaacsim-benchmark/isaacsim_benchmark-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl"
)

for url in "${BASE_URLS[@]}"; do
  filename="$(basename "$url")"
  echo "Downloading: $filename"
  curl -L -C - --retry 100 --retry-delay 5 --max-time 0 -o "$filename" "$url"
done
```

说明：

- 这份列表不是保证覆盖 `isaacsim[all]` 的全部 wheel。
- 但它覆盖了目前已暴露出来和高度可疑的“首批大 wheel 瓶颈”。
- 批量预下载后，再回到 `pip install "isaacsim[all]==5.1.0"`，通常会比每次卡一个再补一个高效得多。

如果明确卡在 `isaacsim_ros2`，优先单独执行：

```bash
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels
wget -c \
  --tries=100 \
  --timeout=120 \
  --read-timeout=120 \
  https://pypi.nvidia.com/isaacsim-ros2/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

或：

```bash
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels
curl -L -C - \
  --retry 100 \
  --retry-delay 5 \
  --max-time 0 \
  -o isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl \
  https://pypi.nvidia.com/isaacsim-ros2/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

下载完成后先校验：

```bash
python -m zipfile -t /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
file /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

通过后再本地安装：

```bash
python -m pip install /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

## Step 4 - Install predownloaded wheel(s)

安装前先验证文件不是半截下载或错误页面：

```bash
ls -lh /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
python -m zipfile -t /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
file /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

如果 `python -m zipfile -t` 失败，说明 wheel 仍然损坏，需要继续续传或删掉后重新下载：

```bash
rm -f /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
cd /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels
wget -c \
  --tries=100 \
  --timeout=120 \
  --read-timeout=120 \
  https://pypi.nvidia.com/isaacsim-kernel/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

确认 wheel 有效后再安装：

```bash
conda activate env_isaaclab
python -m pip install /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl
```

如果你预先下载了多个 wheel，也可以一次性安装本地目录中的 wheel：

```bash
python -m pip install /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/*.whl
```

## Step 5 - Let pip resolve the remaining packages

```bash
python -m pip install "isaacsim[all]==5.1.0" \
  --index-url https://pypi.org/simple \
  --extra-index-url https://pypi.nvidia.com \
  --timeout 120 \
  --retries 20 \
  --resume-retries 20 \
  --cache-dir /home/krz/isaaclab_ws/outputs/pip_cache
```

如果你已经手动安装了一部分大 wheel，继续执行这条命令是合理的；它会把剩余未满足的依赖补齐。

## Step 6 - Minimal verification

```bash
python -c "import isaacsim; print('isaacsim import ok')"
```

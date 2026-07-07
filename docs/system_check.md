# System Check

## Scope

记录 Isaac Lab 安装前的系统检查结果。

## Summary

- Date: `2026-04-29`
- Workspace: `/home/krz/isaaclab_ws`
- Overall status: pass with one sandbox caveat
- Caveat:
  - `nvidia-smi` failed inside the sandbox but succeeded when re-run outside the sandbox

## Raw command results

### `pwd`

```text
/home/krz/isaaclab_ws
```

### `nvidia-smi` (sandbox)

```text
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that the latest NVIDIA driver is installed and running.
```

### `nvidia-smi` (outside sandbox)

```text
Wed Apr 29 18:11:01 2026
NVIDIA-SMI 580.95.05
Driver Version: 580.95.05
CUDA Version: 13.0
GPU 0: NVIDIA GeForce RTX 4090
Memory-Usage: 462MiB / 24564MiB
GPU-Util: 9%
Display active: On
```

### `python --version`

```text
Python 3.13.11
```

### `conda --version`

```text
conda 25.11.1
```

### `which python`

```text
/home/krz/miniconda3/bin/python
```

### `which pip`

```text
/home/krz/miniconda3/bin/pip
```

### `ldd --version`

```text
ldd (Ubuntu GLIBC 2.35-0ubuntu3.8) 2.35
```

### `df -h`

```text
/dev/nvme0n1p2  1.9T total, 413G used, 1.4T available, 24% used
```

### `free -h`

```text
Memory: 125Gi total, 6.5Gi used, 104Gi free, 117Gi available
Swap: 2.0Gi total, 0B used, 2.0Gi free
```

### `uname -a`

```text
Linux krz-Z890-UD-WIFI6E 6.8.0-90-generic #91~22.04.1-Ubuntu SMP PREEMPT_DYNAMIC Thu Nov 20 15:20:45 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
```

### `echo $CUDA_HOME`

```text

```

### `echo $LD_LIBRARY_PATH`

```text
/opt/ros/humble/opt/rviz_ogre_vendor/lib:/opt/ros/humble/lib/x86_64-linux-gnu:/opt/ros/humble/lib
```

## Assessment

1. RTX 4090 visible: yes
2. NVIDIA driver healthy: yes, confirmed outside sandbox
3. Disk capacity sufficient for Isaac Lab attempt: yes, about `1.4T` free on root filesystem
4. Memory capacity sufficient: yes, `125Gi` RAM with `117Gi` available at check time
5. Conda available: yes, `conda 25.11.1`
6. Base Python suitable for direct Isaac Lab install: no, current base is `Python 3.13.11`, so a dedicated `Python 3.11` env is still required
7. CUDA env vars complete: not fully preconfigured, `CUDA_HOME` is empty, but this does not block the planned dedicated-env installation path by itself

## Conclusion

- The machine appears suitable for a fresh Isaac Lab installation attempt.
- Proceed with a dedicated conda environment named `env_isaaclab`.
- Continue documenting any sandbox-specific behavior during install and verification.

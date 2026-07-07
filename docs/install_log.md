# Isaac Lab Installation Log

## Scope

记录 Isaac Lab 新路线相关的环境、依赖、安装、报错与修复过程。

## Constraints

- Use a dedicated conda environment for Isaac Lab
- Do not reuse `ibvs-sac`
- Do not install inside `/home/krz/IBVS SAC`
- Do not use `sudo pip`

## Entry 1 - Pre-install context

- Date: `2026-04-29`
- Workspace: `/home/krz/isaaclab_ws`
- Status: pre-install
- Notes:
  - Legacy IBVS-SAC pipeline is archived and frozen.
  - New route targets official Isaac Lab tasks, starting with `Isaac-Reach-Franka-v0`.
  - No package installation has been executed yet.

## Entry 2 - Pre-install system check

- Commands run:
  - `pwd`
  - `nvidia-smi`
  - `python --version`
  - `conda --version`
  - `which python`
  - `which pip`
  - `ldd --version`
  - `df -h`
  - `free -h`
  - `uname -a`
  - `echo $CUDA_HOME`
  - `echo $LD_LIBRARY_PATH`
- Notable results:
  - Sandbox `nvidia-smi` failed to communicate with the driver
  - Re-run outside sandbox succeeded and reported `NVIDIA GeForce RTX 4090`
  - Driver version: `580.95.05`
  - CUDA version reported by driver: `13.0`
  - Base Python: `3.13.11`
  - Conda: `25.11.1`
  - GLIBC: `2.35`
  - Free disk on `/`: about `1.4T`
  - Available memory: about `117Gi`
  - `CUDA_HOME` empty
  - `LD_LIBRARY_PATH` currently contains ROS-related paths
- Assessment:
  - Suitable to proceed with a dedicated conda environment
  - Do not install Isaac Lab into base because base Python is not the target version
  - Any GPU-sensitive checks may need sandbox-aware handling

## Entry 3 - First attempt to create `env_isaaclab`

- Command:
  - `conda create -n env_isaaclab python=3.11 -y`
- Result:
  - failed inside sandbox
- Error:

```text
NoWritableEnvsDirError: No writeable envs directories configured.
  - /home/krz/.conda/envs
  - /home/krz/miniconda3/envs
```

- Interpretation:
  - failure is caused by sandbox write restrictions on conda environment directories
  - this is not yet evidence of a package or version conflict
- Next action:
  - re-run `conda create` outside the sandbox and keep logging the outcome

## Entry 4 - `env_isaaclab` created successfully

- Command:
  - `conda create -n env_isaaclab python=3.11 -y` (outside sandbox)
- Result:
  - success
- Environment location:
  - `/home/krz/miniconda3/envs/env_isaaclab`
- Verification commands:
  - `conda run -n env_isaaclab python --version`
  - `conda run -n env_isaaclab which python`
  - `conda run -n env_isaaclab pip --version`
- Verification results:
  - `Python 3.11.15`
  - `/home/krz/miniconda3/envs/env_isaaclab/bin/python`
  - `pip 26.0.1` from the new environment

## Entry 5 - Official installation references consulted

- Reference date checked: `2026-04-29`
- Sources:
  - Isaac Lab install doc: `https://isaac-sim.github.io/IsaacLab/main/source/setup/installation/pip_installation.html`
  - Isaac Sim Python install doc: `https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html`
  - Isaac Lab RL scripts doc: `https://isaac-sim.github.io/IsaacLab/release/2.3.0/source/overview/reinforcement-learning/rl_existing_scripts.html`
- Key points extracted from official docs:
  - Isaac Sim 5.x requires Python `3.11`
  - Upgrade `pip` before install
  - Install Isaac Sim pip packages using `isaacsim[all,extscache]==5.1.0`
  - Install CUDA-enabled PyTorch for Linux x86_64 with `torch==2.7.0` and `torchvision==0.22.0` from `cu128`
  - Clone official `IsaacLab` repository and run `./isaaclab.sh --install`
  - `./isaaclab.sh -i rsl_rl` is the official path for RSL-RL support

## Entry 6 - Installation phase started

- Commands started:
  - `conda run -n env_isaaclab python -m pip install --upgrade pip`
  - `conda run -n env_isaaclab python -m pip install -U torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128`
  - `git clone https://github.com/isaac-sim/IsaacLab.git`
- Completed result so far:
  - `pip` upgrade succeeded from `26.0.1` to `26.1`
- In-progress observations:
  - PyTorch install is long-running with buffered output under `conda run`
  - Process inspection confirms active HTTPS downloads and temporary wheel writes in `/tmp`
  - Observed temporary CUDA wheel downloads include `nvidia_cuda_nvrtc_cu12` and `nvidia_cudnn_cu12`
  - Official `IsaacLab` clone has started and is still running
- Current status:
  - installation is still in progress
  - no package conflict or version error has been reported yet

## Entry 7 - Long-running download bottleneck

- Observation window:
  - roughly `18:15` to `19:13` local time on `2026-04-29`
- Current blocking step:
  - `conda run -n env_isaaclab python -m pip install -U torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128`
- Evidence collected:
  - process remained alive for at least `~58 minutes`
  - process state stayed `Sl`
  - `lsof` repeatedly showed active HTTPS connections
  - temporary wheel writes continued to grow over time
- Sampled temporary wheel growth:
  - `nvidia_cuda_nvrtc_cu12` observed around `84M`
  - `nvidia_cudnn_cu12` observed around `46M`
  - later `nvidia_cudnn_cu12` observed around `144M`
  - later `nvidia_cudnn_cu12` observed around `185M`
  - later `nvidia_cudnn_cu12` observed around `284M`
  - later `nvidia_cudnn_cu12` observed around `359M`
- Parallel repo preparation:
  - `git clone https://github.com/isaac-sim/IsaacLab.git` also remained in progress
  - partial directory size sampled around `74M`
  - `git-remote-https` retained an established HTTPS connection during sampling
- Interpretation:
  - current blocker is slow network throughput and large package size
  - there is still no concrete version-conflict or dependency-resolution failure to fix yet
- Downstream impact:
  - `isaacsim[all,extscache]==5.1.0` installation has not started yet
  - `./isaaclab.sh --install` has not started yet

## Entry 8 - Local `environment.yml` prepared for manual install

- File created:
  - `/home/krz/isaaclab_ws/environment.yml`
- Purpose:
  - let the user create `env_isaaclab` locally without reusing `ibvs-sac`
  - pin the main versions needed for the current Isaac Lab route
- Included versions:
  - `python=3.11`
  - `torch==2.7.0`
  - `torchvision==0.22.0`
  - `isaacsim[all,extscache]==5.1.0`
- Notes:
  - PyTorch wheels are sourced from the `cu128` wheel index through `--extra-index-url`
  - CUDA toolkit is not installed as a separate conda package in this file
  - the targeted GPU-compatible stack is the official pip-style route previously recorded in this log

## Entry 9 - Mirror strategy for faster installation

- Reference date checked: `2026-04-29`
- Sources:
  - TUNA PyPI help: `https://mirrors.tuna.tsinghua.edu.cn/help/pypi/`
  - TUNA Anaconda help: `https://mirrors.tuna.tsinghua.edu.cn/help/anaconda/`
  - USTC PyPI help: `https://mirrors.ustc.edu.cn/help/pypi.html`
  - USTC Anaconda help: `https://mirrors.ustc.edu.cn/help/anaconda.html`
- Practical conclusion:
  - `conda` metadata and base packages can usually be accelerated by TUNA or USTC
  - normal `pip` packages can also be accelerated by switching `index-url`
  - this project still needs `https://download.pytorch.org/whl/cu128` for CUDA PyTorch wheels
  - `IsaacLab` source clone comes from GitHub and is not automatically accelerated by `conda` / `pip` mirrors
- Recommended usage:
  - use a mirror for `conda` and default `pip`
  - keep the official PyTorch CUDA wheel index as an additional source
  - keep `git clone https://github.com/isaac-sim/IsaacLab.git` as the default safe clone command

## Entry 10 - Switched to a two-stage environment install

- File updated:
  - `/home/krz/isaaclab_ws/environment.yml`
- Change made:
  - removed `torch==2.7.0` and `torchvision==0.22.0` from `environment.yml`
  - removed the embedded `--extra-index-url https://download.pytorch.org/whl/cu128`
- Reason:
  - CUDA PyTorch wheels are the slowest and most network-sensitive part
  - installing them separately makes retries easier and keeps the base environment cleaner
- New recommended split:
  - Stage A: create `env_isaaclab` from `environment.yml`
  - Stage B: activate `env_isaaclab` and install CUDA PyTorch explicitly with the official `cu128` index plus a domestic mirror as fallback
- Target versions kept:
  - `python=3.11`
  - `isaacsim[all,extscache]==5.1.0`
  - `torch==2.7.0`
  - `torchvision==0.22.0`

## Entry 11 - Analysis of official-source install strategy for `isaacsim[all,extscache]==5.1.0`

- Date: `2026-05-07`
- User goal:
  - switch back to official upstream sources instead of domestic mirrors
  - increase the timeout/retry tolerance for failed downloads
  - avoid restarting fully from zero on each interrupted download
- Analysis:
  - Item 1: effective, but only partially
    - Switching back to the official source can help if mirrors are stale, throttled, or unstable for this package set.
    - It does not guarantee faster throughput; it mainly reduces mirror-specific inconsistency risk.
  - Item 2: effective
    - `pip` supports configurable timeout and retry behavior.
    - Increasing timeout and retry counts is useful for large wheels and unstable long-lived HTTPS transfers.
  - Item 3: partially effective, with an important nuance
    - `pip` caches downloads by default and newer pip versions support resumed/restarted incomplete downloads via `--resume-retries`.
    - However, resumability still depends on the server response and the specific file transfer state.
    - So this can improve behavior, but it is not a hard guarantee that every broken large file will always continue from the exact byte offset.
- Recommended strategy:
  - use official `pypi.org` as the primary package index
  - keep pip cache enabled
  - set an explicit persistent cache directory inside the workspace if desired
  - use `pip download` first to build a local wheelhouse
  - re-run the same `pip download` command until complete
  - then install from the local wheelhouse with `--no-index --find-links`
- Benefit of the two-step flow:
  - once a dependency file is fully downloaded into the wheelhouse or cache, installation no longer depends on the network
  - repeated attempts focus on the still-missing files instead of redoing the full install path

## Entry 12 - Why `Preparing metadata (pyproject.toml)` appears to hang

- Date: `2026-05-07`
- Observed command:
  - `python -m pip download "isaacsim[all,extscache]==5.1.0" ...`
- Observed output:
  - `isaacsim-5.1.0.0.tar.gz` downloaded
  - `isaacsim_kernel-5.1.0.0.tar.gz` downloaded
  - process appeared to stay at `Preparing metadata (pyproject.toml)`
- Cause analysis:
  - the `isaacsim` packages fetched from `pypi.org` are tiny source wrappers, not the full simulator payload
  - during metadata/build preparation, pip is still resolving package requirements and package locations
  - the official Isaac Sim installation flow requires `--extra-index-url https://pypi.nvidia.com`
  - if only `https://pypi.org/simple` is provided, pip can stay in a long dependency-resolution / metadata phase before it finally fails or times out
  - therefore the apparent “hang” is usually network-bound resolution work, not a completed local metadata step
- Practical conclusion:
  - for Isaac Sim, official PyPI alone is not the complete source
  - `pypi.nvidia.com` must be included as the extra index when downloading or installing

## Entry 13 - `IncompleteRead` during `isaacsim-kernel` wheel download

- Date: `2026-05-07`
- Command attempted in `env_isaaclab`:
  - `python -m pip download "isaacsim[all,extscache]==5.1.0" --dest /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels --index-url https://pypi.org/simple --extra-index-url https://pypi.nvidia.com --timeout 120 --retries 20 --resume-retries 20 --cache-dir /home/krz/isaaclab_ws/outputs/pip_cache`
- Observed progress:
  - `isaacsim-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl` started successfully
  - `isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl` reached about `9.2 / 64.3 MB`
- Final error:

```text
ProtocolError: ('Connection broken: IncompleteRead(9185838 bytes read, 55094683 more expected)', IncompleteRead(...))
```

- Interpretation:
  - this is a mid-stream HTTPS connection break, not a version mismatch
  - `--timeout` helps with slow responses, but it does not prevent the server or network path from abruptly closing the transfer
  - `--retries` and `--resume-retries` do not guarantee transparent recovery for every partially transferred wheel in one resolver pass
  - pip may still need the user to re-run the same command so cache and already-complete files can be reused
- More robust next step:
  - prefer downloading one large wheel at a time with the exact filename when possible
  - alternatively keep rerunning the same `pip download` command against the same `--dest` and `--cache-dir`
  - if repeated breakage continues, use a resumable downloader such as `wget -c` or `curl -C -` on the direct wheel URL after discovering that URL

## Entry 14 - Switched to a smaller-step official install plan

- Date: `2026-05-07`
- Reason for switching:
  - repeated failures while trying to fetch `isaacsim[all,extscache]==5.1.0` as a single large dependency set
- Official basis:
  - NVIDIA docs list `all` and `extscache` as separable bundle options for Isaac Sim pip installation
- New plan:
  - Stage A: install `isaacsim[all]==5.1.0` only
  - Stage B: verify `import isaacsim`
  - Stage C: install `isaacsim[extscache]==5.1.0` later only if needed
- Why this is better:
  - reduces the amount of data and dependency fan-out in the first critical install step
  - gets the main Isaac Sim Python package stack working earlier
  - postpones optional extension-cache payloads that are large and network-sensitive
- Practical note:
  - `extscache` helps avoid future on-demand Omniverse extension downloads, but it is not the first thing needed to prove the Isaac Lab baseline

## Entry 15 - Switched from pip-managed large-wheel download to resumable direct download

- Date: `2026-05-07`
- Trigger:
  - repeated failures on `isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl (64.3 MB)`
- New strategy:
  - do not let `pip` handle the fragile first large transfer
  - use a resumable downloader first for the direct NVIDIA wheel URL
  - store wheels in a local wheelhouse under `outputs/pip_downloads/isaacsim_wheels`
  - then ask `pip` to install from local files
- Why:
  - `wget -c` and `curl -C -` are more explicit and reliable for interrupted large-file transfer recovery
  - this isolates the current bottleneck from pip's resolver

## Entry 16 - Prepared manual direct-wheel command list

- File created:
  - `/home/krz/isaaclab_ws/docs/manual_install_commands.md`
- Included content:
  - resumable direct download commands for `isaacsim_kernel`
  - optional direct download commands for several core Isaac Sim wheels listed on `pypi.nvidia.com`
  - local wheel install commands
  - follow-up `pip install "isaacsim[all]==5.1.0"` command for remaining dependency resolution

## Entry 17 - Invalid `isaacsim-kernel` wheel during local install

- Date: `2026-05-07`
- User command:
  - `python -m pip install /home/krz/isaaclab_ws/outputs/pip_downloads/isaacsim_wheels/*.whl`
- Result:
  - `isaacsim`, `isaacsim_app`, `isaacsim_benchmark`, `isaacsim_gui` began processing
  - `isaacsim_kernel-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl` was rejected as invalid
- Interpretation:
  - this strongly suggests the wheel file is corrupted or incomplete
  - common causes are interrupted download, partially resumed file, or an unexpected non-wheel response saved with a `.whl` filename
- Recommended validation:
  - `python -m zipfile -t <wheel>`
  - `file <wheel>`
  - compare file size against expected download size
- Recommended fix:
  - delete the invalid local `isaacsim_kernel` wheel
  - re-download it with `wget -c` or `curl -C -`
  - validate the wheel before retrying `pip install`

## Entry 18 - New bottleneck moved to `isaacsim-ros2`

- Date: `2026-05-07`
- User command:
  - `python -m pip install "isaacsim[all]==5.1.0" --index-url https://pypi.org/simple --extra-index-url https://pypi.nvidia.com --timeout 120 --retries 20 --resume-retries 20 --cache-dir /home/krz/isaaclab_ws/outputs/pip_cache`
- Observed bottleneck:
  - `isaacsim_ros2-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl (105.4 MB)`
  - download stalled around `23.0 / 105.4 MB`
- Interpretation:
  - this confirms the current problem pattern is not specific to `isaacsim-kernel`
  - any 100 MB class Isaac Sim wheel can become the next fragile network bottleneck
- Recommended action:
  - treat `isaacsim_ros2` exactly like `isaacsim_kernel`
  - manually resumable-download it first
  - validate it locally
  - install the local wheel
  - then let pip continue resolving the remaining packages

## Entry 19 - Decided to batch predownload common large wheels

- Date: `2026-05-07`
- New bottleneck observed:
  - `isaacsim_asset-5.1.0.0-cp311-none-manylinux_2_35_x86_64.whl (31.2 MB)`
- Conclusion:
  - the install is now repeatedly exposing one large wheel at a time
  - continuing with a single-wheel reactive workflow is inefficient
- New recommendation:
  - batch predownload a curated set of common large Isaac Sim wheels with resumable commands
  - then let pip resolve the remaining smaller or not-yet-seen dependencies

## Entry 20 - Isaac Sim and PyTorch installation confirmed

- Date: `2026-05-07`
- User-reported successful installs:
  - `isaacsim[all]==5.1.0`
  - CUDA-enabled `torch`
- User-reported verification commands:
  - `python -c "import isaacsim; print('isaacsim import ok')"`
  - `python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"`
- User-reported result:
  - `isaacsim` import works
  - `torch` import works
  - CUDA is available to PyTorch
- Conclusion:
  - the environment has passed the key installation gate needed to continue with Isaac Lab source setup
  - no post-install verification or training step can run until this download stage completes

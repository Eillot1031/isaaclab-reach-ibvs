# IsaacLab Reach-IBVS: SAC-based Visual Servoing Controller

> 基于 NVIDIA Isaac Lab 与 Franka 机械臂的视觉伺服控制器实验项目。项目将视觉伺服任务建模为连续控制强化学习问题，使用 Soft Actor-Critic（SAC）学习从视觉/状态误差到机械臂控制动作的闭环策略，并通过训练曲线、奖励消融、鲁棒性测试和动作空间对比验证控制效果。

<p align="center">
  <img src="assets/sac_round37_side_demo.gif" width="48%" alt="SAC R37 side view demo"/>
  <img src="assets/tracking_demo_r37.gif" width="48%" alt="Tracking demo"/>
</p>

## Highlights

- Isaac Lab + Franka 机械臂仿真环境
- SAC（SKRL backend）连续控制训练流程
- IK-Rel task-space incremental action space
- TanhSquashing + AlphaClamp + CosineAnnealingLR 训练稳定化
- 稠密奖励 + 稀疏成功奖励 + 姿态/动作平滑约束
- 支持训练、评估、视频录制、消融实验、鲁棒性实验和动作空间对比实验

## Project Overview

传统图像基视觉伺服（IBVS）通常依赖交互矩阵、深度估计和局部线性化，在大初始偏差、视野约束和关节限位条件下容易出现收敛域受限或控制不稳定的问题。本项目尝试使用深度强化学习方法学习视觉伺服控制策略，将图像/任务空间误差与机械臂状态作为观测，将连续动作作为策略输出，使控制器通过仿真交互自动学习目标趋近、姿态调整和稳定控制行为。

最终主模型采用 `Isaac-Reach-Franka-IK-Rel-v0` 任务配置，策略输出 6 维末端相对位姿增量：

```text
a = [dx, dy, dz, droll, dpitch, dyaw]
```

底层由差分 IK 负责关节级求解，使策略主要学习任务空间误差修正方向，而不是直接学习复杂的关节空间逆运动学映射。

## Repository Structure

```text
.
├── IsaacLab/                         # Isaac Lab source tree with project modifications
│   ├── scripts/reinforcement_learning/skrl/train.py
│   └── source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/reach/
│       ├── reach_env_cfg.py           # reward, command, termination and curriculum settings
│       ├── mdp/rewards.py             # custom reward terms, e.g. reach_success_bonus
│       └── config/franka/
│           ├── ik_rel_env_cfg.py      # IK-Rel task-space action configuration
│           ├── joint_pos_env_cfg.py
│           ├── vs_env_cfg.py
│           └── agents/skrl_sac_cfg.yaml
├── scripts/
│   ├── play_view.py                   # R37 / IK-Rel policy evaluation and video recording
│   ├── play_vs.py                     # VS variants evaluation and recording
│   ├── play_tracking_demo.py          # continuous target tracking demo
│   ├── play_singularity_test.py       # 180-degree singularity stress test
│   ├── sac_tanh_squashing.py          # SAC tanh squashing and alpha clamp utilities
│   ├── plot_skrl_metrics.py           # TensorBoard scalar plotting
│   ├── select_best_checkpoint.py      # select best checkpoint from SKRL logs
│   ├── run_ablation.sh                # reward ablation training runner
│   ├── eval_ablations_50k.sh          # reward ablation evaluation runner
│   ├── exp3_robustness_eval.py        # robustness evaluation
│   └── exp4_action_space_comparison.py
├── docs/
│   ├── progress_log.md                # full development and experiment log
│   ├── install_log.md
│   ├── experiment_log.md
│   └── system_check.md
├── assets/                            # README figures and GIF demos
├── environment.yml
└── README.md
```

## Environment

The project was developed and tested on the following local setup:

| Item | Version / Configuration |
|---|---|
| OS | Ubuntu 22.04 |
| GPU | NVIDIA GeForce RTX 4090 24GB |
| NVIDIA Driver | 580.95.05 |
| Python env | Conda env `env_isaaclab`, Python 3.11 |
| Isaac Sim | 5.1.0 pip package route |
| Isaac Lab | Local `IsaacLab/` source tree |
| PyTorch | 2.7.0, CUDA 12.8 wheels |
| RL backend | SKRL SAC |

> Note: this repository currently contains a local Isaac Lab source tree with task/config modifications. For long-term maintenance, it is recommended to separate this project into an Isaac Lab external extension or use Isaac Lab as a submodule.

## Installation

Create and activate the conda environment:

```bash
conda create -n env_isaaclab python=3.11 -y
conda activate env_isaaclab
python -m pip install --upgrade pip
```

Install CUDA PyTorch:

```bash
python -m pip install -U torch==2.7.0 torchvision==0.22.0 \
  --index-url https://download.pytorch.org/whl/cu128
```

Install Isaac Sim and Isaac Lab dependencies:

```bash
python -m pip install "isaacsim[all,extscache]==5.1.0" \
  --index-url https://pypi.org/simple \
  --extra-index-url https://pypi.nvidia.com

cd IsaacLab
./isaaclab.sh --install
./isaaclab.sh -i skrl
```

Basic verification:

```bash
conda activate env_isaaclab
python -c "import torch; print(torch.cuda.is_available())"
python -c "import isaacsim; print('isaacsim import ok')"
```

## Training

### Smoke training

A short run can be used to check whether the pipeline works:

```bash
cd /home/krz/isaaclab_ws/IsaacLab
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
  scripts/reinforcement_learning/skrl/train.py \
  --task Isaac-Reach-Franka-IK-Rel-v0 \
  --headless \
  --num_envs 128 \
  --algorithm SAC \
  --max_iterations 500
```

### Main R37 training

The main reported model was trained with:

```bash
cd /home/krz/isaaclab_ws/IsaacLab
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
  scripts/reinforcement_learning/skrl/train.py \
  --task Isaac-Reach-Franka-IK-Rel-v0 \
  --headless \
  --num_envs 512 \
  --algorithm SAC \
  --max_iterations 50000 \
  2>&1 | tee /home/krz/isaaclab_ws/outputs/logs/formal_train_sac_round37.log
```

Main training configuration:

| Item | Value |
|---|---:|
| Algorithm | SKRL SAC |
| Task | `Isaac-Reach-Franka-IK-Rel-v0` |
| Timesteps | 400,000 |
| Max iterations | 50,000 |
| Rollouts | 8 |
| Parallel envs | 512 |
| Network | `[512, 256, 128]` |
| Batch size | 1024 |
| Alpha clamp | 0.01 |
| LR schedule | CosineAnnealingLR, `5e-4 -> 1e-5` |
| Training time | about 151 min on RTX 4090 |

Training outputs are saved under:

```text
IsaacLab/logs/skrl/reach_franka_sac/<timestamp>_sac_torch/
├── checkpoints/
│   ├── agent_*.pt
│   └── best_agent.pt
└── events.out.tfevents.*
```

## Plot Training Curves

```bash
conda run -n env_isaaclab python /home/krz/isaaclab_ws/scripts/plot_skrl_metrics.py \
  --log_dir /home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac/<timestamp>_sac_torch
```

Expected output:

```text
<run_dir>/plots/training_metrics.png
<run_dir>/plots/episode_reward.png
<run_dir>/plots/critic_loss.png
<run_dir>/plots/actor_loss.png
<run_dir>/plots/alpha.png
```

## Evaluation

Evaluate a trained checkpoint for 10 episodes:

```bash
cd /home/krz/isaaclab_ws/IsaacLab
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
  /home/krz/isaaclab_ws/scripts/play_view.py \
  --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
  --headless \
  --num_envs 4 \
  --algorithm SAC \
  --num_episodes 10 \
  --checkpoint /home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac/<timestamp>_sac_torch/checkpoints/best_agent.pt
```

Record a perspective-view video:

```bash
cd /home/krz/isaaclab_ws/IsaacLab
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
  /home/krz/isaaclab_ws/scripts/play_view.py \
  --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
  --checkpoint /home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac/<timestamp>_sac_torch/checkpoints/best_agent.pt \
  --num_envs 1 \
  --headless \
  --num_episodes 10 \
  --algorithm SAC \
  --video \
  --view perspective \
  --hold_pos_threshold 0.025 \
  --hold_image_threshold 0
```

Record the continuous tracking demo:

```bash
cd /home/krz/isaaclab_ws/IsaacLab
OMNI_KIT_ACCEPT_EULA=YES conda run -n env_isaaclab python \
  /home/krz/isaaclab_ws/scripts/play_tracking_demo.py \
  --task Isaac-Reach-Franka-IK-Rel-Play-v0 \
  --checkpoint /home/krz/isaaclab_ws/IsaacLab/logs/skrl/reach_franka_sac/<timestamp>_sac_torch/checkpoints/best_agent.pt \
  --num_envs 1 \
  --headless \
  --algorithm SAC \
  --total_steps 600 \
  --traj_freq 120 \
  --hold_pos_threshold 0.025 \
  --hold_image_threshold 0
```

## Results

### Main Result

| Metric | Result |
|---|---:|
| Mean Return, 10 episodes | **+15.6599 ± 0.5332** |
| Min Return | **+14.9901** |
| Max Return | **+16.4132** |
| Per-step reward | **+0.0435** |
| Average position error | **3.5 cm** |
| `reach_success` | **73.7%** |

The final policy achieves stable target-reaching behavior in the Isaac Lab Franka environment. The sparse `reach_success` term grows from nearly 0 at the beginning of training to 73.7%, indicating that the policy spends most of the later episode near the target region.

![R37 training detail](assets/exp1_r37_training_detail.png)

![Reach success trajectory](assets/exp1_reach_success_trajectory.png)

### Cross-round Training Evolution

| Round | Action Space | Mean Return | Average Position Error | Key Change |
|---|---|---:|---:|---|
| R29 | JointPos | -1.63 | ~22 cm | baseline training |
| R32 | JointPos | -1.10 | ~19 cm | LR schedule + alpha clamp |
| R35 | JointPos | -0.97 | ~21 cm | long training |
| R36 | IK-Rel | +3.31 | ~8 cm | switch to IK-Rel |
| R37 | IK-Rel | **+15.66** | **~3.5 cm** | success bonus + 12s resampling + orientation weight |

![Cross-round evaluation](assets/exp1_cross_round_eval_bar.png)

### Reward Ablation

| Variant | Description | Mean Return |
|---|---|---:|
| A0 | Full model | **+15.66** |
| A1 | Remove success bonus | -0.72 |
| A2 | Remove orientation tracking | -2.74 |
| A3 | Remove action penalties | -0.76 |
| A4 | Position tracking only | -2.13 |

![Reward ablation](assets/exp2_ablation_eval_bar.png)

### Robustness Evaluation

The trained policy is robust to moderate observation noise, initial pose distribution expansion, and action execution error. The main weakness is out-of-distribution workspace extrapolation.

![Robustness grid](assets/exp3_robustness_grid.png)

### Action-space Comparison

IK-Rel significantly outperforms the joint-space baseline. In the action-space comparison, JointPace reaches about 19 cm average position error, while IK-Rel reaches about 3.5 cm.

![Action-space evaluation](assets/exp4_action_space_eval_comparison.png)

## Demo Videos

The following files are provided as lightweight README assets:

```text
assets/sac_round37_side_demo.gif
assets/tracking_demo_r37.gif
assets/sac_round37_side_demo.mp4
assets/tracking_demo_r37.mp4
```

For GitHub README display, GIFs are used directly. Larger MP4 files can be placed under GitHub Releases if repository size becomes a concern.

## Reproducibility Notes

- `best_agent.pt` is not included by default if model checkpoints are too large. Put trained checkpoints under `IsaacLab/logs/skrl/reach_franka_sac/<run>/checkpoints/`, or upload them to GitHub Releases and link them here.
- `outputs/`, `logs/`, `wandb/`, cache folders, and temporary videos should normally be ignored by Git.
- If the repository is intended for long-term public use, consider converting the custom task into a standalone Isaac Lab extension rather than committing the full Isaac Lab source tree.

## Recommended `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/

# Isaac Lab / training outputs
outputs/
logs/
wandb/
runs/
*.pt
*.pth
*.ckpt

# Temporary materials
readme_materials/
*.zip

# Large media: keep only selected README assets
*.avi
*.mov
```

## Acknowledgements

This project is built on NVIDIA Isaac Sim / Isaac Lab and uses SKRL for SAC-based reinforcement learning. The task design follows the visual servoing setting with Franka manipulation in Isaac Lab.

# Isaac Lab Pipeline Plan

## Stage 0 - 系统检查与环境搭建

- 确认 GPU / driver / disk / memory / Python / conda / CUDA 相关环境变量
- 建立独立目录与记录文档
- 创建专用 conda 环境 `env_isaaclab`

## Stage 1 - Isaac Lab 安装与官方验证

- 按官方 quickstart 安装 CUDA 版 PyTorch
- 安装 Isaac Sim pip packages
- clone 官方 `IsaacLab`
- 执行 `./isaaclab.sh --install`
- 做 import 与 list envs 基础验证

## Stage 2 - Isaac-Reach-Franka-v0 smoke training

- 安装 `rsl_rl`
- 使用官方训练脚本启动 headless smoke training
- 从较小 `num_envs` 开始，确认日志、训练启动、checkpoint 输出

## Stage 3 - checkpoint play / video

- 使用实际生成的 checkpoint 路径运行官方 play
- 必要时使用 headless video 模式录制短视频
- 记录默认 logs 路径与输出位置

## Stage 4 - 短程正式训练准备

- 根据 smoke 结果评估稳定性、显存、吞吐
- 选择更合适的 `num_envs` 和短程训练配置
- 保持 headless 训练为默认模式

## Stage 5 - 必要时再做最小修改

- 仅在官方 baseline 已跑通后，再评估是否需要最小配置调整
- 第一阶段禁止迁移旧 reward、旧 SAC、旧 D-H、旧 PyBullet viewer

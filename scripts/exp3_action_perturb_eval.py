#!/usr/bin/env python3
"""Action perturbation robustness test.

Multiplies agent actions by (1 + epsilon) where epsilon ~ Uniform[-delta, delta].
"""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Action perturbation eval.")
parser.add_argument("--num_envs", type=int, default=4)
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-IK-Rel-Play-v0")
parser.add_argument("--checkpoint", type=str, required=True)
parser.add_argument("--num_episodes", type=int, default=10)
parser.add_argument("--delta", type=float, required=True, help="Action perturbation delta")
parser.add_argument("--algorithm", type=str, default="SAC")
parser.add_argument("--ml_framework", type=str, default="torch")
parser.add_argument("--agent", type=str, default=None)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
args_cli.headless = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import os
import random
import statistics

import gymnasium as gym
import skrl
import torch
from packaging import version

SKRL_VERSION = "2.0.0"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    exit()

from skrl.utils.runner.torch import Runner
from isaaclab.envs import ManagerBasedRLEnvCfg, DirectRLEnvCfg, DirectMARLEnvCfg
from isaaclab_rl.skrl import SkrlVecEnvWrapper
import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils.hydra import hydra_task_config

if args_cli.agent is None:
    algorithm = args_cli.algorithm.lower()
    agent_cfg_entry_point = f"skrl_{algorithm}_cfg_entry_point"
else:
    agent_cfg_entry_point = args_cli.agent
    algorithm = agent_cfg_entry_point.split("_cfg")[0].split("skrl_")[-1].lower()


def _steps_per_episode(env_cfg):
    return int(env_cfg.episode_length_s / (env_cfg.sim.dt * env_cfg.decimation))


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device else env_cfg.sim.device
    experiment_cfg["seed"] = 42
    env_cfg.seed = 42

    resume_path = os.path.abspath(args_cli.checkpoint)

    env = gym.make(args_cli.task, cfg=env_cfg)
    env_skrl = SkrlVecEnvWrapper(env, ml_framework=args_cli.ml_framework)

    experiment_cfg["trainer"]["close_environment_at_exit"] = False
    experiment_cfg["agent"]["experiment"]["write_interval"] = 0
    experiment_cfg["agent"]["experiment"]["checkpoint_interval"] = 0
    _off_policy = {"sac", "ddpg", "td3"}
    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        experiment_cfg["agent"].pop("rollouts", None)
    runner = Runner(env_skrl, experiment_cfg)

    if experiment_cfg.get("agent", {}).get("class", "").lower() in _off_policy:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        from sac_tanh_squashing import apply_tanh_squashing, apply_alpha_clamp
        apply_tanh_squashing(runner.agent.policy)
        apply_alpha_clamp(runner.agent, alpha_min=0.01)

    runner.agent.load(resume_path)
    runner.agent.enable_training_mode(False, apply_to_models=True)

    obs, _ = env_skrl.reset()
    states = env_skrl.state()
    n_envs = env_cfg.scene.num_envs
    episode_rewards = torch.zeros(n_envs, device=obs.device)
    episode_returns = []
    steps_per_ep = _steps_per_episode(env_cfg)
    delta = args_cli.delta

    print(f"\n{'='*60}")
    print(f"  Action Perturbation Test: delta={delta}")
    print(f"{'='*60}")

    timestep = 0
    while simulation_app.is_running():
        with torch.inference_mode():
            outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
            actions = outputs[-1].get("mean_actions", outputs[0])

            if delta > 0:
                noise = torch.empty_like(actions).uniform_(-delta, delta)
                actions = actions * (1 + noise)

            obs, rewards, terminated, truncated, infos = env_skrl.step(actions)
            states = env_skrl.state()

        episode_rewards += rewards.squeeze(-1) if rewards.dim() > 1 else rewards
        timestep += 1

        dones = (terminated | truncated).squeeze(-1) if terminated.dim() > 1 else (terminated | truncated)
        done_indices = dones.nonzero(as_tuple=False).squeeze(-1)

        if done_indices.numel() > 0:
            for idx in done_indices:
                ep_ret = episode_rewards[idx.item()].item()
                episode_returns.append(ep_ret)
                print(f"  Episode {len(episode_returns)} | Return: {ep_ret:+.4f}")
                episode_rewards[idx.item()] = 0.0

        if len(episode_returns) >= args_cli.num_episodes:
            break
        if timestep > args_cli.num_episodes * steps_per_ep * 2:
            break

    returns = episode_returns[:args_cli.num_episodes]
    if returns:
        mean_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.0
        print(f"\n{'='*60}")
        print(f"  Evaluation Summary ({len(returns)} episodes)")
        print(f"  Mean Return : {mean_ret:+.4f} +/- {std_ret:.4f}")
        print(f"  Min  Return : {min(returns):+.4f}")
        print(f"  Max  Return : {max(returns):+.4f}")
        print(f"{'='*60}\n")

    env_skrl.close()


if __name__ == "__main__":
    main()
    simulation_app.close()

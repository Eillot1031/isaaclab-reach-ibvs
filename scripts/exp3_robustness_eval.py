#!/usr/bin/env python3
"""Experiment 3: Robustness verification for Round 37 model.

Tests the trained SAC policy under observation noise, initial pose variation,
action perturbation, and workspace expansion -- all eval-only, no retraining.
"""

"""Launch Isaac Sim first."""
import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Robustness evaluation.")
parser.add_argument("--num_envs", type=int, default=4)
parser.add_argument("--task", type=str, default="Isaac-Reach-Franka-IK-Rel-Play-v0")
parser.add_argument("--checkpoint", type=str, required=True)
parser.add_argument("--num_episodes", type=int, default=10)
parser.add_argument("--ml_framework", type=str, default="torch")
parser.add_argument("--algorithm", type=str, default="SAC")
parser.add_argument(
    "--test_type", type=str, required=True,
    choices=["noise", "init_pose", "action_perturb", "workspace"],
    help="Type of robustness test to run."
)
parser.add_argument(
    "--agent", type=str, default=None,
)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
args_cli.headless = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import json
import os
import random
import statistics

import gymnasium as gym
import skrl
import torch
from packaging import version

SKRL_VERSION = "2.0.0"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    skrl.logger.error(f"Unsupported skrl version: {skrl.__version__}")
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


def get_test_conditions(test_type):
    if test_type == "noise":
        return [
            {"label": "0.00", "noise_range": 0.0},
            {"label": "0.01", "noise_range": 0.01},
            {"label": "0.02", "noise_range": 0.02},
            {"label": "0.05", "noise_range": 0.05},
            {"label": "0.10", "noise_range": 0.10},
            {"label": "0.20", "noise_range": 0.20},
        ]
    elif test_type == "init_pose":
        return [
            {"label": "(0.5,1.5)", "pos_range": (0.5, 1.5)},
            {"label": "(0.3,1.7)", "pos_range": (0.3, 1.7)},
            {"label": "(0.1,1.9)", "pos_range": (0.1, 1.9)},
            {"label": "(0.0,2.0)", "pos_range": (0.0, 2.0)},
        ]
    elif test_type == "action_perturb":
        return [
            {"label": "0.00", "delta": 0.0},
            {"label": "0.05", "delta": 0.05},
            {"label": "0.10", "delta": 0.10},
            {"label": "0.20", "delta": 0.20},
            {"label": "0.30", "delta": 0.30},
        ]
    elif test_type == "workspace":
        return [
            {"label": "Default", "ranges": {"pos_x": (0.35, 0.65), "pos_y": (-0.2, 0.2), "pos_z": (0.15, 0.5)}},
            {"label": "Expanded-1", "ranges": {"pos_x": (0.25, 0.75), "pos_y": (-0.3, 0.3), "pos_z": (0.10, 0.60)}},
            {"label": "Expanded-2", "ranges": {"pos_x": (0.15, 0.85), "pos_y": (-0.4, 0.4), "pos_z": (0.05, 0.70)}},
        ]


def apply_condition(env_cfg, test_type, condition):
    """Modify env_cfg in-place based on the test condition."""
    if test_type == "noise":
        noise_val = condition["noise_range"]
        from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
        if noise_val == 0.0:
            env_cfg.observations.policy.joint_pos.noise = None
            env_cfg.observations.policy.joint_vel.noise = None
        else:
            env_cfg.observations.policy.joint_pos.noise = Unoise(n_min=-noise_val, n_max=noise_val)
            env_cfg.observations.policy.joint_vel.noise = Unoise(n_min=-noise_val, n_max=noise_val)
    elif test_type == "init_pose":
        env_cfg.events.reset_robot_joints.params["position_range"] = condition["pos_range"]
    elif test_type == "workspace":
        r = condition["ranges"]
        env_cfg.commands.ee_pose.ranges.pos_x = r["pos_x"]
        env_cfg.commands.ee_pose.ranges.pos_y = r["pos_y"]
        env_cfg.commands.ee_pose.ranges.pos_z = r["pos_z"]


@hydra_task_config(args_cli.task, agent_cfg_entry_point)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, experiment_cfg: dict):
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device else env_cfg.sim.device

    experiment_cfg["seed"] = 42
    env_cfg.seed = 42

    test_type = args_cli.test_type
    conditions = get_test_conditions(test_type)
    all_results = []

    resume_path = os.path.abspath(args_cli.checkpoint)

    for cond in conditions:
        label = cond["label"]
        print(f"\n{'='*60}")
        print(f"  Testing: {test_type} | Condition: {label}")
        print(f"{'='*60}")

        apply_condition(env_cfg, test_type, cond)

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
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
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
        action_perturb_delta = cond.get("delta", 0.0) if test_type == "action_perturb" else 0.0

        timestep = 0
        while simulation_app.is_running():
            with torch.inference_mode():
                outputs = runner.agent.act(obs, states, timestep=0, timesteps=0)
                actions = outputs[-1].get("mean_actions", outputs[0])

                if action_perturb_delta > 0:
                    noise = torch.empty_like(actions).uniform_(-action_perturb_delta, action_perturb_delta)
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
                    episode_rewards[idx.item()] = 0.0

            if len(episode_returns) >= args_cli.num_episodes:
                break
            if timestep > args_cli.num_episodes * steps_per_ep * 2:
                break

        returns = episode_returns[:args_cli.num_episodes]
        if returns:
            mean_ret = statistics.mean(returns)
            std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.0
        else:
            mean_ret, std_ret = float("nan"), float("nan")

        result = {"label": label, "mean": mean_ret, "std": std_ret, "n": len(returns)}
        all_results.append(result)
        print(f"  Result: Mean={mean_ret:+.4f} +/- {std_ret:.4f} (n={len(returns)})")

        env_skrl.close()

    out_file = f"/home/krz/isaaclab_ws/outputs/tables/robustness_{test_type}.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {out_file}")
    print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
    simulation_app.close()

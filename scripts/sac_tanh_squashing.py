"""
Tanh-squashed Gaussian policy patch for SKRL SAC.

Standard SAC (Haarnoja et al. 2018) samples raw actions from a Gaussian, then
applies tanh to squash them into (-1, 1). The log-probability must include the
Jacobian correction:

    log pi(a|s) = log N(u | mu, sigma) - sum_i log(1 - tanh(u_i)^2)

where u is the pre-squash (raw) action.

SKRL's built-in GaussianMixin uses hard clipping instead of tanh squashing,
which causes alpha collapse in SAC because the uncorrected log_prob drives the
entropy coefficient to zero.

Usage:
    from sac_tanh_squashing import apply_tanh_squashing
    runner = Runner(env, agent_cfg)
    apply_tanh_squashing(runner.agent.policy)
"""

from __future__ import annotations

import math
import types
from typing import Any

import torch
from torch.distributions import Normal


def _tanh_squashed_act(self, inputs: dict[str, Any], *, role: str = "") -> tuple[torch.Tensor, dict[str, Any]]:
    """Replacement for GaussianMixin.act() with tanh squashing + Jacobian correction.

    In eval mode (self.training == False) the function returns the deterministic
    tanh(mean) action with a dummy zero log-prob, which avoids unnecessary
    rsample() noise during evaluation.
    """
    mean_actions, outputs = self.compute(inputs, role)
    log_std = outputs["log_std"]

    if self._g_clip_log_std:
        log_std = torch.clamp(log_std, min=self._g_min_log_std, max=self._g_max_log_std)
        outputs["log_std"] = log_std

    det_actions = torch.tanh(mean_actions)
    outputs["mean_actions"] = det_actions

    # In eval mode use deterministic mean actions (no stochastic sampling)
    if not self.training:
        outputs["log_prob"] = torch.zeros(mean_actions.shape[0], 1, device=mean_actions.device)
        return det_actions, outputs

    self._g_distribution = Normal(mean_actions, log_std.exp())

    raw_actions = self._g_distribution.rsample()
    actions = torch.tanh(raw_actions)

    if "taken_actions" in inputs:
        taken = inputs["taken_actions"]
        raw_taken = torch.atanh(taken.clamp(-1 + 1e-6, 1 - 1e-6))
        log_prob = self._g_distribution.log_prob(raw_taken)
        log_prob = log_prob - torch.log(1 - taken.pow(2) + 1e-6)
    else:
        log_prob = self._g_distribution.log_prob(raw_actions)
        log_prob = log_prob - torch.log(1 - actions.pow(2) + 1e-6)

    if self._g_reduction is not None:
        log_prob = self._g_reduction(log_prob, dim=-1)
    if log_prob.dim() != actions.dim():
        log_prob = log_prob.unsqueeze(-1)

    outputs["log_prob"] = log_prob
    return actions, outputs


def apply_alpha_clamp(agent, alpha_min: float = 0.01) -> None:
    """Monkey-patch an SKRL SAC agent to enforce a minimum entropy coefficient.

    After each ``_update`` call the ``log_entropy_coefficient`` is clamped so
    that ``alpha = exp(log_alpha) >= alpha_min``.  This prevents the entropy
    coefficient from collapsing to near-zero even when the tanh-Jacobian-
    corrected log_prob satisfies ``target_entropy`` at very low alpha values.

    Must be called AFTER Runner construction and BEFORE training.
    """
    log_alpha_min = math.log(alpha_min)
    original_update = agent.update

    def _clamped_update(self, *, timestep: int, timesteps: int):
        original_update(timestep=timestep, timesteps=timesteps)
        if hasattr(self, "log_entropy_coefficient"):
            self.log_entropy_coefficient.data.clamp_(min=log_alpha_min)
            self._entropy_coefficient = torch.exp(self.log_entropy_coefficient.detach())

    agent.update = types.MethodType(_clamped_update, agent)


def apply_tanh_squashing(policy) -> None:
    """Monkey-patch an SKRL GaussianMixin policy to use tanh squashing.

    Must be called AFTER Runner construction (which builds models) and BEFORE
    training or checkpoint loading.

    Also disables the hard clip paths since tanh naturally bounds actions.
    """
    policy.act = types.MethodType(_tanh_squashed_act, policy)
    policy._g_clip_actions = False
    policy._g_clip_mean_actions = False

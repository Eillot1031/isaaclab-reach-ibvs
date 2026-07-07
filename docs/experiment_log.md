# Isaac Lab Experiment Log

## Scope

记录 Isaac Lab 中的 train / play / video / checkpoint / logs / outputs。

## Entry 1 - Initial state

- Date: `2026-04-29`
- Task: not run yet
- RL backend: not selected in execution yet
- Train status: not started
- Play status: not started
- Video status: not started
- Checkpoints: none
- Notes:
  - First-phase target is official `Isaac-Reach-Franka-v0` with official workflow.

## Entry 2 - Experiment steps blocked by installation stage

- Date: `2026-04-29`
- Task target: `Isaac-Reach-Franka-v0`
- RL backend target: `RSL-RL`
- Train status: not started
- Play status: not started
- Video status: not started
- Checkpoints: none
- Blocking reason:
  - Isaac Lab installation and verification are not complete yet
  - `list_envs` / `rsl_rl` / smoke train / play commands have not been run

## Entry 3 - Installation gate cleared, ready for Isaac Lab verification

- Date: `2026-05-07`
- Status:
  - `isaacsim` import verified by user
  - `torch` import verified by user
  - `torch.cuda.is_available()` verified by user
- Next execution targets:
  - clone `IsaacLab`
  - run `./isaaclab.sh --install`
  - install `rsl_rl`
  - list environments
  - verify `Isaac-Reach-Franka-v0`

## Entry 4 - First `list_envs.py` log did not contain the environment list

- Date: `2026-05-07`
- Log file:
  - `/home/krz/isaaclab_ws/outputs/logs/reach_franka_list_envs_output.txt`
- Observed content:
  - only one line of effective output
  - `[INFO] Using python from: /home/krz/miniconda3/envs/env_isaaclab/bin/python`
- File stats:
  - line count: `1`
  - file size: `201B`
- Current interpretation:
  - this run did not successfully capture the actual environment listing
  - `Isaac-Reach-Franka-v0` cannot yet be confirmed from this log alone
- Recommended next step:
  - rerun `list_envs.py` and capture both stdout and stderr
  - keep the terminal attached long enough to allow the app to initialize fully

## Entry 5 - Redirected `list_envs.py` appears silent

- Date: `2026-05-07`
- User command:
  - `./isaaclab.sh -p scripts/environments/list_envs.py > /home/krz/isaaclab_ws/outputs/logs/reach_franka_list_envs_output.txt 2>&1`
- User observation:
  - command appeared to have no visible progress
  - no immediate error was shown in terminal
- Interpretation:
  - full stdout/stderr redirection hides live initialization messages
  - Isaac Lab / Isaac Sim startup can take significant time before producing useful output
  - the process may still be running normally even when the terminal looks idle
- Recommended next step:
  - inspect the running process and the live log file
  - rerun with `tee` when interactive visibility is needed

## Entry 6 - `list_envs.py` starts Isaac Sim and multiple runs were left active

- Date: `2026-05-07`
- Evidence from local source:
  - `scripts/environments/list_envs.py` constructs `AppLauncher(headless=True)` before listing tasks
  - this means the script launches Isaac Sim even though the goal is only to print registered environments
- User process snapshot showed:
  - multiple concurrent `bash ./isaaclab.sh -p scripts/environments/list_envs.py`
  - multiple concurrent `/home/krz/miniconda3/envs/env_isaaclab/bin/python scripts/environments/list_envs.py`
- Interpretation:
  - the script is not a trivial instant command
  - repeated retries created several overlapping startup attempts
  - these overlapping runs can make diagnosis harder and may contend for startup resources
- Recommended immediate action:
  - terminate the stale `list_envs.py` runs
  - rerun only one copy with visible output
  - set `OMNI_KIT_ACCEPT_EULA=YES` explicitly and keep `stdout/stderr` visible with `tee`

## Entry 7 - `list_envs.py` was not hung; first-run extension sync was still in progress

- Date: `2026-05-07`
- Evidence from Kit log:
  - Isaac Sim launched successfully in headless mode
  - extension registries were synchronized
  - runtime extensions began downloading from the Omniverse registry / CloudFront
  - example entries:
    - `omni.usd.libs-1.0.1` download took about `181.7s`
    - `omni.mdl-56.0.3` download took about `8.7s`
    - `omni.iray.libs-0.0.0` had just started downloading when the run ended
- Interpretation:
  - the process was still making forward progress
  - the `timeout 600` killed the run before first-time extension caching finished
  - this is a first-run warmup/caching issue, not a confirmed crash
- Important cache path:
  - `/home/krz/.local/share/ov/data/exts/v2`
- Practical implication:
  - restarting too often is counterproductive
  - one longer uninterrupted run is more likely to succeed

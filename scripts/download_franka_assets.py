#!/usr/bin/env python3
"""Download FrankaEmika USD + Props + Materials from Nucleus to assets/robots/franka/."""

import argparse
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Download Franka assets from Nucleus")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import omni.client
from isaaclab.utils.assets import ISAACLAB_NUCLEUS_DIR

DST = "/home/krz/isaaclab_ws/assets/robots/franka"
NUCLEUS_FRANKA = f"{ISAACLAB_NUCLEUS_DIR}/Robots/FrankaEmika"


def _copy_nucleus_file(src: str, dst: str) -> bool:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    result = omni.client.copy(src.replace(os.sep, "/"), dst, omni.client.CopyBehavior.OVERWRITE)
    ok = result == omni.client.Result.OK
    if ok:
        print(f"[OK] {dst}")
    else:
        print(f"[FAIL] {src} -> {dst} ({result})")
    return ok


def _list_nucleus_dir(path: str) -> list[tuple[str, bool]]:
    """Return (name, is_folder) entries under path."""
    entries = []
    result, folder = omni.client.list(path.replace(os.sep, "/"))
    if result != omni.client.Result.OK:
        return entries
    for item in folder:
        name = item.relative_path
        if name in (".", ".."):
            continue
        is_folder = getattr(item, "flags", 0) and (item.flags & 1)
        entries.append((name.rstrip("/"), bool(is_folder)))
    return entries


def _copy_tree(src_dir: str, dst_dir: str) -> int:
    """Recursively copy Nucleus directory; returns file count."""
    os.makedirs(dst_dir, exist_ok=True)
    count = 0
    for name, is_folder in _list_nucleus_dir(src_dir):
        src = f"{src_dir}/{name}"
        dst = os.path.join(dst_dir, name)
        if is_folder or name.endswith("/"):
            count += _copy_tree(src, dst)
        else:
            if _copy_nucleus_file(src, dst):
                count += 1
    return count


def main():
    os.makedirs(DST, exist_ok=True)
    ok = _copy_nucleus_file(
        f"{NUCLEUS_FRANKA}/panda_instanceable.usd",
        os.path.join(DST, "panda_instanceable.usd"),
    )
    n_props = _copy_tree(f"{NUCLEUS_FRANKA}/Props", os.path.join(DST, "Props"))
    n_mat = _copy_tree(f"{NUCLEUS_FRANKA}/Materials", os.path.join(DST, "Materials"))

    props_ok = os.path.isdir(os.path.join(DST, "Props")) and len(os.listdir(os.path.join(DST, "Props"))) > 0
    mat_ok = os.path.isdir(os.path.join(DST, "Materials"))
    if ok and props_ok:
        print(f"[INFO] Franka assets ready at {DST} (Props files: {n_props}, Materials files: {n_mat})")
    else:
        print("[WARN] Download incomplete — check Nucleus connectivity")
    if not mat_ok:
        print("[WARN] Materials/ missing — robot may use Nucleus fallback")


if __name__ == "__main__":
    main()
    simulation_app.close()

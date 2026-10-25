#!/usr/bin/env python3
"""Build every active build.yaml entry in an existing west workspace.

Run with the workspace's Python environment, after west update. Set
ZEPHYR_SDK_INSTALL_DIR if the SDK is not registered with CMake.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=True)
    matrix = yaml.safe_load((repo / "build.yaml").read_text())["include"]
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    env["ZEPHYR_BASE"] = str(workspace / "zephyr")
    results = []
    for entry in matrix:
        name = entry["artifact-name"]
        build = output / (name + "-build")
        firmware = output / (name + ".uf2")
        firmware.unlink(missing_ok=True)
        command = [sys.executable, "-m", "west", "build", "-p", "always",
                   "-s", str(workspace / "zmk/app"), "-d", str(build),
                   "-b", entry["board"]]
        if entry.get("snippet"):
            command += ["-S", entry["snippet"]]
        command += ["--", f"-DZMK_CONFIG={repo / 'config'}",
                    f"-DZMK_EXTRA_MODULES={repo}",
                    f"-DZephyr_DIR={workspace / 'zephyr/share/zephyr-package/cmake'}"]
        if entry.get("shield"):
            command += ["-DSHIELD=" + entry["shield"]]
        if entry.get("cmake-args"):
            command += shlex.split(entry["cmake-args"])
        print(f"Building {name}: {entry['board']}", flush=True)
        with (output / (name + ".log")).open("w") as log:
            result = subprocess.run(command, cwd=workspace, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        checks = {}
        if result.returncode == 0:
            config = (build / "zephyr/.config").read_text().splitlines()
            for symbol in ("NVS", "SETTINGS_NVS"):
                checks[symbol] = f"CONFIG_{symbol}=y" in config
            checks["persistent_settings"] = "CONFIG_SETTINGS_NONE=y" not in config
            checks["uf2"] = (build / "zephyr/zmk.uf2").is_file()
        passed = result.returncode == 0 and all(checks.values())
        if passed:
            shutil.copy2(build / "zephyr/zmk.uf2", firmware)
        results.append({"name": name, "board": entry["board"],
                        "exit_code": result.returncode, "checks": checks, "passed": passed})
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(f"{'PASS' if passed else 'FAIL'} {name}", flush=True)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

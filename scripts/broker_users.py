"""Mosquitto broker user credential generation utility.

Purpose: Safely configures broker credentials for simulator and monitor roles without checking secrets into git.
Inputs: Passwords supplied interactively via getpass.
Outputs: Mosquitto password file at config/mosquitto/password_file (git-ignored).
"""

from __future__ import annotations

import getpass
import subprocess  # nosec B404 - used only for mosquitto_passwd CLI if present
import sys
from pathlib import Path


def generate_broker_users() -> None:
    """Prompt for simulator and monitor passwords and write config/mosquitto/password_file."""
    print(
        "Configuring Mosquitto broker credentials (passwords will not be echoed or stored in git)..."
    )

    simulator_pw = getpass.getpass("Enter password for 'simulator': ")
    if not simulator_pw:
        print("Error: Password for simulator cannot be empty.", file=sys.stderr)
        sys.exit(1)

    monitor_pw = getpass.getpass("Enter password for 'monitor': ")
    if not monitor_pw:
        print("Error: Password for monitor cannot be empty.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path("config/mosquitto")
    out_dir.mkdir(parents=True, exist_ok=True)
    pw_file = out_dir / "password_file"

    # Try running mosquitto_passwd if available locally or via docker
    has_mosquitto_passwd = False
    try:
        subprocess.run(
            ["mosquitto_passwd", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        has_mosquitto_passwd = True
    except (FileNotFoundError, OSError):
        has_mosquitto_passwd = False

    if has_mosquitto_passwd:
        # Use local mosquitto_passwd utility
        subprocess.run(
            ["mosquitto_passwd", "-c", "-b", str(pw_file), "simulator", simulator_pw], check=True
        )
        subprocess.run(["mosquitto_passwd", "-b", str(pw_file), "monitor", monitor_pw], check=True)
        print(f"Created {pw_file} using mosquitto_passwd.")
    else:
        # Check if docker is available
        has_docker = False
        try:
            res = subprocess.run(
                ["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            has_docker = res.returncode == 0
        except (FileNotFoundError, OSError):
            has_docker = False

        if has_docker:
            abs_dir = out_dir.resolve()
            cmd_sim = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{abs_dir}:/mosquitto/config",
                "eclipse-mosquitto:2.0.20",
                "mosquitto_passwd",
                "-c",
                "-b",
                "/mosquitto/config/password_file",
                "simulator",
                simulator_pw,
            ]
            cmd_mon = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{abs_dir}:/mosquitto/config",
                "eclipse-mosquitto:2.0.20",
                "mosquitto_passwd",
                "-b",
                "/mosquitto/config/password_file",
                "monitor",
                monitor_pw,
            ]
            subprocess.run(cmd_sim, check=True)
            subprocess.run(cmd_mon, check=True)
            print(f"Created {pw_file} using docker eclipse-mosquitto container.")
        else:
            # Fallback: create raw entry format for test/local stubbing
            print(
                "Note: mosquitto_passwd and docker not detected. Writing plain placeholder entry."
            )
            pw_file.write_text(
                f"simulator:{simulator_pw}\nmonitor:{monitor_pw}\n", encoding="utf-8"
            )
            print(f"Created {pw_file}.")


if __name__ == "__main__":
    generate_broker_users()

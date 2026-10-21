# Windows host

How an agent whose shell runs on Windows (PowerShell or Git Bash) reaches the Ubuntu WSL distro and the devcontainer. The setup itself is in `docs/dev-setup.md`.

## Run commands in WSL or the container

Write the commands into a script file and pipe it in. Each extra shell layer rewrites inline commands: PowerShell expands `$?` and `$(…)`, `wsl.exe -- bash -c` runs through a second shell that empties variables, and Git Bash rewrites `/paths`. Through stdin, the script arrives unchanged.

From Git Bash:

```bash
# In the distro
cat script.sh | MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -e bash -s

# As root in the distro, for sudo steps (systemctl, modprobe, /etc)
cat script.sh | MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -u root -e bash -s

# In the running devcontainer, as its user
c=$(wsl.exe -d Ubuntu-24.04 -e docker ps -q --filter label=devcontainer.local_folder)
cat script.sh | MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -e docker exec -i -u ubuntu "$c" bash -s
```

A script in the container starts with `source /opt/ros/jazzy/setup.bash`.

## Windows-side tools

- `usbipd` is at `C:\Program Files\usbipd-win\usbipd.exe` and may be missing from `PATH` in an older shell. `list` and `attach` work without admin rights.
- Multi-line `git commit` messages and `gh` bodies go through a file: `git commit -F <file>`, `gh … --body-file <file>`.

## `ros2` CLI

Wrap every `ros2` CLI call in `timeout` (`timeout 15 ros2 topic list`). The CLI talks to the ROS 2 daemon at `127.0.0.1:11511`, and when that daemon is stuck, a call waits forever or fails after about two minutes with `Connection timed out`.

When a call hangs or times out:

1. Restart the daemon: `ros2 daemon stop; ros2 daemon start`.
2. Or skip it with `--no-daemon` on the command (`ros2 topic echo --no-daemon /joy`). Without the daemon, discovery runs only briefly, so a node that just started may not appear yet. Repeat the call.

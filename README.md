# Stubentiger

A small tracked indoor robot on ROS 2 Jazzy: a Raspberry Pi 4 for ROS, an Arduino Uno driving the motors, simulated first in Gazebo and then driven for real with an Xbox 360 controller. Navigation, follow-me and a voice assistant come later.

The domain vocabulary is in [CONTEXT.md](CONTEXT.md) and the architecture decisions are in [docs/adr/](docs/adr/). Planning happens in [GitHub Issues](https://github.com/mkogel/stubentigerV2/issues).

## Development

Development happens in a devcontainer on docker-ce inside an Ubuntu WSL2 distro; [docs/dev-setup.md](docs/dev-setup.md) sets up the laptop step by step. The build, test and lint commands are in [CLAUDE.md](CLAUDE.md) ("Build and test").

## Run the sim from a fresh clone

The Virtual MVP: the robot in Gazebo Harmonic, driven with an Xbox 360 controller through the same stack that later runs on the robot. It needs the laptop set up as in [docs/dev-setup.md](docs/dev-setup.md), steps 1 to 9, and for driving the controller's receiver attached (step 6).

1. In the **Ubuntu terminal**, clone the repo into the distro's own filesystem and open it in VS Code:

   ```bash
   git clone https://github.com/mkogel/stubentigerV2.git ~/stubentigerV2
   code ~/stubentigerV2
   ```

2. In VS Code, run **Dev Containers: Reopen in Container**. The first start pulls the dev image and takes a few minutes.

3. In the **VS Code container terminal**, build:

   ```bash
   source /opt/ros/jazzy/setup.bash
   colcon build --base-paths src sim
   ```

4. Still in the container terminal, start the sim:

   ```bash
   source install/setup.bash
   ros2 launch stubentiger_sim sim.launch.py
   ```

   The Gazebo window opens, and the robot stands on a plain grey floor.

5. Drive with the controller: nothing moves unless you hold a button.

   | Input | Does |
   |---|---|
   | LB held (Dead-man button) | drive at Normal: up to 0.3 m/s, 1.2 rad/s |
   | RB held, with or without LB | drive at Turbo: up to 0.6 m/s, 2.5 rad/s |
   | Left stick, up and down | speed |
   | Right stick, left and right | turn |

   Letting go of the buttons stops the robot. So does switching the controller off.

Stop the sim with Ctrl+C in the container terminal. The launch takes these switches, for example `ros2 launch stubentiger_sim sim.launch.py rviz:=true`:

| Switch | Default | Does |
|---|---|---|
| `gui` | `true` | the Gazebo GUI, as its own process next to the server; `false` runs the server alone, headless |
| `rviz` | `false` | RViz2 with the robot model, its TF and `/odom` |
| `sensors` | `false` | the sim LiDAR, IMU and camera on `/scan`, `/imu/data` and `/camera/image_raw` |

Foxglove connects to `ws://localhost:8765`. The Virtual MVP acceptance checks are in [docs/checklists/virtual-mvp.md](docs/checklists/virtual-mvp.md).

## Contributing

This repo is public and the robot lives in a private home, so nothing private gets committed. Run `pre-commit install` once after cloning; [CLAUDE.md](CLAUDE.md) ("Public repo") explains what counts as private and how it is enforced.

## Copyright

Copyright © 2026 Max Kogel. All rights reserved.

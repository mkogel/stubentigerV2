# Stubentiger

A small tracked indoor robot on ROS 2 Jazzy: a Raspberry Pi 4 for ROS, an Arduino Uno driving the motors, simulated first in Gazebo and then driven for real with an Xbox 360 controller. Navigation, follow-me and a voice assistant come later.

The domain vocabulary is in [CONTEXT.md](CONTEXT.md) and the architecture decisions are in [docs/adr/](docs/adr/). Planning happens in [GitHub Issues](https://github.com/mkogel/stubentigerV2/issues).

## Development

Development happens in a devcontainer on docker-ce inside an Ubuntu WSL2 distro; [docs/dev-setup.md](docs/dev-setup.md) sets up the laptop step by step. The build, test and lint commands are in [CLAUDE.md](CLAUDE.md) ("Build and test").

## Contributing

This repo is public and the robot lives in a private home, so nothing private gets committed. Run `pre-commit install` once after cloning; [CLAUDE.md](CLAUDE.md) ("Public repo") explains what counts as private and how it is enforced.

## Copyright

Copyright © 2026 Max Kogel. All rights reserved.

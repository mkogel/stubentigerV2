# The Arduino stops the motors on its own

The motor-controller firmware is the last line of defence: it stops the motors by itself, without help from the Pi, whenever its own safety conditions trip, including when the Pi has crashed, the serial link is gone or ROS is down. Nothing above the Arduino is trusted to stop the robot. Above it, everything needed to drive safely runs on the Pi, and losing the laptop or the cloud may only cost comfort, never safety. We chose this over trusting ROS-side timeouts alone because the Pi, Wi-Fi and the ROS stack are the parts most likely to fail while the motors are running.

## Consequences

- The firmware owns its own watchdog and cut-offs; the safety-layering ticket decides which conditions trip them and at which thresholds.
- Nothing on the Pi may assume it is the only thing that can stop the robot, and nothing on the laptop or in the cloud may be required to stop it.

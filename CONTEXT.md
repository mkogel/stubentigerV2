# Stubentiger

A small tracked indoor robot, teleoperated first and autonomous later, that eventually follows its owner and acts as a voice-driven personal assistant.

## Language

### Milestones

**Virtual MVP**:
The simulated robot driven by an Xbox 360 controller with dead-man button and Normal/Turbo switching, running the same ROS stack that later runs on the hardware.
_Avoid_: Sim demo, prototype

**Physical MVP**:
The real robot driven by an Xbox 360 controller with the same Teleop behaviour as the Virtual MVP, plus a hardware watchdog stop and battery undervoltage protection.
_Avoid_: Hardware MVP, first drive

### Driving

**Teleop**:
Driving the robot by hand with the Xbox 360 controller; nothing moves unless the driver holds a Dead-man button.
_Avoid_: Manual mode, remote control, RC

**Dead-man button**:
A controller button that must be held for the robot to drive; releasing it stops the robot.
_Avoid_: Enable button, safety button

**Normal**:
The default Teleop speed mode, matching the indoor speed of autonomous driving.

**Turbo**:
The fast Teleop speed mode, active only while its button is held; releasing it drops back to Normal or stops the robot.
_Avoid_: Boost, fast mode

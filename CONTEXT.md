# Stubentiger

A small tracked indoor robot, teleoperated first and autonomous later, that eventually follows its owner and acts as a voice-driven personal assistant.

## Language

### Milestones

**Virtual MVP**:
The simulated robot driven by an Xbox 360 controller with dead-man button and Normal/Turbo switching, running the same ROS stack that later runs on the hardware.
_Avoid_: Sim demo, prototype

**Physical MVP**:
The real robot driven by an Xbox 360 controller with the same Teleop behaviour as the Virtual MVP, plus a hardware watchdog stop, battery undervoltage protection, and a power-on sequence that shows when the robot is ready to drive.
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

### Safety

**Trip**:
The motor controller stopping the motors on its own, without the Pi, because one of its safety conditions fired: no command for too long, a stalled track, a driver fault or a Cut-off.
_Avoid_: Fault stop, emergency stop

**Re-arm**:
After a Trip, the robot drives again only once it has been told to stand still first; a command that was in flight before the Trip never resumes on its own.
_Avoid_: Reset, clear

**Motor switch**:
The physical switch that cuts power to the motors, independent of all software; the robot's hard stop.
_Avoid_: Kill switch, power switch

**Battery warning**:
The motor battery running low enough that the driver is told to finish up; the robot still drives.
_Avoid_: Low battery alarm

**Cut-off**:
The motor battery running so low that the motor controller stops the motors to protect it; the robot stays stopped until the Motor switch is turned off and on again.
_Avoid_: Undervoltage shutdown, brown-out

### Power-up

**Ready**:
The robot can drive the moment the Dead-man button is held: its motor controller answers, nothing has tripped it for good, and the controller is connected. The Motor switch is not part of it.
_Avoid_: Armed, online

**Startup LED**:
The front light that says whether the robot is starting, Ready, or stuck with a fault that waiting won't fix.
_Avoid_: Status LED, ready LED

**Power LED**:
The front light that says the robot's computer has power, blinks when a battery runs low, and goes dark once it is safe to switch off.
_Avoid_: Battery LED

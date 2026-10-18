# Simulating the tracked skid-steer in Gazebo

Research for issue #4. Sources checked on 2026-10-18 against the upstream branches that ship with each ROS 2 distro: Jazzy pairs with Gazebo Harmonic (gz-sim 8, gz-physics 7, gz-sensors 8) and Lyrical pairs with Gazebo Jetty (gz-sim 10, gz-physics 9, gz-sensors 10) ([Gazebo ROS pairing table](https://gazebosim.org/docs/latest/ros_installation/), [gz_ros2_control compatibility matrix](https://github.com/ros-controls/gz_ros2_control/blob/rolling/README.md#compatibility-matrix)). Both Gazebo versions are LTS: Harmonic until May 2029, Jetty until May 2031 ([Gazebo releases](https://gazebosim.org/docs/latest/releases/)). Unless noted otherwise, every finding below holds for both versions.

## Answer

**Model each track as 4 ground-contact wheels and drive it with `diff_drive_controller` through `gz_ros2_control`.** One wheel per side is the commanded joint, and it carries the same joint name the Arduino hardware interface exposes. The other 3 wheels on that side are URDF `<mimic>` joints. They appear only in the sim's `<ros2_control>` block, so the controller YAML is identical in sim and on hardware. Give the wheel joints realistic effort and velocity limits, use the same `wheel_separation_multiplier` in both, and tune the sim's wheel/floor friction until the 10-spin test in sim matches the real robot.

Gazebo's `TrackedVehicle`/`TrackController` systems are not an option now. Stock `gz_ros2_control` cannot drive them: they have no joint to command. Bridging them would need custom C++, they only work with the DART engine, and on a flat indoor floor their extra fidelity adds little.

Deciding facts:

1. `gz_ros2_control`'s `GazeboSimSystem` only writes joint commands: `JointVelocityCmd`, `JointForceCmd`, or position via velocity ([gz_system.cpp `write()`](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control/src/gz_system.cpp#L783-L846)). `TrackController` instead acts on a *link* whose track is fixed to the body. In the upstream example, `left_track_j` is `type='fixed'` ([tracked_vehicle_simple.sdf L193-196](https://github.com/gazebosim/gz-sim/blob/gz-sim8/examples/worlds/tracked_vehicle_simple.sdf#L193-L196)), and the track takes speed commands on a Gazebo topic (`track_cmd_vel`) ([TrackController.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/track_controller/TrackController.hh)). No ros2_control command interface exists to bind to it.
2. `diff_drive_controller` takes one or more joints per side. It sends every joint on a side the same velocity and averages their feedback ([diff_drive_controller.cpp L194-224, L302-308](https://github.com/ros-controls/ros2_controllers/blob/jazzy/diff_drive_controller/src/diff_drive_controller.cpp#L194-L308)). However, `left_wheel_names` has to match the hardware. The real robot has one motor per side, so the sim must also expose one *commanded* joint per side. Mimic joints make that possible (see §3).
3. `wheel_separation_multiplier` scales the separation in **both** the inverse kinematics (commands) and the odometry ([L184, L302-304, L342-346](https://github.com/ros-controls/ros2_controllers/blob/jazzy/diff_drive_controller/src/diff_drive_controller.cpp#L184)). That makes it the single scalar that absorbs skid-steer slip in sim and on hardware alike. `TrackedVehicle`'s `steering_efficiency` is the same idea (§2.3).

## 1. Approaches compared

| | A. Wheels + mimic + `gz_ros2_control` (**recommended**) | B. `TrackedVehicle`/`TrackController` + custom `gz_ros2_control` plugin | C. `TrackedVehicle` driven via `ros_gz_bridge` (no ros2_control) | D. gz `DiffDrive` / `VelocityControl` systems |
|---|---|---|---|---|
| Same controller YAML as hardware | Yes | Yes, through a custom `GazeboSimSystemInterface` ([docs](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/doc/index.rst#advanced-custom-gz_ros2_control-simulation-plugins)) that maps joint velocity commands to `track_cmd_vel` topics and reads track odometry back | **No.** The plugin does its own kinematics and odometry and subscribes to a gz Twist ([TrackedVehicle.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim10/src/systems/tracked_vehicle/TrackedVehicle.hh)) | **No.** Same problem ([DiffDrive.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/diff_drive/DiffDrive.hh), [VelocityControl.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/velocity_control/VelocityControl.hh)) |
| Turning fidelity | Approximate. Skid resistance comes from lateral friction at 8 contact points, tuned to the measured multiplier | Better. It uses "contact surface motion" and steers friction along the desired turning circle. Upstream calls it "provably better than a set of wheels" but "not 100% plausible" ([TrackController.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/track_controller/TrackController.hh)) | Same as B | `DiffDrive` = A with fewer wheels. `VelocityControl` sets the model twist directly, so there is no slip at all |
| Physics engine | Any (default DART) | **DART only.** It needs `SetContactPropertiesCallbackFeature` ([dartsim SimulationFeatures.hh](https://github.com/gazebosim/gz-physics/blob/gz-physics9/dartsim/src/SimulationFeatures.hh#L59), not in [bullet-featherstone](https://github.com/gazebosim/gz-physics/blob/gz-physics9/bullet-featherstone/src/SimulationFeatures.hh)) and contact normals ([TrackController.cc L553](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/track_controller/TrackController.cc#L553)) | DART only | Any |
| Control modes | Velocity (effort possible) | **Velocity only**, "no effort controller is available" ([TrackController.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/track_controller/TrackController.hh)) | Velocity only | Velocity |
| Custom code | None (URDF/xacro + YAML) | C++ pluginlib plugin plus maintenance across Harmonic and Jetty | Python/launch glue, plus a second Teleop/Nav2 path | None, but you lose ros2_control |
| CI/headless cost | Lowest: 8 wheel-ground contacts | Low, plus a per-contact callback in C++ | Low | Lowest |
| Complexity | Low | High | Medium | Low |

A is the only option that meets the hard requirement (same `ros2_control` config) without writing C++. B is the upgrade path if sim and real turning behaviour diverge too much for Nav2 tuning.

## 2. What upstream says about each piece

### 2.1 `gz_ros2_control` (both distros)

- The plugin is `gz_ros2_control-system`, and the hardware plugin inside `<ros2_control>` is `gz_ros2_control/GazeboSimSystem` ([Jazzy demo URDF](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control_demos/urdf/test_diff_drive.xacro.urdf#L149-L178), identical on [lyrical](https://github.com/ros-controls/gz_ros2_control/blob/lyrical/gz_ros2_control_demos/urdf/test_diff_drive.xacro.urdf#L172)). `<parameters>` "can be given multiple times to load multiple files" ([docs](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/doc/index.rst#add-the-gz_ros2_control-plugin)). That lets you load the shared controller YAML plus a small sim-only overlay.
- Velocity commands are "applied directly to the joint as is", and upstream warns this "may cause slippage and odometer errors" because the wheels reach speed instantly while the chassis does not ([Notes on the command interface](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/doc/index.rst#notes-on-the-command-interface)).
- In DART, a joint velocity command turns the joint into a `SERVO` actuator ([JointFeatures.cc L164-167](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/JointFeatures.cc#L149-L167)). Its force limits come from the SDF/URDF joint `effort`, and a missing or negative effort means **infinite** ([SDFFeatures.cc L146-149](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc#L135-L149)). So without an `effort` limit the simulated motor has unlimited torque.
- **Mimic joints.** `ros2_control` builds `mimic_joints` from the URDF `<mimic>` tag for joints listed in a `<ros2_control>` block with no command interfaces. The mimicked joint must be in the same block ([component_parser.cpp L1034-1085](https://github.com/ros-controls/ros2_control/blob/jazzy/hardware_interface/src/component_parser.cpp#L1034-L1085)). `GazeboSimSystem` then drives each follower with a velocity command proportional to its position error × `update_rate` ([gz_system.cpp L848-875](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control/src/gz_system.cpp#L848-L875)). The gain is effectively 1.0 and does not use `position_proportional_gain` ([gz_ros2_control#949](https://github.com/ros-controls/gz_ros2_control/issues/949), open), so followers track stiffly. That is what you want for wheels on one track. The same code exists on [lyrical](https://github.com/ros-controls/gz_ros2_control/blob/lyrical/gz_ros2_control/src/gz_system.cpp).
- `GazeboSimSystem` can also expose Gazebo IMU sensors as ros2_control state interfaces ([gz_system.cpp L135-162](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control/src/gz_system.cpp#L135-L162)). It is optional here (see §5).
- For actuator dynamics there is a pluginlib hook. The `GazeboCustomSimSystem` demo adds a low-pass filter to a velocity joint ([docs](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/doc/index.rst#advanced-custom-gz_ros2_control-simulation-plugins)). Use it if the Arduino PID lag (30 Hz loop) matters for Turbo tuning.

### 2.2 `diff_drive_controller`

- Parameters ([Jazzy definition file](https://github.com/ros-controls/ros2_controllers/blob/jazzy/diff_drive_controller/src/diff_drive_controller_parameter.yaml)):
  - `left_wheel_names`/`right_wheel_names` (arrays)
  - `wheel_separation`: "If this parameter is wrong, the robot will not behave correctly in curves"
  - `wheel_radius`
  - `wheel_separation_multiplier`, `left/right_wheel_radius_multiplier`
  - `open_loop`, `position_feedback`, `enable_odom_tf`, `cmd_vel_timeout` (default 0.5 s)
  - `linear.x.*` / `angular.z.*` velocity, acceleration and jerk limits
- In Jazzy the controller subscribes to `geometry_msgs/TwistStamped` ([userdoc](https://github.com/ros-controls/ros2_controllers/blob/jazzy/diff_drive_controller/doc/userdoc.rst)). The upstream demo YAML still has `use_stamped_vel: true` ([demo yaml](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control_demos/config/diff_drive_controller.yaml)), but that parameter no longer exists in the Jazzy definition. Do not copy it.
- On rolling/Lyrical the parameters are the same except that most are `read_only`, `publish_rate` is gone, and the deprecated `has_*_limits` flags were removed ([master definition](https://github.com/ros-controls/ros2_controllers/blob/master/diff_drive_controller/src/diff_drive_controller_parameter.yaml)). A YAML that uses `.NAN` to disable limits, and no `has_*_limits`, works on both.

### 2.3 `TrackedVehicle` / `TrackController` (for the record)

- `TrackedVehicle` converts a body twist into track speeds as `v ± ω·tracks_separation / (2·steering_efficiency)` ([TrackedVehicle.cc L688-691](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/tracked_vehicle/TrackedVehicle.cc#L688-L691)). The default `steering_efficiency` is 0.5. That equals `wheel_separation_multiplier = 1/steering_efficiency = 2` in `diff_drive_controller` terms.
- `<track_height>` is documented as required ([TrackedVehicle.hh](https://github.com/gazebosim/gz-sim/blob/gz-sim10/src/systems/tracked_vehicle/TrackedVehicle.hh)), but the code never reads it from SDF (only `tracks_separation` and `steering_efficiency`, [L274-276](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/tracked_vehicle/TrackedVehicle.cc#L274-L276)). The plugin's own odometry therefore always uses the hard-coded 0.2 m default ([L365-366](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/tracked_vehicle/TrackedVehicle.cc#L365-L366)). This holds on gz-sim8, gz-sim10 and main. The upstream example even spells it `<tracks_height>`.
- Jetty adds `<body_link>` to `TrackController` (diff of `TrackController.hh` gz-sim8 → gz-sim10). Otherwise the two versions match.
- `TrackController` "does not simulate the effect of grousers". Upstream recommends a very high `<mu1>`, and the example uses `mu=0.7, mu2=150` with `fdir1` on the track collisions ([example world L117-124](https://github.com/gazebosim/gz-sim/blob/gz-sim8/examples/worlds/tracked_vehicle_simple.sdf#L117-L124)).
- If B is ever built: track links attached by fixed joints in URDF get lumped into `base_link` during URDF→SDF conversion unless `<preserveFixedJoint>true</preserveFixedJoint>` is set ([gz_ros2_control docs](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/doc/index.rst#using-force-torque-sensors-in-simulation)). After lumping, `TrackController` would have no link to attach to.

### 2.4 Physics engine facts that matter for A

- The default engine is DART on both Harmonic and Jetty ([Physics.cc gz-sim8 L933](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc#L933), [gz-sim10 L972-975](https://github.com/gazebosim/gz-sim/blob/gz-sim10/src/systems/physics/Physics.cc#L972-L975)). DART uses an ODE-based collision detector ([gz-physics9 EntityManagementFeatures.cc L810](https://github.com/gazebosim/gz-physics/blob/gz-physics9/dartsim/src/EntityManagementFeatures.cc#L810)).
- DART reads `mu`, `mu2`, `slip1`, `slip2` and `fdir1` from `<surface><friction><ode>` ([gz-physics7 SDFFeatures.cc L934-951](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc#L934-L951), [gz-physics9 L953-968](https://github.com/gazebosim/gz-physics/blob/gz-physics9/dartsim/src/SDFFeatures.cc#L953-L968)). It does **not** read `kp`/`kd`/`min_depth`/`max_vel`, so the ODE-era contact-stiffness tuning has no effect.
- When two surfaces touch, DART uses the **minimum** of their friction coefficients ([DART ContactSurface.cpp L114-116](https://github.com/dartsim/dart/blob/v6.13.2/dart/constraint/ContactSurface.cpp#L114-L116)). The floor friction caps whatever you set on the wheels.
- The URDF `<gazebo reference="link">` shortcuts are `mu1`, `mu2`, `fdir1`, `kp`, `kd`, `maxVel` and `minDepth` ([sdformat parser_urdf.cc L1403-1432](https://github.com/gazebosim/sdformat/blob/sdf14/src/parser_urdf.cc#L1403-L1432)). For `slip1`/`slip2`, put a full `<collision><surface>…</surface></collision>` blob inside the `<gazebo reference>`. It is merged into the link's collision ([L1690-1716](https://github.com/gazebosim/sdformat/blob/sdf14/src/parser_urdf.cc#L1690-L1716)).
- DART does **not** implement native mimic constraints. Only bullet-featherstone (and MuJoCo on main) have `SetMimicConstraintFeature` ([bullet-featherstone JointFeatures.hh L55](https://github.com/gazebosim/gz-physics/blob/gz-physics9/bullet-featherstone/src/JointFeatures.hh#L55)). sdformat converts URDF `<mimic>` into SDF `<mimic>` ([parser_urdf.cc L3152-3161](https://github.com/gazebosim/sdformat/blob/sdf14/src/parser_urdf.cc#L3152-L3161)), so with DART Gazebo prints a one-time `gzerr` that it cannot create the constraint ([Physics.cc L1905-1915](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc#L1905-L1915)). That error is harmless: `gz_ros2_control` does the coupling itself (§2.1). **Do not switch to bullet-featherstone** with this design, because native mimic and gz_ros2_control's mimic would then both act on the same joints.

## 3. URDF/xacro modelling notes (approach A)

Geometry from the photos (`docs/setup-images/robot-side.jpg`): a raised idler at the front, 4 road wheels on the ground, and the drive sprocket high at the rear-top. On a flat floor only the run of track under the road wheels touches the ground. So:

- **Contact wheels:** 4 per side. Place them at the real road-wheel x positions (measure them). Use cylinders whose bottom sits at the track's ground line. Model the idler, sprocket and track belt as **visual only**.
- **Radius = `wheel_radius`.** The encoder sits on the sprocket, so the hardware interface reports sprocket angle and `wheel_radius` is the sprocket's effective radius, 0.0215 m (43 mm sprocket, `docs/initial-buildplan.md`). Use the same radius for the sim contact cylinders so that joint rad/s ↔ m/s matches hardware. Alternatively, keep the visual road-wheel radius `r_w` and set the mimic `multiplier = 0.0215 / r_w`. Note that `<mimic offset>` was ignored by gz_ros2_control until [#952](https://github.com/ros-controls/gz_ros2_control/issues/952) was closed on 2026-08-29. The current `jazzy` branch applies it; keep `offset="0"` anyway.
- **Joint layout:** use the same commanded joint names as hardware, e.g. `left_wheel_joint`/`right_wheel_joint`, on the rearmost road wheel (nearest the sprocket). The other three road-wheel joints are `continuous` joints with `<mimic joint="left_wheel_joint" multiplier="1"/>`. `robot_state_publisher` computes mimic joints itself ([robot_state_publisher.cpp L185-195](https://github.com/ros/robot_state_publisher/blob/jazzy/src/robot_state_publisher.cpp#L185-L195)), so the hardware TF tree stays complete even though the real `<ros2_control>` block lists only two joints.
- **`<ros2_control>` switch:** a xacro arg `use_sim` selects `gz_ros2_control/GazeboSimSystem` (2 commanded joints + 6 mimic joints with state interfaces only) or `tank_hardware/...` (2 joints). The controller YAML does not change.
- **Motor limits:**
  - URDF `<limit velocity>` = 460 rpm = 48.2 rad/s at the sprocket.
  - `effort` = stall torque. Pololu #2272 lists 5.5 kg·cm ≈ 0.54 N·m at 6 V, an extrapolated value ([Pololu #2272](https://www.pololu.com/product/2272)), split over the 4 wheels of a side (≈ 0.135 N·m each at r = 21.5 mm). That gives ≈ 25 N tractive force per side.
  - Without `effort` the servo has infinite torque (§2.1), so the sim never stalls and accelerates unrealistically.
  - Speed: 48.2 rad/s × 0.0215 m ≈ 1.04 m/s theoretical. Put the real Teleop/Turbo caps in the shared `diff_drive_controller` limits (`linear.x.max_velocity`, `max_acceleration`, …) so sim and hardware clip identically.
- **Friction (sim-only `<gazebo reference>` blocks):**
  - Start isotropic on the wheels (`mu1 = mu2 ≈ 1.0`, no `fdir1`).
  - Give the floor model an explicit, realistic `mu` for your floor type, because DART takes min(wheel, floor) (§2.4).
  - Lateral friction at the 8 contact points is what makes the sim need a `wheel_separation_multiplier > 1`.
  - These starting values are guesses. Tune them as described below.
- **Separation multiplier:**
  - Set `wheel_separation` to the measured track-centre distance, which the buildplan still lists as a to-do.
  - Calibrate `wheel_separation_multiplier` on the real robot (buildplan Phase 1 step 6: 10 spins on the spot) and put it in the shared YAML.
  - In sim, command the same 10-spin test with that YAML and compare ground-truth yaw with commanded yaw. Adjust wheel/floor `mu2` (lateral, with `fdir1` set along the wheel's rolling direction) until they match.
  - Before hardware exists, run the sim with the multiplier at 1.0, measure the sim's effective factor, and use that as a placeholder.
  - Background: the effective separation of a skid-steer is larger than the geometric one because the instantaneous centres of rotation of the tracks move outward. Mandow et al. model this with an "ICR expansion factor" ([Mandow et al., IROS 2007, doi:10.1109/IROS.2007.4399139](https://doi.org/10.1109/IROS.2007.4399139)).
- **Inertia:**
  - Weigh the robot.
  - Model `base_link` as a box (225 × 225 mm footprint, real height) carrying most of the mass, with box inertia `I = m/12·(b²+c²)`.
  - Give each wheel a small mass (e.g. 20–30 g) with cylinder inertia `Ixx = Iyy = m/12·(3r²+h²)`, `Izz = m r²/2`.
  - Keep `base_footprint` as the massless root with a fixed joint to `base_link`, per buildplan Phase 2. Every link with a collision needs a non-zero, physically consistent inertia, or DART becomes unstable.
- **Fixed-joint lumping:** sensor frames on fixed joints (`laser_frame`, `imu_link`, `camera_link`) are lumped into `base_link` during URDF→SDF conversion, and their `<gazebo reference>` extensions move with them ([parser_urdf.cc ReduceFixedJoints L408-430](https://github.com/gazebosim/sdformat/blob/sdf14/src/parser_urdf.cc#L408-L430)). The sensor still sits at the right pose, but see the frame-ID pitfall in §5.

Illustrative xacro fragment (not product code):

```xml
<!-- joint_name: "${side}_wheel_joint" for the commanded wheel, "${side}_road_wheel_${idx}_joint" for the rest -->
<xacro:macro name="road_wheel" params="side idx x joint_name mimic">
  <link name="${side}_road_wheel_${idx}">
    <!-- cylinder axis rotated onto y, so iyy is the axial moment m*r^2/2 -->
    <collision><origin rpy="${pi/2} 0 0"/><geometry><cylinder radius="0.0215" length="0.04"/></geometry></collision>
    <inertial><mass value="0.025"/><inertia ixx="6.2e-6" iyy="5.8e-6" izz="6.2e-6" ixy="0" ixz="0" iyz="0"/></inertial>
  </link>
  <joint name="${joint_name}" type="continuous">
    <parent link="base_link"/><child link="${side}_road_wheel_${idx}"/>
    <origin xyz="${x} ${track_y if side == 'left' else -track_y} ${wheel_z}"/>
    <axis xyz="0 1 0"/>
    <limit effort="0.135" velocity="48.2"/>
    <xacro:if value="${mimic}"><mimic joint="${side}_wheel_joint" multiplier="1" offset="0"/></xacro:if>
  </joint>
  <gazebo reference="${side}_road_wheel_${idx}"><mu1>1.0</mu1><mu2>1.0</mu2></gazebo>
</xacro:macro>
<!-- Per side: one call with mimic=false (commanded), three with mimic=true. -->
```

(sdformat citations here are from the `sdf14` branch used by Harmonic; Jetty ships sdformat 16, and I did not re-check those line numbers on it.)

## 4. Running it: laptop (WSLg) and CI

- **Launch:** `ros_gz_sim`'s `gz_sim.launch.py` with `gz_args`, a `ros_gz_sim create` spawn, a `/clock` bridge (`/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock`), then spawners for `joint_state_broadcaster` and the drive controller. Every node uses `use_sim_time: true` ([upstream diff-drive demo launch](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control_demos/launch/diff_drive_example.launch.py), [ros_gz_bridge README](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/README.md)).
- **Headless/CI:** run the server only (`-s`) with `--headless-rendering`. This uses EGL, needs no X server, and "is only available with OGRE2". On a machine without a GPU, "OGRE will revert to software rendering" ([Gazebo headless rendering](https://gazebosim.org/api/sim/8/headless_rendering.html)). Physics for 8 wheel contacts is trivial. The cost is in rendering sensors (gpu_lidar, camera) under software rendering on GitHub-hosted runners. Add a xacro arg to turn the camera off in CI.
- **Jetty bonus:** a CPU lidar (`<sensor type="lidar">` + `gz-sim-cpu-lidar-system`) that ray-casts through physics "without depending on gz-rendering" ([CpuLidarSensor.hh](https://github.com/gazebosim/gz-sensors/blob/gz-sensors10/include/gz/sensors/CpuLidarSensor.hh), [SdfEntityCreator.cc L1127-1130](https://github.com/gazebosim/gz-sim/blob/gz-sim10/src/SdfEntityCreator.cc#L1127-L1130), [CMakeLists](https://github.com/gazebosim/gz-sim/blob/gz-sim10/src/systems/cpu_lidar/CMakeLists.txt)).
  - Status: backported to the gz-sim10 branch on 2026-08-29. It is **not** in the latest tag, gz-sim10 10.5.0 of 2026-07-29 ([Changelog](https://github.com/gazebosim/gz-sim/blob/gz-sim10/Changelog.md)). gz-sensors10 10.1.1 already contains the sensor.
  - Harmonic does not have it.
  - Once it is released, Lyrical CI could run lidar-only Nav2 tests without any rendering.
- **WSLg with the RTX 3050:**
  - Open Robotics reports that the `LIBGL_ALWAYS_SOFTWARE=1` workaround "is not necessary anymore" on recent Garden/Harmonic, but "WSLg is still not an officially tested platform for Gazebo" ([Discourse, 2023-11](https://discourse.openrobotics.org/t/wslg-with-gpu-support-available-on-latest-version-of-gazebo-garden-and-harmonic/48128)).
  - On hybrid-graphics laptops, Mesa's D3D12 driver picks the GPU from `MESA_D3D12_DEFAULT_ADAPTER_NAME` (case-insensitive substring, e.g. `NVIDIA`) ([Mesa D3D12 docs](https://docs.mesa3d.org/drivers/d3d12.html)).
  - An older OGRE2-on-WSL2 crash is tracked in [gz-rendering#662](https://github.com/gazebosim/gz-rendering/issues/662). The fallback is the `ogre` render engine for the GUI or `LIBGL_ALWAYS_SOFTWARE=1`.

## 5. Simulated sensors

Add the world-level systems once: `gz-sim-sensors-system` with `<render_engine>ogre2</render_engine>` (needed for gpu_lidar and camera), and `gz-sim-imu-system` for the IMU ([Gazebo sensors tutorial](https://gazebosim.org/docs/harmonic/sensors/)). Bridge to ROS with `ros_gz_bridge` using a YAML `config_file`. The mappings are `gz.msgs.LaserScan`→`sensor_msgs/msg/LaserScan`, `gz.msgs.IMU`→`sensor_msgs/msg/Imu`, `gz.msgs.Image`/`CameraInfo`→`sensor_msgs/msg/Image`/`CameraInfo`, all `GZ_TO_ROS` ([ros_gz_bridge README](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/README.md)). Use the same ROS topic names as the real drivers (`/scan`, `/imu/data_raw`, `/camera/image_raw`) so downstream nodes don't change.

| Sensor | SDF (inside `<gazebo reference="…">`) | Values to match the real hardware |
|---|---|---|
| RPLIDAR A1M8 | `type="gpu_lidar"` (both); `type="lidar"` CPU variant on Jetty once released | `update_rate` 5.5; 360° (`min_angle` −π, `max_angle` π); `samples` ≈ 1450 (8 kHz ÷ 5.5 Hz) or fewer for CI; `range` 0.15–12 m; Gaussian noise ≈ 1 % of range ([Slamtec A1 spec](https://www.slamtec.com/en/lidar/a1spec)). Pose x=+7.5 mm, y=−29 mm, z=+68 mm from `base_link` (buildplan Phase 0) |
| ICM-20948 IMU | `type="imu"` + Imu system | Rate as the real Python node publishes. Add Gaussian noise on `angular_velocity`/`linear_acceleration`. Bridge to `/imu/data_raw` and keep `imu_filter_madgwick` in the sim pipeline for parity. Alternatively read it through `gz_ros2_control`'s IMU sensor interface (§2.1) |
| Pi camera | `type="camera"` | 640×480 @ 15 fps (buildplan Phase 5). Needs a separate `camera_optical_frame` (ROS optical convention, z forward). Set it via the bridge's `override_frame_id`/`frame_id` ([ros_gz_bridge README](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/README.md)) |

**Frame IDs:** the published `header.frame_id` defaults to the *sensor name*, not the link. Set it explicitly. On Harmonic use `<gz_frame_id>laser_frame</gz_frame_id>` ([gz-sensors8 Sensor.cc L186-195](https://github.com/gazebosim/gz-sensors/blob/gz-sensors8/src/Sensor.cc#L186-L195)). On Jetty use the SDF `<frame_id>`; `gz_frame_id` still works there but logs a deprecation warning ([gz-sensors10 Sensor.cc L181-197](https://github.com/gazebosim/gz-sensors/blob/gz-sensors10/src/Sensor.cc#L181-L197)). To cover both, gate it with a xacro arg.

## 6. Pitfalls

1. **Unlimited motor torque.** Without URDF `effort`, DART's velocity servo has infinite force (§2.1). Wheels then never stall against walls, and acceleration is unrealistic. Set the effort and use `diff_drive_controller` acceleration limits.
2. **Instant wheel speed → slip and odometry error** with the velocity interface, as upstream warns. Keep `linear.x.max_acceleration` realistic. Optionally model actuator lag with a custom `GazeboSimSystemInterface`.
3. **Mimic coupling is gz_ros2_control's, not DART's.** Mimic joints must be listed in the sim `<ros2_control>` block with state interfaces only, or they spin freely. Expect the harmless `gzerr` about mimic constraints. Do not use bullet-featherstone with this design. Followers are position-servoed at gain 1 regardless of `position_proportional_gain` ([#949](https://github.com/ros-controls/gz_ros2_control/issues/949)).
4. **Floor friction caps wheel friction** (DART min rule). Empty worlds' default ground plane is not tuned for your floor, so define the floor surface yourself.
5. **`kp`/`kd`/`minDepth`/`maxVel` do nothing with DART.** Tune `mu`/`mu2`/`fdir1`/`slip1`/`slip2` instead.
6. **Multiplier calibrated in one world only.** The sim and real multipliers only match after friction tuning. Re-check them after changing floors or robot mass.
7. **TwistStamped in Jazzy:** run Teleop with `stamped:=true`, and in Nav2 set `enable_stamped_cmd_vel` (already in the buildplan). Do not copy the stale `use_stamped_vel` from the upstream demo YAML.
8. **Sensor `frame_id` defaults to the sensor name.** Use `gz_frame_id` on Harmonic and `frame_id` on Jetty. Camera images need an optical frame.
9. **Headless sensors need OGRE2 + EGL.** On GPU-less CI runners they fall back to software rendering, which is slow for cameras, so disable the camera in CI.
10. **WSLg is not officially tested.** If rendering is black or crashes, select the NVIDIA adapter via `MESA_D3D12_DEFAULT_ADAPTER_NAME`, then fall back to `ogre` or software rendering.
11. **If you ever adopt `TrackedVehicle`:** `<track_height>` is silently ignored, which skews only the plugin's own odometry. It needs DART and `preserveFixedJoint` on the track links, and supports velocity commands only.

## 7. Open items for the implementation ticket

- Measure: track-centre separation, road-wheel x positions and contact line height, robot mass and CoM height, IMU pose.
- A first spike should verify that mimic-coupled road wheels behave stably under traction in DART: no chatter, sensible stall when pushing a wall. This is the one part of the recommendation that upstream demos do not show directly; the upstream mimic demo is a gripper.
- Decide whether the Arduino PID lag needs a low-pass sim plugin after comparing step responses (sim vs `e` encoder logs).

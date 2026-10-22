# Virtual MVP checklist

The hands-on checks for Virtual MVP acceptance (`v0.1.0`), run on the laptop with the real Xbox 360 controller. Everything else is proven in CI (#24, "Testing Decisions").

Before you start: the laptop is set up as in [`docs/dev-setup.md`](../dev-setup.md), the receiver is attached with `usbipd` (step 6) and the controller is on.

## Record a run

Post each run as a comment on the Virtual MVP acceptance issue:

```markdown
## Virtual MVP checklist run

- Date: YYYY-MM-DD
- Commit: <full SHA of the commit under test>

| # | Item | Result |
|---|---|---|
| 1 | Fresh clone, README steps | pass / fail |
| 2 | GUI switch | pass / fail |
| 3 | RViz2 switch | pass / fail |
| 4 | Drive with the controller | pass / fail |
| 5 | No creep, 10 s | pass / fail |
| 6 | Controller off while driving | pass / fail |
| 7 | RViz2 and Foxglove show the motion | pass / fail |
| 8 | Real-time factor with the robot | the value |
| 9 | Release | pass / fail |

Notes: <anything that failed or looked odd>
```

A failed item gets a note on what happened. Screenshots show the sim only, never a room.

## Steps

All commands run in the **VS Code container terminal** (`ubuntu@…`) unless a step says otherwise.

1. **Fresh clone, README steps.** Follow the README section "Run the sim from a fresh clone" in a new clone (for example `~/stubentiger-check`), word for word. Pass: the build succeeds and the launch shows the robot in the Gazebo GUI, standing still on the grey floor.

2. **GUI switch.** With the sim from step 1 running, in a second container terminal:

   ```bash
   ps -eo pid,args | grep 'gz sim' | grep -v grep
   ```

   Pass: two processes, one with `-s` (the server) and one with `-g` (the GUI). Close the Gazebo window: the robot stack keeps running (`ros2 topic hz /odom` still shows about 50 Hz). Then stop the launch with Ctrl+C.

3. **RViz2 switch.** Start the sim again with RViz2:

   ```bash
   ros2 launch stubentiger_sim sim.launch.py rviz:=true
   ```

   Pass: RViz2 opens with the fixed frame `odom`, the robot model, the TF frames (including `lidar_link`, `imu_link` and `camera_optical_link`) and the `/odom` arrows. No display shows an error.

4. **Drive with the controller.** Leave that launch running.
   - Hold **LB** and push the left stick forward: the robot drives forward at walking pace (Normal, 0.3 m/s). The right stick turns it.
   - Hold **RB** as well (or RB alone): it drives about twice as fast (Turbo, 0.6 m/s).
   - Let go of RB with LB still held: it drops back to Normal.
   - Let go of both buttons with the stick still pushed: it stops at once.
   - Push the sticks without holding a button: nothing moves.

   Pass: all five behave as described.

5. **No creep.** Note the robot's position:

   ```bash
   ros2 topic echo --once --no-daemon /odom nav_msgs/msg/Odometry --field pose.pose.position
   ```

   `--no-daemon` and the type keep it from hanging on mirrored networking ([`docs/agents/windows-host.md`](../agents/windows-host.md), "`ros2` CLI"). Hold LB with your thumbs off the sticks for 10 s, then read the position again. Pass: the robot did not move and the position is unchanged. Record any difference.

6. **Controller off while driving.** Hold LB, drive forward, and switch the controller off (hold the Guide button until the ring goes dark) while still driving. Pass: the robot stops within about 0.8 s, well under a second. Switch the controller back on, hold LB: it drives again without any other step.

7. **RViz2 and Foxglove show the motion.** In Foxglove (desktop app or the browser, [`docs/dev-setup.md`](../dev-setup.md) step 13), open a connection to `ws://localhost:8765` and add a 3D panel. Drive the robot. Pass: RViz2 and Foxglove both show the robot moving and turning.

8. **Real-time factor with the robot.** Drive for a minute with the Gazebo GUI open and read the real-time factor in its bottom-right corner. Record it. A value far below 1 is recorded as a finding for a new decision (dual-boot), not a failed item.

9. **Release.** On GitHub:
   - CI is green on `main`.
   - Every `package.xml` has version `0.1.0` (`grep -h '<version>' src/*/package.xml sim/*/package.xml`).
   - The annotated tag `v0.1.0` and its GitHub Release exist.

   Pass: all three.

# SensorAgent Architecture

## 1. Project Goal

SensorAgent is an interactive industrial robot agent for object perception, natural language instruction understanding, task planning, robotic manipulation, visual verification, and failure recovery.

The target closed loop is:

```text
Natural language instruction
→ Task understanding
→ Open-vocabulary segmentation
→ RGB-D 3D localization
→ Behavior-tree task planning
→ Robotic pick-and-place execution
→ Visual verification
→ Failure recovery
```

The project follows a **simulation-first, real-robot-transfer** strategy. We first build a simulation environment aligned with the real ROS2-based robot arm, validate the full Agent workflow in simulation, and then migrate the same workflow to the physical robot setup.

## 2. System Overview

The system is designed as an **Agent middleware + WebSocket orchestration + ROS2 execution stack** architecture.

```text
┌────────────────────────────┐
│        Web UI / CLI         │
│ Instruction, status, video  │
└─────────────┬──────────────┘
              │ WebSocket
┌─────────────▼──────────────┐
│        Agent Server         │
│ Parsing / orchestration     │
└─────────────┬──────────────┘
              │
      ┌───────┼──────────────────────┐
      │       │                      │
┌─────▼───┐ ┌─▼────────┐      ┌──────▼──────┐
│Perception│ │Behavior  │      │ Recovery    │
│SAM3/RGBD │ │Tree      │      │ RL Policy   │
└─────┬───┘ └─┬────────┘      └──────┬──────┘
      │       │                      │
      └───────┼──────────────────────┘
              │ Robot Command API
┌─────────────▼──────────────┐
│       Robot Gateway         │
│ WebSocket/HTTP ↔ ROS2 Bridge│
└─────────────┬──────────────┘
              │ ROS2
┌─────────────▼──────────────┐
│ ROS2 Robot Stack            │
│ MoveIt2 / tf2 / ros2_control│
│ Camera / Gripper / Driver   │
└────────────────────────────┘
```

## 3. Module Responsibilities

| Module | Responsibility |
|---|---|
| **Web UI / CLI** | Accept natural language commands and display RGB frames, depth maps, masks, behavior-tree states, and execution logs. |
| **Agent Server** | Main orchestration service for instruction intake, task state management, module invocation, and event streaming. |
| **Instruction Parser** | Convert natural language instructions into structured task JSON. |
| **Perception Service** | Use SAM3 / DINO-X for open-vocabulary segmentation and fuse RGB-D input to estimate 3D poses. |
| **Scene Graph Service** | Build an industrial scene graph containing objects, bin cells, spatial relations, and graspable regions. |
| **Behavior Tree Runtime** | Decompose tasks into executable nodes such as detect, grasp, place, verify, and recover. |
| **Robot Gateway** | Translate high-level Agent commands into ROS2 actions, services, and topics. |
| **ROS2 Robot Stack** | Handle robot control, MoveIt2 motion planning, tf transforms, gripper control, and camera drivers. |
| **RL Recovery Service** | Generate recovery actions for grasp failures, placement offsets, occlusion, and retry decisions. |

## 4. Core Data Flow

Example user instruction:

```text
Put the silver roller on the left into the third bin cell.
```

Parsed task:

```json
{
  "task_type": "pick_and_place",
  "object_query": "left silver roller",
  "target_query": "third cell of the bin",
  "constraints": {
    "avoid_collision": true,
    "verify_after_place": true
  }
}
```

Perception output:

```json
{
  "object": {
    "label": "silver roller",
    "mask_id": "mask_001",
    "pose_3d": [0.42, -0.13, 0.08, 0, 0, 1.57],
    "confidence": 0.91
  },
  "target": {
    "label": "bin_cell_3",
    "pose_3d": [0.60, 0.20, 0.10, 0, 0, 0],
    "confidence": 0.95
  }
}
```

Behavior-tree execution flow:

```text
ParseInstruction
→ CaptureRGBD
→ SegmentObject
→ EstimateObjectPose
→ SegmentTargetCell
→ EstimateTargetPose
→ PlanGrasp
→ ExecuteGrasp
→ VerifyGrasp
→ PlanPlace
→ ExecutePlace
→ VerifyPlace
→ RecoverIfFailed
```

## 5. Boundary Between WebSocket and ROS2

WebSocket and ROS2 have separate responsibilities:

| Layer | Responsibility |
|---|---|
| **WebSocket** | High-level Agent tasks, status events, perception results, behavior-tree states, and UI updates. |
| **ROS2** | Robot control, trajectory execution, sensor streams, tf transforms, and real-time hardware interfaces. |

The Agent does not directly control motors or low-level joints. Instead, it calls high-level robot primitives through the Robot Gateway:

```python
capture_rgbd()
move_to_pose()
open_gripper()
close_gripper()
pick()
place()
verify_object_in_cell()
```

The Robot Gateway then translates these primitives into MoveIt2 planning requests, gripper commands, camera calls, and ROS2 actions.

## 6. Unified Simulation and Real-Robot Interface

The system hides the difference between simulation and the physical robot behind a unified execution interface:

```text
RobotExecutor
├── SimExecutor
└── RealExecutor
```

The Agent and behavior tree depend only on `RobotExecutor`, not on a specific simulator or robot driver.

```python
class RobotExecutor:
    def capture_rgbd(self): ...
    def move_to_pose(self, pose): ...
    def open_gripper(self): ...
    def close_gripper(self): ...
    def pick(self, grasp_pose): ...
    def place(self, target_pose): ...
    def get_robot_state(self): ...
    def verify_object_in_cell(self, object_id, cell_id): ...
```

The backend can be switched through configuration:

```yaml
robot:
  backend: sim   # sim / real
```

## 7. Recommended Directory Layout

```text
sensoragent/
├── apps/
│   ├── agent_server/          # FastAPI + WebSocket service
│   ├── web_ui/                # Visualization frontend
│   └── cli/                   # Command-line entry point
│
├── core/
│   ├── agent/                 # Agent orchestration logic
│   ├── planner/               # Instruction parsing and task JSON generation
│   ├── behavior_tree/         # Behavior-tree nodes and runtime
│   ├── schemas/               # Pydantic data models
│   └── config/                # Configuration management
│
├── perception/
│   ├── open_vocab/            # SAM3 / DINO-X adapters
│   ├── rgbd/                  # Depth maps, point clouds, camera intrinsics
│   ├── scene_graph/           # 3D scene graph
│   └── calibration/           # Hand-eye calibration and coordinate transforms
│
├── execution/
│   ├── executor_base.py       # RobotExecutor abstract interface
│   ├── sim_executor.py        # Simulation executor
│   ├── real_executor.py       # Real robot executor
│   └── primitives/            # pick/place/move/verify primitives
│
├── ros2_ws/
│   └── src/
│       ├── robot_gateway/     # WebSocket/HTTP ↔ ROS2 bridge node
│       ├── robot_bringup/     # Real robot launch configuration
│       ├── robot_moveit/      # MoveIt2 configuration
│       └── sim_bringup/       # Simulation launch configuration
│
├── recovery/
│   ├── rl_envs/               # Reinforcement learning environments
│   ├── policies/              # Trained recovery policies
│   └── trainers/              # PPO/SAC training scripts
│
├── simulation/
│   ├── scenes/                # Workbench, bin, and object scenes
│   ├── assets/                # URDF / mesh / CAD assets
│   └── randomization/         # Random placement, lighting, occlusion
│
├── data/
│   ├── samples/               # Example RGB-D, masks, task records
│   ├── datasets/              # Training and evaluation data
│   └── logs/                  # Execution logs
│
├── docs/
│   ├── zh/                    # Chinese archive documents
│   ├── setup.md
│   └── experiment.md
│
└── tests/
```

## 8. Technical Roadmap

The project should be implemented in the following order:

1. **Build the aligned robot simulation environment**  
   Load the robot arm, gripper, camera, workbench, bin, and industrial parts.

2. **Establish the Agent workflow**  
   Implement natural language input, task JSON generation, behavior-tree execution, and status feedback.

3. **Run the full simulation loop**  
   Complete the pipeline from instruction input to simulated pick-and-place execution.

4. **Integrate open-vocabulary perception**  
   Use SAM3 / DINO-X to segment target objects and bin cells from text prompts.

5. **Fuse RGB-D 3D localization**  
   Convert masks, depth maps, and camera calibration into robot-frame 3D poses.

6. **Transfer to the physical robot**  
   Integrate ROS2, MoveIt2, the real camera, gripper, and hand-eye calibration.

7. **Add failure recovery**  
   Use rule-based recovery and local RL policies for grasp failures, placement offsets, and occlusions.

## 9. Innovation Points

1. **Open-vocabulary industrial perception**  
   SAM3 / DINO-X enables natural-language-driven segmentation of industrial parts and bin cells, supporting unknown or newly added categories.

2. **RGB-D 3D scene understanding**  
   Open-vocabulary masks are fused with depth data to generate executable 3D positions, poses, and spatial relations.

3. **VLA-style task planning**  
   Natural language, visual perception, and robot state are converted into structured task graphs instead of plain text plans.

4. **Behavior-tree execution control**  
   Behavior trees organize perception, grasping, placing, verification, and recovery into an interpretable and debuggable execution flow.

5. **Local RL failure recovery**  
   Reinforcement learning is used for high-value local recovery policies such as re-grasping, placement correction, and retry selection.

6. **Simulation-to-real transfer**  
   A unified `RobotExecutor` interface allows the same Agent workflow to operate in both simulation and the real ROS2 robot setup.

## 10. Final Deliverables

The final project should deliver:

```text
Runnable source code
Simulation environment
ROS2 robot interface
Open-vocabulary perception adapters
Behavior-tree execution system
Failure recovery policies
Experimental data and metrics
Technical report
User guide
Demonstration video
```

Core demonstration scenario:

```text
Natural language instruction
→ Recognition of scattered industrial parts
→ Localization of the target bin cell
→ Robotic grasping of the target part
→ Placement into the specified cell
→ Visual verification
→ Automatic retry or correction after failure
```

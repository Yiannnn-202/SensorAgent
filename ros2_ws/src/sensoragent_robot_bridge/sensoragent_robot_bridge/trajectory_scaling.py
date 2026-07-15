"""Trajectory timing helpers independent of ROS message imports."""


def scale_joint_trajectory_speed(trajectory, speed: float) -> None:
    """Scale joint trajectory timing, velocity, and acceleration in place."""

    if speed <= 0.0 or speed > 1.0:
        raise ValueError("speed must be greater than 0 and at most 1")

    for point in trajectory.points:
        total_nanoseconds = (
            int(point.time_from_start.sec) * 1_000_000_000
            + int(point.time_from_start.nanosec)
        )
        scaled_nanoseconds = int(round(total_nanoseconds / speed))
        point.time_from_start.sec = scaled_nanoseconds // 1_000_000_000
        point.time_from_start.nanosec = scaled_nanoseconds % 1_000_000_000
        point.velocities = [value * speed for value in point.velocities]
        point.accelerations = [
            value * speed * speed for value in point.accelerations
        ]

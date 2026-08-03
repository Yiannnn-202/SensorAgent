# 黑白料箱金属零件场景

该场景与默认 `industrial_pgs.sdf` 相互独立。它复用相同的 RM65-B、工作台、RGB-D 相机架、照明和 ROS 2 控制链路，并提供桌面散放取料区和白底黑线的 3x3 分格目标料箱。

## 启动

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=industrial_sorting_metal_pgs.sdf
```

## 初始布局

七类金属零件散放在工作台一侧，3x3 料箱位于另一侧且初始为空，用于语音指令驱动的抓取和分格放置。扁平的法兰和齿轮已替换为六角立柱和带肩轴套，便于 Robotiq 2F-85 从侧面稳定夹取。料箱为 `420 x 420 mm`，每个格位有 `128 x 128 mm` 的净宽和 `55 mm` 外壁，供 Robotiq 2F-85 自上而下进入。

圆柱、轴和螺栓以横放姿态初始化，避免仿真开始后滚动。料箱墙体和分隔条均有碰撞体，可防止零件跨格。

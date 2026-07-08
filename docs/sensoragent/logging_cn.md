# 日志

SensorAgent 维护自己的 Agent 侧日志。机器人、仿真、相机或其他模块的运行时日志不默认存放在这里，除非某个 integration 明确导入。

## 运行日志目录

默认运行日志位于仓库根目录的 `logs/`：

```text
logs/
├── app.log
├── tasks/
├── traces/
└── errors/
```

`logs/` 目录已被 Git 忽略。

## 人类可读日志

`logs/app.log` 用于开发和演示时实时观察。

Linux/macOS：

```bash
tail -f logs/app.log
```

Windows PowerShell：

```powershell
Get-Content logs\app.log -Wait
```

## 结构化任务日志

任务级日志建议以 JSONL 写入 `logs/tasks/`。

示例：

```json
{"event":"task_started","task_id":"...","input":"put the roller into cell 3"}
{"event":"tool_call_started","task_id":"...","tool":"vision.detect_object","input":{}}
{"event":"tool_call_finished","task_id":"...","tool":"vision.detect_object","output":{},"duration_ms":120}
{"event":"task_finished","task_id":"...","status":"success"}
```

## Trace 日志

`logs/traces/` 用于记录更细的执行 span，例如 Agent planning、skill execution、tool invocation、retry 和 integration call。

## 错误日志

非预期运行错误可以同步写入 `logs/errors/`，方便调试。

## 配置

日志目录和日志级别应通过配置文件和环境变量配置。

推荐配置形态：

```yaml
logging:
  level: info
  console: true
  file: logs/app.log
  task_dir: logs/tasks
  trace_dir: logs/traces
  error_dir: logs/errors
```

推荐环境变量覆盖：

```env
SENSORAGENT_LOG_DIR=logs
SENSORAGENT_LOG_LEVEL=debug
```

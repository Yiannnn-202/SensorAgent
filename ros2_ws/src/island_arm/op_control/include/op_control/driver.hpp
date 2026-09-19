// Copyright 2025 op_control authors
// Low-level synchronous OmniPicker driver.

#ifndef OP_CONTROL_DRIVER_HPP_
#define OP_CONTROL_DRIVER_HPP_

#include "op_control/types.hpp"

#include <functional>
#include <memory>
#include <string>

namespace op_control {
namespace detail {
class SerialPort;
class FrameParser;
}  // namespace detail

/// Synchronous blocking OmniPicker driver.
///
/// All work happens in the caller thread. Execute() is not thread-safe and
/// must be serialized by the caller (the ROS node does this with a mutex).
/// The state callback is invoked synchronously from Execute() whenever a
/// valid frame is received.
class Driver {
 public:
  Driver();
  ~Driver();

  Driver(const Driver&) = delete;
  Driver& operator=(const Driver&) = delete;

  /// Opens the serial port in raw 8N1 mode.
  bool Connect(const std::string& port, int baudrate);
  void Disconnect();
  bool IsConnected() const;

  /// Executes a gripper motion command. Blocks until completion or timeout.
  ///
  /// @param pos    Target position in [0.0, 1.0]; 1.0 is fully open.
  /// @param force  Normalized force in [0.0, 1.0].
  /// @param speed  Normalized speed in [0.0, 1.0].
  /// @param acc    Normalized acceleration in [0.0, 1.0].
  /// @param dec    Normalized deceleration in [0.0, 1.0].
  Result Execute(float pos, float force, float speed, float acc, float dec);

  /// Copies the last known state into @p out_state.
  void GetState(State* out_state) const;

  /// Sets the callback invoked synchronously for every valid received frame.
  using StateCallback = std::function<void(const State&)>;
  void SetStateCallback(StateCallback cb);

 private:
  void NotifyState(const State& state);

  std::unique_ptr<detail::SerialPort> serial_;
  std::unique_ptr<detail::FrameParser> parser_;
  StateCallback state_cb_;
  State last_state_{};
};

}  // namespace op_control

#endif  // OP_CONTROL_DRIVER_HPP_

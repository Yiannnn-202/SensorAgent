// Copyright 2025 op_control authors

#include "op_control/driver.hpp"

#include "detail/protocol.hpp"
#include "detail/serial_port.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <thread>

namespace op_control {

Driver::Driver()
    : serial_(std::make_unique<detail::SerialPort>()),
      parser_(std::make_unique<detail::FrameParser>()) {}

Driver::~Driver() { Disconnect(); }

bool Driver::Connect(const std::string& port, int baudrate) {
  return serial_->Open(port, baudrate);
}

void Driver::Disconnect() { serial_->Close(); }

bool Driver::IsConnected() const { return serial_->IsOpen(); }

void Driver::GetState(State* out_state) const {
  if (out_state != nullptr) {
    *out_state = last_state_;
  }
}

void Driver::SetStateCallback(StateCallback cb) { state_cb_ = std::move(cb); }

void Driver::NotifyState(const State& state) {
  last_state_ = state;
  if (state_cb_) {
    state_cb_(state);
  }
}

Result Driver::Execute(float pos, float force, float speed, float acc, float dec) {
  if (!IsConnected()) {
    return Result::kSerialError;
  }

  pos = std::max(0.0f, std::min(1.0f, pos));
  force = std::max(0.0f, std::min(1.0f, force));
  speed = std::max(0.0f, std::min(1.0f, speed));
  acc = std::max(0.0f, std::min(1.0f, acc));
  dec = std::max(0.0f, std::min(1.0f, dec));

  const std::uint8_t target_pos_hex =
      static_cast<std::uint8_t>(pos * 255.0f);
  const bool is_closing = target_pos_hex < 128;

  detail::Frame cmd = detail::BuildCommand(pos, force, speed, acc, dec);

  if (!serial_->FlushInput()) {
    return Result::kSerialError;
  }

  if (!serial_->Write(cmd.data.data(), cmd.data.size())) {
    return Result::kSerialError;
  }

  // Allow the gripper to start and shed residual torque.
  std::this_thread::sleep_for(std::chrono::milliseconds(kStartupSettleMs));

  const auto timeout = std::chrono::milliseconds(
      static_cast<int>(kDefaultTimeoutSec * 1000.0f));
  const auto start = std::chrono::steady_clock::now();
  auto last_send = start;

  bool seen_feedback = false;
  int max_pos_fb = -1;
  int last_pos_fb = -1;
  int stable_count = 0;

  detail::Frame frame{};
  std::vector<std::uint8_t> rx_chunk(64);

  while (true) {
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = now - start;
    if (elapsed >= timeout) {
      break;
    }

    // Resend the command every 50 ms to keep the firmware reporting state.
    if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_send)
            .count() >= kCommandResendMs) {
      if (!serial_->Write(cmd.data.data(), cmd.data.size())) {
        return Result::kSerialError;
      }
      last_send = now;
    }

    int n = serial_->Read(rx_chunk.data(), rx_chunk.size(), kReadTimeoutMs);
    if (n < 0) {
      return Result::kSerialError;
    }

    if (n > 0) {
      if (!parser_->Feed(rx_chunk.data(), static_cast<std::size_t>(n), &frame)) {
        std::cerr << "[op_control] Unrecognized serial bytes:";
        for (int i = 0; i < n; ++i) {
          std::cerr << ' ' << std::hex << std::setw(2) << std::setfill('0')
                    << static_cast<int>(rx_chunk[static_cast<std::size_t>(i)]);
        }
        std::cerr << std::dec << std::setfill(' ') << std::endl;
        continue;
      }

      State state{};
      detail::FrameToState(frame, &state);
      NotifyState(state);

      const std::uint8_t state_fb = frame.State();
      const std::uint8_t pos_fb = frame.Pos();
      seen_feedback = true;

      if (static_cast<int>(pos_fb) > max_pos_fb) {
        max_pos_fb = static_cast<int>(pos_fb);
      }
      if (static_cast<int>(pos_fb) == last_pos_fb) {
        ++stable_count;
      } else {
        stable_count = 0;
        last_pos_fb = static_cast<int>(pos_fb);
      }

      // Dropped state takes priority over position tolerance.
      if (state_fb == static_cast<std::uint8_t>(Status::kDropped)) {
        return Result::kDropped;
      }

      // Arrived at target.
      if (state_fb == static_cast<std::uint8_t>(Status::kArrived)) {
        if (std::abs(static_cast<int>(pos_fb) -
                     static_cast<int>(target_pos_hex)) <= kPosTolerance) {
          return Result::kSuccess;
        }
        if (!is_closing && target_pos_hex >= 200 &&
            pos_fb >= kOpenPosThreshold) {
          return Result::kSuccess;
        }
      }

      // Stalled: closing means grasped, otherwise check proximity.
      if (state_fb == static_cast<std::uint8_t>(Status::kStalled)) {
        if (is_closing) {
          return Result::kGrasped;
        }
        if (std::abs(static_cast<int>(pos_fb) -
                     static_cast<int>(target_pos_hex)) <= kPosTolerance) {
          return Result::kSuccess;
        }
        if (pos_fb >= kOpenPosThreshold) {
          return Result::kSuccess;
        }
      }

      // Position tolerance fallback.
      if (std::abs(static_cast<int>(pos_fb) -
                   static_cast<int>(target_pos_hex)) <= kPosTolerance) {
        return Result::kSuccess;
      }

      // Stable position: firmware still reports MOVING but motion has stopped.
      if (stable_count >= kStableThreshold) {
        return Result::kSuccess;
      }
    }
  }

  // Timeout fallback for open motion only; never applied to closing.
  if (!is_closing && seen_feedback &&
      max_pos_fb >= kOpenPosMinProgress) {
    return Result::kSuccess;
  }

  return Result::kTimeout;
}

}  // namespace op_control

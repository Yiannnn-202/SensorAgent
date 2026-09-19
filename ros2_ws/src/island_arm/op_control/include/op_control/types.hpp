// Copyright 2025 op_control authors
// Public type definitions for the OmniPicker gripper driver.

#ifndef OP_CONTROL_TYPES_HPP_
#define OP_CONTROL_TYPES_HPP_

#include <array>
#include <cstdint>

namespace op_control {

// Protocol constants.
inline constexpr std::uint8_t kFrameHeader0 = 0x41;
inline constexpr std::uint8_t kFrameHeader1 = 0x41;
inline constexpr std::size_t kFrameLength = 12;
inline constexpr std::size_t kChecksumIndex = 11;
inline constexpr std::size_t kStateIndex = 4;
inline constexpr std::size_t kPosIndex = 5;
inline constexpr std::size_t kForceIndex = 7;

inline constexpr char kDefaultPort[] =
    "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0";
inline constexpr int kDefaultBaudrate = 115200;
inline constexpr float kDefaultTimeoutSec = 8.0f;
inline constexpr int kOpenPosThreshold = 220;
inline constexpr int kOpenPosMinProgress = 180;
inline constexpr int kPosTolerance = 30;
inline constexpr int kStableThreshold = 5;
inline constexpr int kCommandResendMs = 50;
inline constexpr int kReadTimeoutMs = 50;
inline constexpr int kStartupSettleMs = 200;

/// Normalized gripper status reported by firmware.
enum class Status : std::uint8_t {
  kArrived = 0x00,
  kMoving = 0x01,
  kStalled = 0x02,
  kDropped = 0x03,
  kUnknown = 0xFF
};

/// Operation result code.
enum class Result : std::int8_t {
  kSuccess = 0,
  kGrasped,
  kDropped,
  kTimeout,
  kSerialError,
  kBusy,
  kInvalidParam,
  kNotInitialized
};

/// Real-time gripper state.
struct State {
  float pos = 0.0f;
  float force = 0.0f;
  float vel = 0.0f;
  Status status = Status::kUnknown;
  std::array<std::uint8_t, kFrameLength> raw_frame{};
};

}  // namespace op_control

#endif  // OP_CONTROL_TYPES_HPP_

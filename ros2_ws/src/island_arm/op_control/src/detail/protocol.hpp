// Copyright 2025 op_control authors
// Internal OmniPicker 12-byte frame protocol helpers.

#ifndef OP_CONTROL_DETAIL_PROTOCOL_HPP_
#define OP_CONTROL_DETAIL_PROTOCOL_HPP_

#include "op_control/types.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace op_control {
namespace detail {

struct Frame {
  std::array<std::uint8_t, kFrameLength> data{};

  bool IsValid() const {
    return data[0] == kFrameHeader0 && data[1] == kFrameHeader1;
  }
  std::uint8_t State() const { return data[kStateIndex]; }
  std::uint8_t Pos() const { return data[kPosIndex]; }
  std::uint8_t Force() const { return data[kForceIndex]; }
};

Frame BuildCommand(float pos, float force, float speed, float acc, float dec);
std::uint8_t ComputeChecksum(const Frame& frame);
bool ValidateFrame(const Frame& frame);

/// Appends @p raw bytes to a rolling buffer and extracts the newest valid frame.
/// Returns true if a valid frame was found; the frame is written to @p out.
bool ParseNewestFrame(const std::uint8_t* raw, std::size_t len, Frame* out,
                      std::vector<std::uint8_t>* rolling_buffer);

void FrameToState(const Frame& frame, State* out_state);

/// Rolling buffer that extracts the newest valid 12-byte frame.
class FrameParser {
 public:
  FrameParser() = default;

  /// Feeds new bytes and returns true if a valid frame was found.
  bool Feed(const std::uint8_t* raw, std::size_t len, Frame* out);

 private:
  std::vector<std::uint8_t> buffer_;
};



}  // namespace detail
}  // namespace op_control

#endif  // OP_CONTROL_DETAIL_PROTOCOL_HPP_

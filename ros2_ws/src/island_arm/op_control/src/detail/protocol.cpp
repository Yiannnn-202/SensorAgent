// Copyright 2025 op_control authors

#include "detail/protocol.hpp"

#include <algorithm>
#include <cstring>

namespace op_control {
namespace detail {

Frame BuildCommand(float pos, float force, float speed, float acc, float dec) {
  Frame frame{};
  frame.data[0] = kFrameHeader0;
  frame.data[1] = kFrameHeader1;
  frame.data[2] = 0x01;  // command type
  frame.data[3] = 0x00;

  frame.data[4] =
      static_cast<std::uint8_t>(std::max(0.0f, std::min(1.0f, pos)) * 255.0f);
  frame.data[5] =
      static_cast<std::uint8_t>(std::max(0.0f, std::min(1.0f, force)) * 255.0f);
  frame.data[6] =
      static_cast<std::uint8_t>(std::max(0.0f, std::min(1.0f, speed)) * 255.0f);
  frame.data[7] =
      static_cast<std::uint8_t>(std::max(0.0f, std::min(1.0f, acc)) * 255.0f);
  frame.data[8] =
      static_cast<std::uint8_t>(std::max(0.0f, std::min(1.0f, dec)) * 255.0f);
  frame.data[9] = 0x00;
  frame.data[10] = 0x00;
  frame.data[11] = ComputeChecksum(frame);
  return frame;
}

std::uint8_t ComputeChecksum(const Frame& frame) {
  std::uint16_t sum = 0;
  for (std::size_t i = 2; i < 11; ++i) {
    sum += frame.data[i];
  }
  return static_cast<std::uint8_t>((~sum) & 0xFF);
}

bool ValidateFrame(const Frame& frame) {
  return frame.IsValid() && frame.data[kChecksumIndex] == ComputeChecksum(frame);
}

bool ParseNewestFrame(const std::uint8_t* raw, std::size_t len, Frame* out,
                      std::vector<std::uint8_t>* rolling_buffer) {
  if (raw == nullptr || out == nullptr || rolling_buffer == nullptr || len == 0) {
    return false;
  }

  rolling_buffer->insert(rolling_buffer->end(), raw, raw + len);

  // Keep the buffer bounded. The newest valid frame is likely near the end.
  if (rolling_buffer->size() > 256) {
    rolling_buffer->erase(
        rolling_buffer->begin(),
        rolling_buffer->end() - (kFrameLength * 2 - 1));
  }

  // Search from back to front for the newest valid frame header.
  if (rolling_buffer->size() < kFrameLength) return false;

  for (std::size_t i = rolling_buffer->size() - kFrameLength;
       i != static_cast<std::size_t>(-1); --i) {
    if ((*rolling_buffer)[i] == kFrameHeader0 &&
        (*rolling_buffer)[i + 1] == kFrameHeader1) {
      std::memcpy(out->data.data(), rolling_buffer->data() + i, kFrameLength);
      if (ValidateFrame(*out)) {
        return true;
      }
    }
  }
  return false;
}

void FrameToState(const Frame& frame, State* out_state) {
  if (out_state == nullptr) return;

  out_state->pos = static_cast<float>(frame.Pos()) / 255.0f;
  out_state->force = static_cast<float>(frame.Force()) / 255.0f;
  out_state->vel = 0.0f;

  std::uint8_t st = frame.State();
  if (st == static_cast<std::uint8_t>(Status::kArrived)) {
    out_state->status = Status::kArrived;
  } else if (st == static_cast<std::uint8_t>(Status::kMoving)) {
    out_state->status = Status::kMoving;
  } else if (st == static_cast<std::uint8_t>(Status::kStalled)) {
    out_state->status = Status::kStalled;
  } else if (st == static_cast<std::uint8_t>(Status::kDropped)) {
    out_state->status = Status::kDropped;
  } else {
    out_state->status = Status::kUnknown;
  }

  std::memcpy(out_state->raw_frame.data(), frame.data.data(), kFrameLength);
}

bool FrameParser::Feed(const std::uint8_t* raw, std::size_t len, Frame* out) {
  return ParseNewestFrame(raw, len, out, &buffer_);
}

}  // namespace detail
}  // namespace op_control

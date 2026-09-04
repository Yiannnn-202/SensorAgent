#ifndef ARM_CONTROL__TYPES_HPP_
#define ARM_CONTROL__TYPES_HPP_

#include <cstdint>

namespace arm_control {

enum class ErrorCode : int32_t {
  kOk = 0,
  kBusy = 1,
  kInvalidRequest = 2,
  kArmDriverError = 3,
  kTimeout = 4,
  kNotInitialized = 5,
  kInternalError = 6,
};

enum class ArmState : uint8_t {
  kIdle = 0,
  kMoving = 1,
  kError = 2,
};

constexpr double kDegToRad = 3.14159265358979323846 / 180.0;
constexpr double kRadToDeg = 180.0 / 3.14159265358979323846;

}  // namespace arm_control

#endif  // ARM_CONTROL__TYPES_HPP_

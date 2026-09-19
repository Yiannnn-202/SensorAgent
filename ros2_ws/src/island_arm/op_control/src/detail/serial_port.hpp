// Copyright 2025 op_control authors
// Internal POSIX serial port wrapper.

#ifndef OP_CONTROL_DETAIL_SERIAL_PORT_HPP_
#define OP_CONTROL_DETAIL_SERIAL_PORT_HPP_

#include <cstddef>
#include <cstdint>
#include <string>

namespace op_control {
namespace detail {

/// RAII wrapper for POSIX serial port (termios + select).
class SerialPort {
 public:
  SerialPort();
  ~SerialPort();

  SerialPort(const SerialPort&) = delete;
  SerialPort& operator=(const SerialPort&) = delete;

  bool Open(const std::string& port, int baudrate);
  void Close();
  bool IsOpen() const;

  bool Write(const std::uint8_t* data, std::size_t len);

  /// Reads up to @p len bytes with @p timeout_ms.
  /// Returns number of bytes read, 0 on timeout, -1 on error.
  int Read(std::uint8_t* buf, std::size_t len, int timeout_ms);

  bool FlushInput();

 private:
  int fd_;
};

}  // namespace detail
}  // namespace op_control

#endif  // OP_CONTROL_DETAIL_SERIAL_PORT_HPP_

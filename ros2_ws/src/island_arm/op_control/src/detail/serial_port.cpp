// Copyright 2025 op_control authors

#include "detail/serial_port.hpp"

#include <fcntl.h>
#include <sys/select.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>

namespace op_control {
namespace detail {

namespace {

bool ToSpeed(int baudrate, speed_t* speed) {
  if (speed == nullptr) return false;
  switch (baudrate) {
    case 9600:
      *speed = B9600;
      return true;
    case 19200:
      *speed = B19200;
      return true;
    case 38400:
      *speed = B38400;
      return true;
    case 57600:
      *speed = B57600;
      return true;
    case 115200:
      *speed = B115200;
      return true;
    default:
      return false;
  }
}

}  // namespace

SerialPort::SerialPort() : fd_(-1) {}

SerialPort::~SerialPort() { Close(); }

bool SerialPort::Open(const std::string& port, int baudrate) {
  Close();

  fd_ = ::open(port.c_str(), O_RDWR | O_NOCTTY | O_SYNC);
  if (fd_ < 0) {
    return false;
  }

  struct termios tty;
  if (::tcgetattr(fd_, &tty) != 0) {
    Close();
    return false;
  }

  speed_t speed;
  if (!ToSpeed(baudrate, &speed) || ::cfsetospeed(&tty, speed) != 0 ||
      ::cfsetispeed(&tty, speed) != 0) {
    Close();
    return false;
  }

  tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
  tty.c_iflag = 0;
  tty.c_lflag = 0;
  tty.c_oflag = 0;
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;

  tty.c_cflag |= (CLOCAL | CREAD);
  tty.c_cflag &= ~(PARENB | PARODD);
  tty.c_cflag &= ~CSTOPB;
  tty.c_cflag &= ~CRTSCTS;

  if (::tcsetattr(fd_, TCSANOW, &tty) != 0) {
    Close();
    return false;
  }

  return true;
}

void SerialPort::Close() {
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
}

bool SerialPort::IsOpen() const { return fd_ >= 0; }

bool SerialPort::Write(const std::uint8_t* data, std::size_t len) {
  if (!IsOpen() || data == nullptr) return false;

  std::size_t written = 0;
  while (written < len) {
    ssize_t n = ::write(fd_, data + written, len - written);
    if (n < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    if (n == 0) return false;
    written += static_cast<std::size_t>(n);
  }
  return true;
}

int SerialPort::Read(std::uint8_t* buf, std::size_t len, int timeout_ms) {
  if (!IsOpen() || buf == nullptr) return -1;

  fd_set rfds;
  FD_ZERO(&rfds);
  FD_SET(fd_, &rfds);

  struct timeval tv;
  tv.tv_sec = timeout_ms / 1000;
  tv.tv_usec = (timeout_ms % 1000) * 1000;

  int ret = ::select(fd_ + 1, &rfds, nullptr, nullptr, &tv);
  if (ret < 0) {
    if (errno == EINTR) return 0;
    return -1;
  }
  if (ret == 0) return 0;

  ssize_t n = ::read(fd_, buf, len);
  if (n < 0) {
    if (errno == EAGAIN || errno == EINTR) return 0;
    return -1;
  }
  return static_cast<int>(n);
}

bool SerialPort::FlushInput() {
  if (!IsOpen()) return false;
  return ::tcflush(fd_, TCIFLUSH) == 0;
}

}  // namespace detail
}  // namespace op_control

"""Typed errors for tool registration and invocation."""


class ToolError(Exception):
  """Base class for tool-related errors."""


class ToolRegistrationError(ToolError):
  """Raised when a tool cannot be registered."""


class ToolNotFoundError(ToolError):
  """Raised when a requested tool is not registered."""


class ToolExecutionError(ToolError):
  """Raised when a tool fails unexpectedly during execution."""


class ToolValidationError(ToolError):
  """Raised when tool input or output does not match its contract."""


class ToolTimeoutError(ToolError):
  """Raised when a tool invocation exceeds its timeout."""

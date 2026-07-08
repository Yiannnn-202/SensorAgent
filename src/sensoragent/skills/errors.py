"""Typed errors for skill registration and invocation."""


class SkillError(Exception):
  """Base class for skill-related errors."""


class SkillRegistrationError(SkillError):
  """Raised when a skill cannot be registered."""


class SkillNotFoundError(SkillError):
  """Raised when a requested skill is not registered."""


class SkillExecutionError(SkillError):
  """Raised when a skill fails unexpectedly during execution."""

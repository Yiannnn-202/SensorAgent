"""Typed errors for workflow execution."""


class WorkflowError(Exception):
  """Base class for workflow-related errors."""


class WorkflowTemplateError(WorkflowError):
  """Raised when workflow input templating fails."""


class WorkflowExecutionError(WorkflowError):
  """Raised when workflow execution fails unexpectedly."""

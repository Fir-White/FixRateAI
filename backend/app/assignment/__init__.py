"""ALG03: pure crew selection, without saving assignments."""
from .schemas import AssignmentRequest, AssignmentSelection
from .selection import select_crew

__all__ = ["AssignmentRequest", "AssignmentSelection", "select_crew"]

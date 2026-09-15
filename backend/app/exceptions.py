class QualificationFailedError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class FollowUpConflictError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidStatusTransitionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        stage: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.stage = stage

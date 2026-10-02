class ApplicationError(Exception):
    """Application failure translated into HTTP only at the API boundary."""
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class AppException(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(AppException):
    def __init__(self, message):
        super().__init__(message, 400)

class NotFoundError(AppException):
    def __init__(self, message):
        super().__init__(message, 404)

class AuthenticationError(AppException):
    def __init__(self, message):
        super().__init__(message, 401)

class AuthorizationError(AppException):
    def __init__(self, message):
        super().__init__(message, 403)

class InsufficientCreditsError(AppException):
    def __init__(self, balance, required):
        super().__init__(f'Insufficient credits. You have {balance}, need {required}', 400)
        self.balance = balance
        self.required = required

class JobStatusError(AppException):
    def __init__(self, message):
        super().__init__(message, 400)

class ExtractionError(AppException):
    def __init__(self, message):
        super().__init__(message, 500)

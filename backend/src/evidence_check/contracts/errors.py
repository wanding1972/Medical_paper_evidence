"""Stable errors without raw input data in their message."""


class EvidenceCheckError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class InputError(EvidenceCheckError):
    pass


class PolicyError(EvidenceCheckError):
    pass


class DocumentReadError(EvidenceCheckError):
    pass


class TaskStepError(EvidenceCheckError):
    def __init__(self,code: str,message: str,diagnostics: dict):
        super().__init__(code,message)
        self.diagnostics=diagnostics

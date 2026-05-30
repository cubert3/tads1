"""Core detection pipeline modules."""

__all__ = ["AccidentDetectionProcessor"]


def __getattr__(name: str):
    if name == "AccidentDetectionProcessor":
        from core.processor import AccidentDetectionProcessor
        return AccidentDetectionProcessor
    raise AttributeError(name)

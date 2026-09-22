from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolReconciliationQualification:
    green_tool_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.green_tool_keys, tuple):
            raise TypeError('green_tool_keys must be a tuple')
        normalized: list[str] = []
        seen: set[str] = set()
        for tool_key in self.green_tool_keys:
            _require_non_empty_string(tool_key, 'tool_key')
            if tool_key in seen:
                raise ValueError('green_tool_keys must not contain duplicates')
            seen.add(tool_key)
            normalized.append(tool_key)
        object.__setattr__(self, 'green_tool_keys', tuple(sorted(normalized)))

    def is_green(self, tool_key: str) -> bool:
        _require_non_empty_string(tool_key, 'tool_key')
        return tool_key in self.green_tool_keys


@dataclass(frozen=True, slots=True, order=True)
class EvaluatorQualificationKey:
    family_key: str
    evaluator_key: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.family_key, 'family_key')
        _require_non_empty_string(self.evaluator_key, 'evaluator_key')


@dataclass(frozen=True, slots=True)
class EvaluatorQualificationCatalog:
    qualified_keys: tuple[EvaluatorQualificationKey, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.qualified_keys, tuple):
            raise TypeError('qualified_keys must be a tuple')
        normalized: list[EvaluatorQualificationKey] = []
        seen: set[EvaluatorQualificationKey] = set()
        for key in self.qualified_keys:
            if not isinstance(key, EvaluatorQualificationKey):
                raise TypeError('qualified_keys must contain EvaluatorQualificationKey values')
            if key in seen:
                raise ValueError('qualified_keys must not contain duplicates')
            seen.add(key)
            normalized.append(key)
        object.__setattr__(self, 'qualified_keys', tuple(sorted(normalized)))

    def is_qualified(self, family_key: str, evaluator_key: str) -> bool:
        return (
            EvaluatorQualificationKey(
                family_key=family_key,
                evaluator_key=evaluator_key,
            )
            in self.qualified_keys
        )


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')

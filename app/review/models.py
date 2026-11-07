from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewerRequest(StrictModel):
    name: str = Field(min_length=2, max_length=80)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError("Enter your name")
        return value.strip()


class DecisionRequest(StrictModel):
    version: int = Field(ge=1)
    action: Literal["accepted", "edited", "rejected", "clarification_requested"]
    reason: str = Field(min_length=3, max_length=2000)
    edited_text: str | None = Field(default=None, max_length=10000)
    edited_data: dict[str, str] | None = None

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("A reason is required")
        return value.strip()


class VersionRequest(StrictModel):
    version: int = Field(ge=1)


class ClarificationRequest(VersionRequest):
    action: Literal["answer", "skip"]
    values: dict[str, str | float | bool] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=2000)


class FindingClarificationRequest(VersionRequest):
    response: str = Field(min_length=3, max_length=4000)

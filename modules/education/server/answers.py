"""Output schema and citation rules preserved from QJQ."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Citation(BaseModel):
    """A source reference that must exist in the supplied context."""

    model_config = ConfigDict(extra="forbid")
    source_id: str
    quote: str


class EducationAnswer(BaseModel):
    """Strict output schema for the education system prompt."""

    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern=r"^(answer|hint|quiz|plan|notice)$")
    answer: str
    citations: list[Citation]
    uncertainty: list[str]
    next_steps: list[str]

    @model_validator(mode="after")
    def require_evidence_or_uncertainty(self) -> "EducationAnswer":
        """Keep source-free claims visibly uncertain."""
        if not self.citations and not self.uncertainty:
            raise ValueError("Provide citations or explicitly record uncertainty")
        return self

from pydantic import BaseModel, Field


class IssueReportCreate(BaseModel):
    description: str = Field(min_length=1)

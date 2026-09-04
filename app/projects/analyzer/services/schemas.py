from typing import List, Optional
from pydantic import BaseModel, Field


class PositiveSignal(BaseModel):
    description: str = Field(description="One-sentence description of the matching strength or qualification")
    keywords: List[str] = Field(default_factory=list, description="List of matching skill keywords")


class NegativeSignal(BaseModel):
    description: str = Field(description="One-sentence description of missing skill, gap, or mismatch")
    keywords: List[str] = Field(default_factory=list, description="List of missing or weak skill keywords")


class ResumeEvaluationOutput(BaseModel):
    percent_match: int = Field(ge=0, le=100, description="Overall matching score from 0 to 100")
    positive: List[PositiveSignal] = Field(default_factory=list, description="Strengths and matching qualifications")
    negative: List[NegativeSignal] = Field(default_factory=list, description="Gaps, missing requirements, or concerns")
    description: str = Field(description="Executive summary of the candidate's alignment with the role")


class TechnicalQuestionSet(BaseModel):
    repo: str = Field(description="Name of the repository, project, or role section (e.g., 'Job Description', 'Experience')")
    questions: List[str] = Field(default_factory=list, description="Interview questions targeting technical depth")
    summary: str = Field(default="", description="Summary of the code or technical domain evaluated")
    source: str = Field(default="jd", description="Source category: 'github', 'jd', 'experience', or 'project'")


class CandidateAnalysisResult(BaseModel):
    file_name: str
    pdf_path: str
    match_report: ResumeEvaluationOutput
    question_sets: List[TechnicalQuestionSet]
    github_questions: List[TechnicalQuestionSet]
    links: List[dict] = Field(default_factory=list)
    resume_text: str = ""

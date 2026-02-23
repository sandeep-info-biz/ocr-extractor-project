from typing import List, Optional

from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    degree: str
    field_of_study: str
    institution: str
    graduation_year: int | None = None


class ResumeExtractedResponse(BaseModel):
    first_name: str = ""
    last_name: str = ""
    phone_number: str = ""
    email: str = ""
    date_of_birth: str = ""
    gender: str = ""
    religion: str = ""
    marital_status: str = ""
    nationality_country_name: str = ""
    country_region: str = ""
    city: str = ""
    postal_code: str = ""
    languages: List[str] = Field(default_factory=list)
    industry_type: str = ""
    designation_or_position: str = ""
    total_experience: int | None = None
    gulf_expierence: bool = False
    passport_number: str = ""
    passport_expiry_date: str = ""
    skills: List[str] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    education_degree: str = ""
    about_description_summary: str = ""
    linkedin_url: str = ""
    raw_text: str = ""


class RetrainMappingRequest(BaseModel):
    new_entries: List[ResumeExtractedResponse]
    append_to_existing: bool = True
    run_check: bool = True


class RetrainMappingResponse(BaseModel):
    dataset_path: str
    model_path: str
    total_dataset_entries: int
    added_entries: int
    mapping_counts: dict
    check_average_overall_score: float | None = None


class ExtractionWithTokenResponse(BaseModel):
    token_id: str
    extracted_data: ResumeExtractedResponse


class FeedbackRequest(BaseModel):
    token_id: str
    extracted_data: Optional[ResumeExtractedResponse] = None
    rating: int = 5
    corrected_data: Optional[ResumeExtractedResponse] = None
    retrain_on_submit: bool = True


class FeedbackResponse(BaseModel):
    token_id: str
    rating: int
    retrained: bool
    total_dataset_entries: int
    mapping_counts: dict
    feedback_weight: int = 1
    feedback_accuracy: float | None = None


class ModelCompareReport(BaseModel):
    ml_mode: str
    llm_mode: str
    agreement_ratio: float
    ml_completeness_ratio: float
    llm_completeness_ratio: float
    per_field_agreement: dict


class ExtractionCompareResponse(BaseModel):
    token_id: str
    ml_output: ResumeExtractedResponse
    llm_output: ResumeExtractedResponse
    compare_report: ModelCompareReport
    ml_legacy_eval: Optional[dict] = None
    llm_legacy_eval: Optional[dict] = None
    ml_full_schema_eval: Optional[dict] = None
    llm_full_schema_eval: Optional[dict] = None
    ml_error: Optional[str] = None
    llm_error: Optional[str] = None
    llm_debug: Optional[List[str]] = None
    ground_truth_error: Optional[str] = None


class AutoTrainLLMResponse(BaseModel):
    token_id: str
    trained: bool
    added_entries: int
    total_dataset_entries: int
    dataset_path: str
    model_path: str
    mapping_counts: dict
    llm_output: ResumeExtractedResponse
    extracted_data: Optional[ResumeExtractedResponse] = None
    rating: int = 5
    corrected_data: Optional[ResumeExtractedResponse] = None
    retrain_on_submit: bool = True
    llm_error: Optional[str] = None
    llm_debug: Optional[List[str]] = None


class AutoTrainResponse(BaseModel):
    token_id: str
    trained: bool
    added_entries: int
    total_dataset_entries: int
    dataset_path: str
    model_path: str
    mapping_counts: dict
    extracted_data: ResumeExtractedResponse
    parse_error: Optional[str] = None
    debug: Optional[List[str]] = None

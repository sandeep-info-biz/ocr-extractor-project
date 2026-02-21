import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?:(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4})"
)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+\b", re.IGNORECASE)

SECTION_HEADERS = {
    "summary": ["summary", "professional summary", "profile", "objective"],
    "education": ["education", "academic background", "qualification"],
    "experience": ["experience", "work history", "employment history", "professional experience"],
    "skills": ["skills", "technical skills", "core competencies", "expertise"],
    "languages": ["languages", "language proficiency"],
    "projects": ["projects", "personal projects", "professional projects"],
    "certifications": ["certifications", "certificates", "licenses"],
}

DEFAULT_SKILLS = [
    "python", "java", "javascript", "typescript", "sql", "mysql", "postgresql", "mongodb",
    "aws", "azure", "gcp", "docker", "kubernetes", "git", "linux", "pandas", "numpy",
    "scikit-learn", "tensorflow", "pytorch", "nlp", "spacy", "opencv", "flask", "django",
    "fastapi", "react", "node.js", "excel", "power bi",
]

DEGREE_HINTS = [
    "b.tech", "b.e", "b.sc", "bca", "m.tech", "m.e", "m.sc", "mca", "mba",
    "bachelor", "master", "phd", "doctorate", "diploma",
]

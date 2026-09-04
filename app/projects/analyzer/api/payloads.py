FIELD_DEFINITIONS = [
    {"name": "full_name", "label": "Full Name", "type": "text", "data_type": "text"},
    {"name": "email", "label": "Email", "type": "email", "data_type": "email"},
    {"name": "phone", "label": "Phone Number", "type": "tel", "data_type": "tel"},
    {"name": "resume", "label": "Resume / CV", "type": "file", "data_type": "file", "accept": ["pdf", "doc", "docx"]},
    {"name": "experience_years", "label": "Years of Experience", "type": "number", "data_type": "number"},
    {"name": "github_url", "label": "GitHub Profile", "type": "text", "data_type": "text"},
    {"name": "linkedin_url", "label": "LinkedIn Profile", "type": "text", "data_type": "text"},
    {"name": "portfolio", "label": "Portfolio URL", "type": "text", "data_type": "text"},
    {"name": "current_company", "label": "Current Company", "type": "text", "data_type": "text"},
    {"name": "expected_ctc", "label": "Expected Compensation", "type": "text", "data_type": "text"},
    {"name": "notice_period", "label": "Notice Period", "type": "text", "data_type": "text"},
    {"name": "city", "label": "Current City", "type": "text", "data_type": "text"},
    {"name": "address", "label": "Address", "type": "text", "data_type": "text"},
    {"name": "dob", "label": "Date of Birth", "type": "date", "data_type": "date"},
    {"name": "age", "label": "Age", "type": "number", "data_type": "number"},
    {"name": "gender", "label": "Gender", "type": "text", "data_type": "text"},
    {"name": "country", "label": "Country", "type": "text", "data_type": "text"},
]

CUSTOM_FIELD_TYPES = [
    {"value": "text", "label": "Text"},
    {"value": "file", "label": "File (Resume/Docs)"},
    {"value": "number", "label": "Number"},
    {"value": "email", "label": "Email"},
    {"value": "date", "label": "Date"},
]

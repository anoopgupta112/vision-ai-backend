TEMPLATES = {
    "HR": [
        {"name": "full_name", "label": "Full Name", "data_type": "text"},
        {"name": "email", "label": "Email", "data_type": "email"},
        {"name": "phone", "label": "Phone Number", "data_type": "tel"},
        {"name": "resume", "label": "Resume", "data_type": "file", "accept": ["pdf", "docx"]},
    ],
    "College": [
        {"name": "student_name", "label": "Student Name", "data_type": "text"},
        {"name": "roll_no", "label": "Roll Number", "data_type": "text"},
        {"name": "course", "label": "Course", "data_type": "text"},
        {"name": "marksheet", "label": "Marksheet", "data_type": "file", "accept": ["pdf"]},
    ],
}


def get_all_templates():
    return [{"name": key, "fields": value} for key, value in TEMPLATES.items()]


def get_template_by_name(name: str):
    return TEMPLATES.get(name)

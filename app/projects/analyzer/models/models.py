from typing import Any, Dict, List


class FormDefinition:
    def __init__(self, fields: List[Dict[str, Any]]):
        self.fields = fields
        self.submissions = []

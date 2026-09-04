import os
from typing import List, Dict, Any

from app.projects.analyzer.services.analysis_graph import run_candidate_analysis


def process_uploaded_pdfs(pdf_files: list, jd: str, save_dir: str) -> List[Dict[str, Any]]:
    results = []

    for pdf in pdf_files:
        base_name = os.path.basename(pdf.filename)
        save_path = os.path.join(save_dir, base_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        pdf.save(save_path)

        analysis = run_candidate_analysis(
            pdf_path=save_path,
            jd=jd,
            file_name=base_name,
        )

        results.append(
            {
                "pdf_path": base_name,
                "file_name": base_name,
                "match_report": analysis.get("match_report", {}),
                "links": analysis.get("links", []),
                "question_sets": analysis.get("question_sets", []),
                "github_questions": analysis.get("github_questions", []),
                "resume_text": analysis.get("resume_text", ""),
            }
        )

    return results


"""Explainable, deterministic candidate-to-job matching."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .db import connect

TECH_TERMS = {
    "Python",
    "C++",
    "Java",
    "Go",
    "SQL",
    "PyTorch",
    "TensorFlow",
    "PaddlePaddle",
    "Transformers",
    "DeepSpeed",
    "vLLM",
    "CUDA",
    "Docker",
    "Kubernetes",
    "Linux",
    "OCR",
    "VLM",
    "LLM",
    "Agent",
    "RAG",
    "MCP",
    "FAISS",
    "CLIP",
    "Qwen",
    "InternVL",
    "LLaVA",
    "OpenCV",
    "YOLO",
    "DBNet",
    "PPO",
    "DPO",
    "GRPO",
    "SFT",
    "RLHF",
    "多模态",
    "内容安全",
    "目标检测",
    "图像分类",
    "模型量化",
    "分布式训练",
    "微调",
    "推理优化",
    "向量检索",
    "智能体",
    "数据清洗",
}


def load_profile(path: str | Path) -> dict:
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    profile.setdefault("skills", [])
    profile.setdefault("target_titles", [])
    profile.setdefault("target_directions", [])
    profile.setdefault("preferred_locations", [])
    profile.setdefault("excluded_terms", [])
    return profile


def _contains(text: str, term: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", term):
        return term.lower() in text.lower()
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I) is not None


def infer_job_skills(text: str, declared: list[str]) -> list[str]:
    explicit = sorted(set(str(term).strip() for term in declared if str(term).strip()))
    if explicit:
        return explicit
    return sorted(term for term in TECH_TERMS if _contains(text, term))


def score_job(job: dict, profile: dict) -> dict:
    title = str(job.get("title") or "")
    description = str(job.get("description") or "")
    location = str(job.get("location") or "")
    text = f"{title}\n{description}"
    candidate_skills = {str(item).lower(): str(item) for item in profile["skills"]}
    job_skills = infer_job_skills(text, job.get("skills", []))
    matched = [skill for skill in job_skills if skill.lower() in candidate_skills]
    missing = [skill for skill in job_skills if skill.lower() not in candidate_skills]

    skill_score = 20.0 if not job_skills else 55.0 * len(matched) / len(job_skills)
    title_hits = [term for term in profile["target_titles"] if _contains(title, str(term))]
    title_score = min(20.0, 10.0 * len(title_hits))
    direction_hits = [term for term in profile["target_directions"] if _contains(text, str(term))]
    direction_score = min(15.0, 5.0 * len(direction_hits))
    location_hits = [
        term for term in profile["preferred_locations"] if _contains(location, str(term))
    ]
    location_score = 10.0 if location_hits else 0.0
    exclusions = [term for term in profile["excluded_terms"] if _contains(text, str(term))]
    penalty = min(40.0, 20.0 * len(exclusions))
    score = max(
        0.0, min(100.0, skill_score + title_score + direction_score + location_score - penalty)
    )

    if score >= 80:
        recommendation = "must_review"
    elif score >= 65:
        recommendation = "recommended"
    elif score >= 45:
        recommendation = "consider"
    else:
        recommendation = "low_match"
    reasons = []
    if matched:
        reasons.append("matched skills: " + ", ".join(matched))
    if title_hits:
        reasons.append("target title signals: " + ", ".join(map(str, title_hits)))
    if direction_hits:
        reasons.append("target directions: " + ", ".join(map(str, direction_hits)))
    if location_hits:
        reasons.append("preferred location: " + ", ".join(map(str, location_hits)))
    if exclusions:
        reasons.append("exclusion penalty: " + ", ".join(map(str, exclusions)))
    if not reasons:
        reasons.append("insufficient matching evidence")
    return {
        "score": round(score, 1),
        "recommendation": recommendation,
        "matched_skills": matched,
        "missing_skills": missing,
        "explanation": "; ".join(reasons),
    }


def score_database(db_path: str | Path, profile: dict) -> int:
    updated = 0
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM jobs").fetchall()
        for row in rows:
            job = dict(row)
            job["skills"] = json.loads(job["skills_json"])
            result = score_job(job, profile)
            connection.execute(
                """
                UPDATE jobs SET match_score=?, recommendation=?, matched_skills_json=?,
                    missing_skills_json=?, match_explanation=? WHERE job_id=?
                """,
                (
                    result["score"],
                    result["recommendation"],
                    json.dumps(result["matched_skills"], ensure_ascii=False),
                    json.dumps(result["missing_skills"], ensure_ascii=False),
                    result["explanation"],
                    row["job_id"],
                ),
            )
            updated += 1
    return updated

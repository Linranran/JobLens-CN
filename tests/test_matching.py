from joblens.matching import score_job


def test_matching_is_explainable():
    job = {
        "title": "多模态算法工程师",
        "location": "北京",
        "description": "使用 Python、PyTorch、OCR 和 VLM 进行多模态模型微调。",
        "skills": ["Python", "PyTorch", "OCR", "VLM"],
    }
    profile = {
        "skills": ["Python", "PyTorch", "OCR", "VLM"],
        "target_titles": ["算法工程师"],
        "target_directions": ["多模态", "OCR"],
        "preferred_locations": ["北京"],
        "excluded_terms": ["实习"],
    }
    result = score_job(job, profile)
    assert result["score"] >= 80
    assert result["recommendation"] == "must_review"
    assert "Python" in result["matched_skills"]
    assert "matched skills" in result["explanation"]


def test_excluded_term_reduces_score():
    profile = {
        "skills": ["Python"],
        "target_titles": ["算法工程师"],
        "target_directions": [],
        "preferred_locations": ["北京"],
        "excluded_terms": ["实习"],
    }
    base = {"title": "算法工程师", "location": "北京", "skills": ["Python"]}
    regular = score_job({**base, "description": "Python 开发"}, profile)
    internship = score_job({**base, "description": "Python 实习岗位"}, profile)
    assert internship["score"] < regular["score"]

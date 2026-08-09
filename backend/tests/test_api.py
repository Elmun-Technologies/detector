from fastapi.testclient import TestClient

from app.main import app
from app.scoring import normalized_weights


def sample_context() -> dict:
    return {
        "title": "Retention uchun 3 signal",
        "topic": "Instagram Reels retentionini oshirish uchun checklist",
        "transcript": "Video nega to‘xtaydi? Mana 3 ta qadam. Keyingi video uchun saqlab qo‘ying.",
        "duration_seconds": 34,
        "width": 1080,
        "height": 1920,
        "has_subtitles": True,
        "audience": "SMM mutaxassislari va kichik biznes egalari",
        "account": {"account_type": "expert", "average_views": 12000},
    }


def test_expert_weights_are_normalized_and_prioritize_retention() -> None:
    weights = normalized_weights("expert")
    assert round(sum(weights.values()), 8) == 1
    assert weights["retention"] > 0.20
    assert weights["save"] > 0.10


def test_manual_analysis_reaches_completed_state() -> None:
    with TestClient(app) as client:
        created = client.post("/v1/analyses", json={"context": sample_context()})
        assert created.status_code == 202
        job_id = created.json()["id"]
        # TestClient runs scheduled asyncio tasks on the same event loop.
        import time
        time.sleep(0.35)
        fetched = client.get(f"/v1/analyses/{job_id}")
        assert fetched.status_code == 200
        payload = fetched.json()
        assert payload["status"] == "completed"
        assert 0 <= payload["report"]["scores"]["viral_score"] <= 100
        assert payload["report"]["disclaimer"]


def test_idea_endpoint_labels_fact_check_work() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/ideas/check",
            json={"idea": "2026-yilda O‘zbekistonda qaysi reklama kanallari ishlaydi?", "objective": "save"},
        )
    assert response.status_code == 200
    result = response.json()
    assert result["fact_check_needed"]
    assert result["potential_score"] >= 45


def test_video_upload_accepts_supported_format_and_creates_job() -> None:
    import json

    with TestClient(app) as client:
        response = client.post(
            "/v1/analyses/upload",
            data={"context": json.dumps(sample_context())},
            files={"file": ("clip.mp4", b"not-a-real-video-in-test", "video/mp4")},
        )
    assert response.status_code == 202
    assert response.json()["source_filename"] == "clip.mp4"

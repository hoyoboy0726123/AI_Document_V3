import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parents[1]
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def login():
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "Admin@123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def run_classification_flow(token: str):
    headers = auth_headers(token)

    start_resp = client.get("/api/v1/classification-guide/start", headers=headers)
    start_resp.raise_for_status()
    payload = start_resp.json()

    session_id = payload["session_id"]
    question = payload["question"]

    current = question
    while True:
        option = current["options"][0]
        answer_resp = client.post(
            "/api/v1/classification-guide/answer",
            json={
                "session_id": session_id,
                "question_id": current["id"],
                "selected_option_id": option["id"],
            },
            headers=headers,
        )
        answer_resp.raise_for_status()
        data = answer_resp.json()
        if data.get("suggestion"):
            suggestion = data["suggestion"]
            print("Final suggestion classification_id:", suggestion["classification_id"])
            return data["suggestion"]["classification_id"]
        current = data["question"]


def run_document_flow(token: str, classification_id: str):
    headers = auth_headers(token)

    create_resp = client.post(
        "/api/v1/documents",
        json={
            "title": "季度財務報告",
            "content": "這是測試用的財務報告內容。",
            "metadata": {
                "file_type": "report",
                "project_id": "proj_alpha",
                "keywords": ["finance"],
            },
        },
        headers=headers,
    )
    create_resp.raise_for_status()
    document = create_resp.json()
    document_id = document["id"]

    apply_resp = client.post(
        f"/api/v1/documents/{document_id}/classify",
        json={"classification_id": classification_id},
        headers=headers,
    )
    apply_resp.raise_for_status()
    print("Document classification applied.")


if __name__ == "__main__":
    token = login()
    classification_id = run_classification_flow(token)
    run_document_flow(token, classification_id)
    print("All tests passed.")

from __future__ import annotations

import os

import requests

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_API = "https://api.linkedin.com/v2"


def get_linkedin_urn() -> str | None:
    response = requests.get(
        f"{LINKEDIN_API}/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=10,
    )
    if response.ok:
        subject = response.json().get("sub")
        return f"urn:li:person:{subject}" if subject and not subject.startswith("urn") else subject

    print(f"LinkedIn auth error: {response.status_code} - {response.text}")
    return None


def check_linkedin_connection() -> bool:
    response = requests.get(
        f"{LINKEDIN_API}/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=10,
    )
    if response.ok:
        data = response.json()
        print(f"Connected to LinkedIn as: {data.get('name')} ({data.get('email')})")
        return True

    print(f"LinkedIn connection error: {response.status_code} - {response.text}")
    return False


def publish_to_linkedin(post: dict) -> dict | None:
    urn = get_linkedin_urn()
    if not urn:
        return None

    tags_str = " ".join(f"#{tag.replace(' ', '')}" for tag in post.get("tags", []))
    body = post["body"][:2800].strip()
    source_url = post.get("source_url", "").strip()

    text = (
        f"{post['title']}\n\n"
        f"{body}\n\n"
        f"{source_url}\n\n"
        f"{tags_str}"
    ).strip()

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
        },
    }

    try:
        response = requests.post(
            f"{LINKEDIN_API}/ugcPosts",
            headers={
                "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        print("Posted to LinkedIn.")
        print(f"Post ID: {data.get('id', 'n/a')}")
        return data

    except Exception as error:
        print(f"LinkedIn publish error: {error}")
        if hasattr(error, "response") and error.response is not None:
            print(f"Details: {error.response.text}")
        return None


if __name__ == "__main__":
    print("Checking LinkedIn connection...\n")
    if check_linkedin_connection():
        test_post = {
            "title": "Test Post from News AI Parser",
            "body": "This is a test post generated automatically.",
            "tags": ["cybersecurity", "devops", "automation"],
            "source_url": "https://example.com",
        }
        print("\nPublishing test post...\n")
        publish_to_linkedin(test_post)

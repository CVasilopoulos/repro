import re
from dataclasses import dataclass

import httpx

ISSUE_RE = re.compile(r"^https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/(\d+)/?(?:[#?].*)?$")
API = "https://api.github.com"
BODY_LIMIT = 12000
COMMENT_LIMIT = 3


@dataclass
class Issue:
    owner: str
    repo: str
    number: int
    url: str
    title: str
    body: str
    author: str
    created_at: str
    state: str
    labels: list[str]
    comments: list[dict]
    default_branch: str
    clone_url: str
    language: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_issue_url(url: str) -> tuple[str, str, int]:
    m = ISSUE_RE.match(url.strip())
    if not m:
        raise ValueError("expected a GitHub issue URL like https://github.com/owner/repo/issues/123")
    return m.group(1), m.group(2), int(m.group(3))


def _headers(token: str) -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "repro-agent", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def fetch_issue(url: str, token: str = "") -> Issue:
    owner, repo, number = parse_issue_url(url)
    async with httpx.AsyncClient(timeout=20, headers=_headers(token)) as http:
        r = await http.get(f"{API}/repos/{owner}/{repo}/issues/{number}")
        if r.status_code == 404:
            raise ValueError("issue not found (private repository or wrong number)")
        r.raise_for_status()
        issue = r.json()
        if "pull_request" in issue:
            raise ValueError("that is a pull request, not an issue")
        rr = await http.get(f"{API}/repos/{owner}/{repo}")
        rr.raise_for_status()
        meta = rr.json()
        comments = []
        if issue.get("comments"):
            rc = await http.get(issue["comments_url"], params={"per_page": COMMENT_LIMIT})
            if rc.status_code == 200:
                comments = [
                    {"author": c["user"]["login"], "body": (c.get("body") or "")[:3000]} for c in rc.json()
                ]
    return Issue(
        owner=meta["owner"]["login"],
        repo=meta["name"],
        number=number,
        url=issue["html_url"],
        title=issue["title"],
        body=(issue.get("body") or "")[:BODY_LIMIT],
        author=issue["user"]["login"],
        created_at=issue["created_at"],
        state=issue["state"],
        labels=[l["name"] for l in issue.get("labels", [])],
        comments=comments,
        default_branch=meta["default_branch"],
        clone_url=meta["clone_url"],
        language=meta.get("language") or "",
    )


async def post_comment(full_name: str, number: int, body: str, token: str) -> str:
    async with httpx.AsyncClient(timeout=20, headers=_headers(token)) as http:
        r = await http.post(f"{API}/repos/{full_name}/issues/{number}/comments", json={"body": body})
        r.raise_for_status()
        return r.json()["html_url"]

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import git
import os
import shutil
import re
import stat
import requests
from urllib.parse import urlparse, quote

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ✅ Fix Windows permission issue
def remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


class RepoRequest(BaseModel):
    repo_url: str
    token: str = ""


@app.post("/check-repo")
def check_repo(data: RepoRequest):
    # Parse owner/repo from URL
    parts = data.repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    
    headers = {"Accept": "application/vnd.github+json"}
    if data.token:
        headers["Authorization"] = f"Bearer {data.token}"
    
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=headers
    )
    
    if r.status_code == 200:
        info = r.json()
        return {
            "accessible": True,
            "private": info.get("private", False),
            "name": info.get("full_name"),
            "description": info.get("description", ""),
            "stars": info.get("stargazers_count", 0),
            "language": info.get("language", "")
        }
    elif r.status_code == 404:
        return {"accessible": False, "private": True, "reason": "not_found"}
    elif r.status_code == 403:
        return {"accessible": False, "private": True, "reason": "rate_limited"}
    elif r.status_code == 401:
        return {"accessible": False, "private": True, "reason": "bad_token"}
    else:
        return {"accessible": False, "reason": "unknown"}


@app.get("/")
def home():
    return {"message": "Backend running 🚀"}


# =========================
# 🔹 HELPERS
# =========================

def normalize_path(path):
    return path.replace("\\", "/").strip()


def get_file_type(file):
    if file.endswith(".py"):
        return "backend"
    elif file.endswith((".js", ".ts")):
        return "frontend"
    elif file.endswith((".html", ".css")):
        return "frontend"
    elif file.endswith(".json"):
        return "config"
    else:
        return "other"


def classify_role(file):
    f = file.lower()
    if "api" in f or "route" in f:
        return "api"
    elif "util" in f:
        return "utility"
    elif "model" in f:
        return "data"
    elif "index" in f or "main" in f:
        return "entry"
    else:
        return "general"


def simple_summary(file):
    if file.endswith(".js"):
        return "JavaScript logic file"
    elif file.endswith(".html"):
        return "UI structure file"
    elif file.endswith(".css"):
        return "Styling file"
    elif file.endswith(".py"):
        return "Backend logic file"
    else:
        return "Other file"


def resolve_relative(source, target):
    """Handles flat + nested paths"""
    return normalize_path(
        os.path.normpath(os.path.join(os.path.dirname(source), target))
    )


# =========================
# 🔹 MAIN API
# =========================

@app.post("/analyze-repo")
def analyze(data: RepoRequest):
    repo_url = data.repo_url
    repo_path = "repo"

    try:
        # 🔹 Clean old repo
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path, onerror=remove_readonly)

        # 🔹 Clone repo
        if data.token:
            parsed = urlparse(repo_url)
            # URL-encode the token to avoid "Malformed input to a URL function" errors
            safe_token = quote(data.token)
            auth_url = f"{parsed.scheme}://{safe_token}@{parsed.netloc}{parsed.path}"
            try:
                git.Repo.clone_from(auth_url, repo_path)
            except Exception as e:
                error_msg = str(e).replace(data.token, "HIDDEN_TOKEN")
                raise Exception(error_msg)
        else:
            git.Repo.clone_from(repo_url, repo_path)

        nodes = []
        edges = []
        file_scores = {}
        all_files = []

        skip_dirs = {
            ".git", "node_modules", "__pycache__", "dist", "build", ".venv"
        }

        # 🔹 FIRST PASS: Collect files and build scores
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                full_path = os.path.join(root, file)

                if os.path.getsize(full_path) > 200000:
                    continue

                relative_path = normalize_path(
                    os.path.relpath(full_path, repo_path)
                )

                all_files.append((root, file, relative_path))

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except:
                    content = ""

                # =========================
                # 🔹 JS / TS
                # =========================
                if file.endswith((".js", ".ts")):
                    imports = re.findall(r'import .* from [\'"](.*?)[\'"]', content)
                    requires = re.findall(r'require\([\'"](.*?)[\'"]\)', content)

                    for imp in imports + requires:
                        if imp.startswith("."):
                            target = resolve_relative(relative_path, imp)

                            edges.append({"source": relative_path, "target": target})

                            file_scores[target] = file_scores.get(target, 0) + 1

                # =========================
                # 🔹 HTML
                # =========================
                if file.endswith(".html"):
                    scripts = re.findall(r'<script.*src=["\'](.*?)["\']', content)
                    links = re.findall(r'<link.*href=["\'](.*?)["\']', content)

                    for src in scripts + links:
                        if not src.startswith("http"):
                            target = resolve_relative(relative_path, src)

                            edges.append({"source": relative_path, "target": target})

                            file_scores[target] = file_scores.get(target, 0) + 1

                # =========================
                # 🔹 PYTHON
                # =========================
                if file.endswith(".py"):
                    imports = re.findall(r'import (\w+)', content)

                    for imp in imports:
                        target = imp + ".py"
                        edges.append({"source": relative_path, "target": target})

        # 🔹 SECOND PASS: Build nodes with impact scores
        for root, file, relative_path in all_files:
            full_path = os.path.join(root, file)

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except:
                content = ""

            # ✅ NODE
            nodes.append({
                "id": relative_path,
                "type": get_file_type(file),
                "role": classify_role(relative_path),
                "summary": simple_summary(file),
                "preview": content[:200],
                "folder": relative_path.split("/")[0] if "/" in relative_path else "root",
                "impact": file_scores.get(relative_path, 0)
            })

        # =========================
        # 🔹 CLEAN EDGES
        # =========================
        valid_nodes = set(n["id"] for n in nodes)

        edges = [
            e for e in edges
            if normalize_path(e["target"]) in valid_nodes
        ]

        # =========================
        # 🔹 IMPORTANT FILES
        # =========================
        important_files = sorted(
            file_scores,
            key=file_scores.get,
            reverse=True
        )[:5]

        # =========================
        # 🔹 ENTRY POINTS
        # =========================
        entry_points = [
            n["id"] for n in nodes
            if "index" in n["id"] or "main" in n["id"]
        ]

        # =========================
        # 🔥 ONBOARDING PATH
        # =========================
        onboarding_path = entry_points + important_files[:3]

        # =========================
        # 🔹 LIMIT SIZE
        # =========================
        nodes = nodes[:200]
        edges = edges[:300]

        return {
            "nodes": nodes,
            "edges": edges,
            "important_files": important_files,
            "entry_points": entry_points,
            "onboarding_path": onboarding_path,
            "total_files": len(nodes),
            "debug": {
                "nodes_count": len(nodes),
                "edges_count": len(edges)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        try:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path, onerror=remove_readonly)
        except:
            pass

class QueryRequest(BaseModel):
    query: str
    nodes: list

@app.post("/query-repo")
def query_repo(data: QueryRequest):
    query_lower = data.query.lower()
    relevant = [
        n for n in data.nodes
        if query_lower in n["id"].lower() or
           (n.get("summary") and query_lower in n.get("summary").lower()) or
           query_lower in n.get("role", "").lower() or
           query_lower in n.get("type", "").lower()
    ]
    
    # Rank by impact score descending
    relevant_sorted = sorted(relevant, key=lambda n: n.get("impact", 0), reverse=True)
    
    return {
        "explanation": f"Based on your query '{data.query}', we found {len(relevant)} relevant file(s).",
        "relevant_paths": [n["id"] for n in relevant_sorted[:5]]
    }
import json
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


def remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


class RepoRequest(BaseModel):
    repo_url: str
    token: str = ""


@app.post("/check-repo")
def check_repo(data: RepoRequest):
    repo_url = data.repo_url.rstrip("/")
    import subprocess
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        if data.token:
            parsed = urlparse(repo_url)
            safe_token = quote(data.token)
            auth_url = f"{parsed.scheme}://{safe_token}@{parsed.netloc}{parsed.path}"
            
            res = subprocess.run(["git", "ls-remote", auth_url], capture_output=True, env=env, timeout=10)
            if res.returncode == 0:
                return {"accessible": True, "private": True}
            else:
                return {"accessible": False, "private": True, "reason": "bad_token"}
        else:
            res = subprocess.run(["git", "ls-remote", repo_url], capture_output=True, env=env, timeout=10)
            if res.returncode == 0:
                return {"accessible": True, "private": False}
            else:
                return {"accessible": False, "private": True}
    except Exception as e:
        return {"accessible": False, "reason": str(e)}


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
    elif "test" in f or "spec" in f:
        return "test"
    else:
        return "general"


def simple_summary(file):
    """Fallback summary when AI is unavailable."""
    if file.endswith(".js"):
        return "JavaScript logic file"
    elif file.endswith(".ts"):
        return "TypeScript module"
    elif file.endswith(".html"):
        return "UI structure file"
    elif file.endswith(".css"):
        return "Stylesheet"
    elif file.endswith(".py"):
        return "Python backend module"
    elif file.endswith(".json"):
        return "Configuration or data file"
    else:
        return "Project file"


def ai_summary(file_path: str, content: str) -> str:
    """
    Call Claude API for a one-sentence file summary.
    Requires ANTHROPIC_API_KEY env variable.
    Falls back to simple_summary() on any error.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return simple_summary(file_path)

    try:
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic(api_key=api_key)
        snippet = content[:800]
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=80,
            messages=[{
                "role": "user",
                "content": (
                    f"File: {file_path}\n\n"
                    f"Content snippet:\n{snippet}\n\n"
                    "Write ONE concise sentence (max 20 words) describing what this file does. "
                    "No preamble, just the sentence."
                )
            }]
        )
        return message.content[0].text.strip()
    except Exception:
        return simple_summary(file_path)


def resolve_relative(source, target):
    return normalize_path(
        os.path.normpath(os.path.join(os.path.dirname(source), target))
    )


# =========================
# 🔹 MAIN ANALYZE ENDPOINT
# =========================

@app.post("/analyze-repo")
def analyze(data: RepoRequest):
    repo_url = data.repo_url
    repo_path = "repo"

    try:
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path, onerror=remove_readonly)

        if data.token:
            parsed = urlparse(repo_url)
            safe_token = quote(data.token)
            auth_url = f"{parsed.scheme}://{safe_token}@{parsed.netloc}{parsed.path}"
            try:
                git.Repo.clone_from(auth_url, repo_path)
            except Exception as e:
                error_msg = str(e).replace(data.token, "HIDDEN_TOKEN")
                raise Exception(error_msg)
        else:
            git.Repo.clone_from(repo_url, repo_path)

        edges = []
        file_scores = {}   # path → import count
        raw_files = []     # (relative_path, filename, content)
        libraries = []

        # Parse package.json
        pkg_path = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    for name, ver in deps.items():
                        libraries.append({"name": name, "version": str(ver).replace("^", "").replace("~", ""), "type": "npm"})
            except Exception:
                pass

        # Parse requirements.txt
        req_path = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(req_path):
            try:
                with open(req_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = re.split(r'[=><~]+', line, maxsplit=1)
                            name = parts[0].strip()
                            ver = parts[1].strip() if len(parts) > 1 else "latest"
                            if name:
                                libraries.append({"name": name, "version": ver, "type": "pip"})
            except Exception:
                pass

        skip_dirs = {".git", "node_modules", "__pycache__", "dist", "build", ".venv"}

        # ── Pass 1: walk files, build edges + scores ──────────────────
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for file in files:
                full_path = os.path.join(root, file)

                if os.path.getsize(full_path) > 200000:
                    continue

                relative_path = normalize_path(
                    os.path.relpath(full_path, repo_path)
                )

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    content = ""

                raw_files.append((relative_path, file, content))

                # JS / TS imports
                if file.endswith((".js", ".ts")):
                    imports = re.findall(r'import .* from [\'"](.*?)[\'"]', content)
                    requires = re.findall(r'require\([\'"](.*?)[\'"]\)', content)
                    for imp in imports + requires:
                        if imp.startswith("."):
                            target = resolve_relative(relative_path, imp)
                            edges.append({"source": relative_path, "target": target})
                            file_scores[target] = file_scores.get(target, 0) + 1

                # HTML script/link tags
                if file.endswith(".html"):
                    scripts = re.findall(r'<script.*src=["\'](.*?)["\']', content)
                    links = re.findall(r'<link.*href=["\'](.*?)["\']', content)
                    for src in scripts + links:
                        if not src.startswith("http"):
                            target = resolve_relative(relative_path, src)
                            edges.append({"source": relative_path, "target": target})
                            file_scores[target] = file_scores.get(target, 0) + 1

                # Python imports
                if file.endswith(".py"):
                    imports = re.findall(r'import (\w+)', content)
                    for imp in imports:
                        target = imp + ".py"
                        edges.append({"source": relative_path, "target": target})

        # ── Pass 2: build nodes (impact score now complete) ───────────
        # Only call AI for the top 10 highest-impact files to keep latency low
        top_files = set(
            sorted(file_scores, key=file_scores.get, reverse=True)[:10]
        )

        nodes = []
        for relative_path, file, content in raw_files:
            impact = file_scores.get(relative_path, 0)

            summary = (
                ai_summary(relative_path, content)
                if relative_path in top_files
                else simple_summary(file)
            )

            nodes.append({
                "id": relative_path,
                "type": get_file_type(file),
                "role": classify_role(relative_path),
                "summary": summary,
                "impact": impact,          # ✅ FIX: was missing before
                "preview": content[:200],
                "folder": relative_path.split("/")[0] if "/" in relative_path else "root"
            })

        # ── Clean edges: only keep edges where both ends exist ─────────
        valid_nodes = set(n["id"] for n in nodes)
        edges = [
            e for e in edges
            if normalize_path(e["target"]) in valid_nodes
        ]

        # ── Top important files ────────────────────────────────────────
        important_files = sorted(
            file_scores, key=file_scores.get, reverse=True
        )[:5]

        # ── Entry points ───────────────────────────────────────────────
        entry_points = [
            n["id"] for n in nodes
            if "index" in n["id"].lower() or "main" in n["id"].lower()
        ]

        # ── Onboarding path: entries first, then top imports ──────────
        seen = set(entry_points)
        onboarding_path = entry_points + [
            f for f in important_files if f not in seen
        ][:3]

        # ── Limit size ─────────────────────────────────────────────────
        nodes = nodes[:200]
        edges = edges[:300]

        return {
            "nodes": nodes,
            "edges": edges,
            "important_files": important_files,
            "entry_points": entry_points,
            "onboarding_path": onboarding_path,
            "total_files": len(nodes),
            "libraries": libraries,
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
        except Exception:
            pass


# =========================
# 🔹 QUERY ENDPOINT
# =========================

class QueryRequest(BaseModel):
    query: str
    nodes: list


@app.post("/query-repo")
def query_repo(data: QueryRequest):
    query_lower = data.query.lower()

    # ✅ FIX: frontend sends {path, summary, category} — use those keys
    matched = [
        n for n in data.nodes
        if query_lower in n.get("path", "").lower()
        or query_lower in n.get("summary", "").lower()
        or query_lower in n.get("category", "").lower()
    ]

    # Sort by impact if available, otherwise keep order
    matched.sort(key=lambda n: n.get("impact", 0), reverse=True)

    relevant_paths = [n["path"] for n in matched[:5]]

    return {
        "explanation": (
            f"Found {len(matched)} file(s) matching '{data.query}'. "
            + (f"Top match: {relevant_paths[0]}" if relevant_paths else "No files matched.")
        ),
        "relevant_paths": relevant_paths,
        "results": matched[:5]
    }

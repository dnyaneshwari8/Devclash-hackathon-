# 🚀 Codebase Visualization & Analysis Tool

## 📌 Overview

This project is a **Developer Onboarding & Codebase Intelligence Tool** built using **FastAPI (Backend)** and a frontend (HTML, CSS, JS).

It helps developers:

* Understand large codebases quickly
* Visualize file dependencies
* Identify important files
* Get AI-powered file summaries
* Query the codebase using natural language

---

## 🧠 Key Features

### 🔹 1. Repository Access Check

* Endpoint: `/check-repo`
* Verifies if a Git repository is:

  * Public ✅
  * Private 🔒 (requires token)
* Uses `git ls-remote` internally

---

### 🔹 2. Codebase Analysis Engine

* Endpoint: `/analyze-repo`
* Core feature of the project

#### ⚙️ What it does:

* Clones the repository
* Parses files (JS, TS, Python, HTML, etc.)
* Extracts:

  * File dependencies (imports, requires)
  * File roles (API, utility, model, etc.)
  * File types (frontend/backend/config)

---

### 🔗 3. Dependency Graph

* Builds relationships:

  * `"File A → imports → File B"`
* Outputs:

  * `nodes` (files)
  * `edges` (dependencies)

---

### 📊 4. File Impact Analysis

* Calculates **impact score** based on:

  * How many files import a file

➡️ Helps identify:

* Critical files
* High-risk files

---

### 🧩 5. Smart File Classification

Each file is labeled with:

#### 📁 Type:

* `backend` → Python
* `frontend` → JS/TS/HTML/CSS
* `config` → JSON
* `other`

#### 🏷️ Role:

* `api`
* `utility`
* `data`
* `entry`
* `test`
* `general`

---

### 🤖 6. AI-Powered Summaries

* Uses **Claude API (Anthropic)**
* Generates **1-line summaries** for top important files

Fallback:

* Uses rule-based summary if API is unavailable

---

### 📦 7. Dependency Extraction

Automatically detects libraries from:

* `package.json` → npm packages
* `requirements.txt` → Python packages

---

### 🚀 8. Entry Point Detection

Detects:

* `index.js`
* `main.py`
* Similar files

---

### 🧭 9. Onboarding Path Generator

Provides a **learning path** for new developers:

1. Entry files
2. Important files
3. High-impact modules

---

### 🔍 10. Natural Language Query System

* Endpoint: `/query-repo`

#### Example Queries:

* "authentication"
* "api routes"
* "database logic"

#### Output:

* Matching files
* Explanation
* Relevant file paths

---

## 🛠️ Tech Stack

### Backend:

* FastAPI
* GitPython
* Python Standard Libraries
* Anthropic API (optional)

### Frontend:

* HTML
* CSS
* JavaScript
* (Likely uses graph visualization like React Flow or similar)

---

## 📂 API Endpoints

### 1. Home

```
GET /
```

Response:

```
{ "message": "Backend running 🚀" }
```

---

### 2. Check Repository

```
POST /check-repo
```

#### Request:

```
{
  "repo_url": "https://github.com/user/repo",
  "token": "optional"
}
```

#### Response:

```
{
  "accessible": true,
  "private": false
}
```

---

### 3. Analyze Repository

```
POST /analyze-repo
```

#### Response:

```
{
  "nodes": [...],
  "edges": [...],
  "important_files": [...],
  "entry_points": [...],
  "onboarding_path": [...],
  "libraries": [...]
}
```

---

### 4. Query Repository

```
POST /query-repo
```

#### Request:

```
{
  "query": "api",
  "nodes": [...]
}
```

#### Response:

```
{
  "explanation": "...",
  "relevant_paths": [...],
  "results": [...]
}
```

---

## ⚙️ Installation & Setup

### 1. Clone Project

```
git clone <your-repo>
cd project-folder
```

---

### 2. Install Dependencies

```
pip install fastapi uvicorn gitpython anthropic
```

---

### 3. Run Server

```
uvicorn main:app --reload
```

---

### 4. Open in Browser

```
http://127.0.0.1:8000
```

---

## 🔐 Environment Variables (Optional)

For AI summaries:

```
ANTHROPIC_API_KEY=your_api_key
```

---

## 📌 Project Workflow

1. User enters GitHub repo URL
2. Backend:

   * Validates repo
   * Clones repo
   * Parses files
   * Builds graph
3. Frontend:

   * Displays dependency graph
   * Shows file insights
4. User queries system for insights

---

## ⚠️ Limitations

* Large repos are truncated (200 nodes / 300 edges)
* Only basic regex-based parsing
* Python import resolution is simplified
* AI summaries limited to top 10 files

---

## 🚀 Future Improvements

* Full AST parsing (better accuracy)
* Real-time graph updates
* Code change impact prediction
* AI chat over repo
* Support for more languages
* Better UI (drag, zoom, clustering)

---

## 👩‍💻 Use Cases

* Developer onboarding
* Hackathons
* Codebase understanding
* Technical interviews
* Software architecture analysis

---

## 🎯 Conclusion

This project solves a **real-world developer pain point**:

> Understanding large codebases quickly without manual effort.

It combines:

* Static analysis ⚙️
* AI summarization 🤖
* Visualization 📊

Making it a **powerful developer productivity tool**.

---


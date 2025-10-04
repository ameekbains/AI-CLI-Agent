# 🧠 AI CLI Agent

The **AI CLI Agent** lets you run Git and Bash commands from natural language prompts.  
It supports **local models** (Ollama, LM Studio) or a **built-in dataset** of 500+ Git/Bash examples.

---

## ✨ Features

- 🚀 **Natural language → safe shell commands**
- 📚 **500+ built-in heuristic examples** (Git + Bash)
- 🤖 **Local model support**: [Ollama](https://ollama.ai), [LM Studio](https://lmstudio.ai)
- 🔒 **Command validation** (rejects unsafe/dangerous commands)
- 📝 **Interactive editing** before execution
- 📜 **History & replay** of previous sessions
- 🛡 **Safe mode** requiring explicit confirmation
- 🌐 **MCP/HTTP server** for integration with editors & tools

---

## 📦 Installation

### 1. Extract or Clone
```bash
unzip aicli_code.zip
cd aicli_code

2. Install with the Helper Script
bash install.sh
This will:
Create a .venv/ virtual environment
Upgrade pip
Install the package with dependencies
Manual installation alternative:
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .

Example Usage
Run a command:
ai run "List files in current directory"
Or for development:
python -m aicli.cli run "List files in current directory"
Example output:
Prompt: List files in current directory
Generated command: ls -la
Run this command? [y/N]: y

By default, the agent runs in mock mode, using the built-in dataset.
To switch to a model:
ai configure
You’ll be prompted to select:
Provider:
mock → heuristic dataset (offline, default)
ollama → local Ollama server
lmstudio → LM Studio local server
Model name (depends on provider):
Ollama: llama2, mistral, codellama, etc.
LM Studio: whichever model you’ve downloaded
Check available models:
ai list-models
Example: Ollama
# Download model
ollama pull llama2

# Configure AI CLI
ai configure   # provider=ollama, model=llama2

# Run a command
ai run "Show git branches"
Example: LM Studio
# In LM Studio:
# 1. Download a model
# 2. Enable the "Local API Server" toggle in settings

# Configure AI CLI
ai configure   # provider=lmstudio, model=your_model_name

# Run a command
ai run "Check current git status"
🕑 History & Replay
Show your command history:
ai history
Sample output:
1. ls -la
2. git status
3. git checkout -b feature/login
Replay a command by index:
ai !3
(re-runs the 3rd command in your history)
🧩 Safe Mode
Enable safe mode for extra protection:
ai configure
When safe mode is active, you must confirm explicitly with --yes:
ai run "Delete temp files" --yes
🌐 Running as a Server
Start the agent as an MCP/HTTP server:
ai serve
Exposes a /generate endpoint:
Accepts JSON payloads like:
{ "prompt": "List all git branches" }
Returns validated commands in JSON
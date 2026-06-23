```markdown
# 📖 Open-Source Deployment Playbook: Build Your Own Agentic Auditor

Welcome to the public installation blueprint! This step-by-step workbook is designed to guide you through setting up, configuring, and launching your own local instance of the Agentic Legal Auditor.

---

## 🛠️ Prerequisites & System Requirements

Before initializing the workspace, ensure your development machine has the following tools installed:
* **Python (Version 3.11 or later)**
* **Node.js (Version 20.x or later)**
* **Docker Desktop** (Optional, for running via containers)
* A code editor like **VS Code**

---

## 🔑 Third-Party Account & Key Management

This system connects to lightweight external APIs to keep your local machine running fast. You will need to collect three free keys to make the platform work:

1. **Groq API Key:** Used to run the ultra-fast Llama-3.3 intelligence model.
   * *How to get it:* Create a free account at [Groq Console](https://console.groq.com/) and click **Create API Key**.
2. **Supabase Database Credentials:** Stores your legal documents safely inside a secure vector cloud database.
   * *How to get it:* Start a free project at [Supabase](https://supabase.com/). Head to Project Settings -> API to copy your `Project URL` and `service_role secret key`.
3. **Unstructured API Key:** Handles extracting raw text from PDFs effortlessly.
   * *How to get it:* Get a free key at [Unstructured.io](https://unstructured.io/).

---

## ⚙️ Local Configuration & Setup Step-by-Step

### 1. Clone and Prepare the Environment Variables
Create a file named `.env` in the root folder of the project and paste the following template, filling in your specific API tokens:

```text
SUPABASE_URL=[https://your-project-id.supabase.co](https://your-project-id.supabase.co)
SUPABASE_SERVICE_KEY=your-long-service-role-key
GROQ_API_KEY=gsk_your-groq-key-here
UNSTRUCTURED_API_KEY=your-unstructured-key-here
BACKEND_PORT=8000
FRONTEND_PORT=4321

2. Boot Up the Python Backend Application

Open a terminal tab in your root directory and run the following terminal strings:

# Create and activate a clean isolated Python sandbox environment
python3 -m venv .venv
source .venv/bin/activate

# Install the required underlying framework modules
pip install -r requirements.txt

# Run the live development server instance
uvicorn app.main:app --reload --port 8000

3. Launch the Web Interface Frontend

Open a second terminal tab, navigate into the frontend folder, and initialize the web application:

cd frontend
npm install
npm run dev

Now, open your web browser and load up http://localhost:4321 to begin using your compliance agent!

---

##  

📘 Glossary of Core Concepts

    RAG (Retrieval-Augmented Generation): A method that feeds an AI specific reference text (like an uploaded contract) so it answers accurately based on facts instead of guessing.

    Vector Database: A specialized database that translates text into long lists of math coordinates (embeddings), allowing the system to instantly search documents based on the meaning of words rather than exact keywords.

    Agentic Routing: The cognitive process where an AI reviews a user's question and decides on its own which tool to activate (e.g., searching an internal PDF vs. scanning the public internet).

    Token-Bucket Rate Limiter: A security shield that hands out virtual "execution coins" to users. Every message costs a coin. If a user runs out of coins, they must wait for the bucket to refill, protecting the system from overload.
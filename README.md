# RethinkAI - Community Sentiment Analysis Platform

A comprehensive AI-powered platform for analyzing and understanding community sentiment around public safety in the Dorchester community of Boston. This project combines traditional data science approaches with LLM-based chat interactions to explore and make sense of community data.

## 🎯 Project Goals

This platform enables:
- **Interactive Data Exploration**: Query 311 requests, crime reports, and community events through natural language
- **Community Engagement**: Access community newsletters, meeting transcripts, and policy documents via semantic search
- **Intelligent Question Routing**: Automatically routes questions to SQL queries (structured data) or RAG retrieval (documents) or both (hybrid mode)
- **Event Discovery**: Find upcoming community events with temporal queries

## 📁 Project Structure

```
ml-misi-community-sentiment/
├── api/                          # Flask REST API (session auth + legacy API keys)
│   ├── api_v2.py                 # Main API endpoint (agent-powered)
│   ├── api.py                    # Legacy API (deprecated)
│   ├── datastore/                # Static data files
│   ├── prompts/                  # LLM prompt templates
│   └── requirements.txt          # API dependencies
│
├── on_the_porch/                 # Core chatbot and data processing
│   ├── unified_chatbot.py        # Main chatbot orchestration
│   ├── sql_chat/                 # SQL query generation and execution
│   ├── rag stuff/                # RAG retrieval system
│   ├── data_ingestion/           # Automated data sync (Google Drive, Email)
│   ├── calendar/                 # Event extraction and processing
│   └── new_metadata/             # Database schema metadata generation
│
├── dataset-documentation/        # Dataset documentation (see below)
├── test_frontend/                # Frontend testing interface
├── public/                      # Static frontend assets
└── Old_exp/                     # Legacy experiments (ignored in git)
```

## 🚀 Quick Start

### Demo-Friendly Setup (Dockerized MySQL, recommended for quick evals)

For instructors and evaluators, a lightweight demo setup is available in the `demo/` folder. This avoids any client credentials and uses a small demo database snapshot and vector store **without running the data ingestion pipeline**, since ingestion requires additional setup of Google Drive and Gmail credentials.

To keep setup instructions in one place (and avoid the main README getting out of sync with the actual scripts), **all demo-specific setup steps are documented in** `demo/README.md`.  

From the project root, see:

- `demo/README.md` – how to:
  - Run `demo/setup.sh` or `demo/setup_windows.bat`
  - Bring up the Dockerized MySQL demo database
  - Configure the minimal `.env` values needed for the demo

Once you’ve followed the steps in `demo/README.md`, you can **skip the Installation section below** and just use the Configuration and Running API/frontend sections as reference.

### Prerequisites

- Python 3.11+
- MySQL 8.0+ (for structured data) or Docker (for the demo DB)
- Google Gemini API key

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ml-misi-community-sentiment
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Mac/Linux
   venv\Scripts\activate     # On Windows
   ```

3. **Install dependencies**
   ```bash
   # Install all dependencies from root requirements.txt
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   - This project uses a **single `.env` file at the repo root**
   - Copy `example_env.txt` to `.env` (then edit values):
   ```bash
   cp example_env.txt .env
   ```

5. **Set up database**
   - Create a MySQL database (default: `rethink_ai_boston`)
   - Or use the demo DB described in `demo/README.md`
   - For ingestion + live data sync, see `on_the_porch/data_ingestion/README.md`

6. **Run the API**
   ```bash
   python api/api_v2.py
   ```
   The API will start on `http://127.0.0.1:8888`

7. **Run the Frontend** (in a separate terminal)
   ```bash
   cd public
   python -m http.server 8000
   ```
   Then open `http://localhost:8000` in your browser

  **Note**: Make sure the backend API is running before starting the frontend. The frontend connects to the API at `http://127.0.0.1:8888` by default.

## ⚙️ Configuration

### Environment Variables

The project uses a **single `.env` file at the repo root**.

- Copy `example_env.txt` to `.env`:
  ```bash
  cp example_env.txt .env
  ```
- Edit `.env` and fill in the values for your environment.

**Key Variables (non-exhaustive):**
- `GEMINI_API_KEY` – Google Gemini API key (required)
- `RETHINKAI_API_KEYS` – legacy API keys (used only by `POST /chat` and `GET /events`)
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` – MySQL connection
- `VECTORDB_DIR` – path to the ChromaDB/vector DB directory
- `GOOGLE_DRIVE_FOLDER_ID` and related `GOOGLE_*/GMAIL_*` settings – data ingestion

## 📊 Data Sources

### Structured Data (MySQL)
- **311 Requests**: Service requests from Boston 311 system
- **911 Reports**: Crime and emergency reports
- **Community Events**: Calendar events extracted from newsletters

### Unstructured Data (Vector Database)

- **Meeting Transcripts**: Community meeting notes and discussions
- **Policy Documents**: City planning documents, budgets, and initiatives

### Data Ingestion
The system automatically syncs data from:
- **Google Drive**: Client-uploaded documents (PDF, DOCX, TXT, MD)
- **Email Newsletters**: Automated extraction of events to calendar

See `on_the_porch/data_ingestion/README.md` for details.

## 🔌 API Endpoints

### Primary (session-based) endpoints (`api/api_v2.py`)

- `GET /auth/me`
- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /conversations`
- `POST /conversations`
- `GET /conversations/:id/messages`
- `POST /conversations/:id/messages`

The `public/` frontend uses these session-based endpoints (cookies + CSRF).

### Legacy compatibility (API-key) endpoints (`api/api_v2.py`)

- **POST /chat** - Main chat interaction with intelligent routing
- **POST /log** - Log interactions
- **PUT /log** - Update interaction feedback
- **GET /events** - Fetch upcoming community events
- **GET /health** - Health check

See `api/README.md` for detailed API documentation.

## 🗂️ Dataset Documentation

Comprehensive dataset documentation is available in the `dataset-documentation/` folder. This includes:
- Data source descriptions
- Schema documentation
- Data quality notes
- Usage examples

See `dataset-documentation/README.md` for details.

## 🎓 For Next Student Team

### What We've Built

This project implements a **hybrid AI system** that combines:
1. **SQL-based queries** for structured data (311, 911, events)
2. **RAG (Retrieval-Augmented Generation)** for document-based answers
3. **Intelligent routing** that selects the best approach for each question

### Key Components

1. **Unified Chatbot** (`on_the_porch/unified_chatbot.py`)
   - Routes questions to SQL, RAG, or hybrid mode
   - Manages conversation history and context
   - Handles source citations

2. **Data Ingestion Pipeline** (`on_the_porch/data_ingestion/`)
   - Automated sync from Google Drive and email
   - Event extraction from newsletters
   - Vector database updates

3. **API Layer** (`api/api_v2.py`)
   - RESTful endpoints for frontend integration
   - Session management
   - Interaction logging

### Recommended Next Steps

1. **Start Here**: Review `on_the_porch/unified_chatbot.py` to understand the core routing logic
2. **Test the API**: Use `api/test_api_v2.py` to test endpoints
3. **Explore Data**: Check `dataset-documentation/` for available data sources
4. **Frontend Integration**: 
   - See `public/` for the production frontend (see `public/README.md` for details)
   - See `test_frontend/` for example frontend code
   - Both can be used to test the API via a web interface

### Development Workflow

1. **Local Development (session-based UI)**
   ```bash
   python api/api_v2.py
   cd public && python -m http.server 8000
   ```

2. **Legacy API-key testing**
   - See `test_frontend/` (API-key based) or call `POST /chat` with header `RethinkAI-API-Key`

3. **Data Updates**
   ```bash
   # Run data ingestion
   cd on_the_porch/data_ingestion
   python boston_data_sync/boston_data_sync.py
   ```

3. **Database Setup**
   - See `on_the_porch/data_ingestion/README.md` for database initialization

### Common Issues & Solutions

- **API Key Errors**: Ensure `GEMINI_API_KEY` is set in `.env`
- **Database Connection**: Verify MySQL credentials and database exists
- **Vector DB Issues**: Check `VECTORDB_DIR` path and permissions
- **Import Errors**: Ensure virtual environment is activated and dependencies installed

### Documentation References

- API Documentation: `api/README.md`
- Data Ingestion: `on_the_porch/data_ingestion/README.md`
- Dataset Info: `dataset-documentation/README.md`
- API v2 Details: `on_the_porch/api_readme.md`

## 🌐 Deployment

### DreamHost Setup (needs to be tested)

See `scripts/dreamhost/` for deployment scripts:
- `setup.sh` - Initial server setup
- `deploy.sh` - Application deployment
- `database_setup.sh` - Database initialization

### Production Considerations

- Use `gunicorn` or similar WSGI server for production
- Set `FLASK_SESSION_COOKIE_SECURE=True` for HTTPS
- Configure proper CORS origins
- Set up database backups
- Monitor API usage and costs

## 📝 License

See `LICENSE.md` for license information.

## 👥 Contact

- **Project Owner**: buspark@bu.edu
- **Repository**: [GitHub Link]

## 🔗 Links

- **Interactive Dashboard**: [Add dashboard URL if hosted]
- **API Documentation**: See `api/README.md`
- **Dataset Documentation**: See `dataset-documentation/README.md`

---

**Note**: The `Old_exp/` folder contains legacy experiments and is excluded from version control. Focus on the `api/` and `on_the_porch/` directories for active development.

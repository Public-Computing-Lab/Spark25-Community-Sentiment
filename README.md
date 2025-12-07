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
├── api/                          # Flask REST API (v2.0)
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

### Prerequisites

- Python 3.11+
- MySQL 8.0+ (for structured data)
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
   - Copy `.env.example` files to `.env` in each directory
   - See [Configuration](#configuration) section below

5. **Set up database**
   - Create MySQL database: `rethink_ai_boston`
   - Run database setup scripts (see `on_the_porch/data_ingestion/`)

6. **Run the API**
   ```bash
   cd api
   python api_v2.py
   ```
   The API will start on `http://127.0.0.1:8888`

7. **Run the Frontend** (in a separate terminal)
   ```bash
   # From project root
   cd public
   python -m http.server 8000
   ```
   Then open `http://localhost:8000` in your browser

   **Note**: Make sure the backend API is running before starting the frontend. The frontend connects to the API at `http://127.0.0.1:8888` by default.

## 🧪 Demo-Friendly Setup (Dockerized MySQL)

For instructors and evaluators, a lightweight demo setup is available in the `demo/` folder. This avoids any client credentials and uses a small demo database snapshot and vector store.

**Additional prerequisite**:
- Docker Desktop (or Docker + Docker Compose)

**Demo flow (from project root)**:
1. Run one-time setup:
   ```bash
   bash demo/setup.sh
   ```
   This will:
   - Create a virtualenv `.venv/`
   - Install Python dependencies
   - Unzip the demo ChromaDB/vector store
   - Start a MySQL demo database via Docker and import `demo/mysql_demo_dump.sql`
2. Copy the appropriate `.env.example` to `.env` (root or `on_the_porch/`) and fill in at least `GEMINI_API_KEY`. Demo database defaults are already set for the Dockerized MySQL instance.
3. Start the backend and frontend as described in the **Quick Start** section above.

See `demo/README.md` for concise demo-specific instructions.

## ⚙️ Configuration

### Environment Variables

The project uses environment variables for configuration. See `.env.example` files in:
- `api/.env.example` - API configuration
- `on_the_porch/.env.example` - Core chatbot configuration
- `on_the_porch/data_ingestion/.env.example` - Data ingestion configuration

**Key Variables:**
- `GEMINI_API_KEY` - Google Gemini API key (required)
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` - Database connection
- `RETHINKAI_API_KEYS` - API authentication keys (comma-separated)
- `GOOGLE_DRIVE_FOLDER_ID` - Google Drive folder for document sync
- `DATABASE_URL` - PostgreSQL connection string (if using vector DB)

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

### Agent API v2.0 (`api/api_v2.py`)

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

1. **Local Development**
   ```bash
   # Start API server
   cd api
   python api_v2.py
   
   # Test with curl or Postman
   curl -X POST http://localhost:8888/chat \
     -H "RethinkAI-API-Key: your-key" \
     -H "Content-Type: application/json" \
     -d '{"message": "What events are happening this weekend?"}'
   ```

2. **Data Updates**
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

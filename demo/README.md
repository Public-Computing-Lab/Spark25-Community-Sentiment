## Demo Setup

This `demo/` folder contains a minimal, self-contained setup so an evaluator can bring up the project quickly without access to client credentials or infrastructure.

There are some troubleshooting steps at the end of this file incase you face the same issues we faced.

### Prerequisites

- **Python 3.11+**
- **Docker Desktop** (or Docker + Docker Compose)

### One-time data artifacts (already in repo)

- `demo/mysql_demo_dump.sql` – MySQL dump of a demo database
- `demo/docker-compose.demo.yml` – spins up MySQL with the demo data
- `demo/vectordb_new.zip` – compressed ChromaDB/vector store (you create this locally before committing)

### 1. Run the demo setup

From the project root:

- On Mac/Linux (or Windows with WSL / Git Bash):

  ```bash
  bash demo/setup.sh
  ```

- On Windows **without** WSL (Command Prompt / PowerShell):

  ```bat
  demo\setup_windows.bat
  ```

This will:
- Create a `.venv_demo` virtual environment just for the demo
- Install Python dependencies from the root `requirements.txt`
- Unzip `demo/vectordb_new.zip` so the vector DB is available
- Start a MySQL demo database using Docker (`mysql:8` image) and import `mysql_demo_dump.sql`

### 2. Environment variables

1. From the project root, copy the example env file to `.env`:
   ```bash
   cp example_env.txt .env
   ```
2. Open `.env` and fill in at least:
   - `GEMINI_API_KEY` (leave blank if you want to run without Gemini-based features)
   - Leave the demo DB values as-is if you are using the Docker demo:
     - `MYSQL_HOST=localhost`
     - `MYSQL_PORT=3306`
     - `MYSQL_USER=demo_user`
     - `MYSQL_PASSWORD=demo_pass`
     - `MYSQL_DB=sentiment_demo`

### 3. Run backend and frontend

You'll need two terminals for this, activate the venv in both.

On Mac/Linux (or WSL), from the project root:

```bash
source .venv_demo/bin/activate
```

On Windows (Command Prompt or PowerShell), from the project root:

```bat
.\.venv_demo\Scripts\activate
```

From the project root, in **one terminal**:

```bash
cd api
python api_v2.py
```

The API will start on `http://127.0.0.1:8888`.

In **another terminal**:

```bash
cd public
python -m http.server 8000
```

Then open `http://localhost:8000` in your browser. Make sure the backend is running first.

### Notes

- The demo database and vector store are for evaluation only and are not up to date.
- For full production setup and data ingestion, see the main `README.md` and `on_the_porch/data_ingestion/README.md`.
 
### Troubleshooting

#### Python Version Issues (macOS)

**Error:** `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`

**Cause:** The code requires Python 3.10+ (preferably 3.11+), but your system is using Python 3.9.

**Solution:**
1. Install Python 3.11:
   ```bash
   brew install python@3.11
   ```

2. Verify installation:
   ```bash
   python3.11 --version
   ```

3. Recreate the virtual environment:
   ```bash
   rm -rf .venv_demo
   bash demo/setup.sh
   ```

The setup script will automatically detect and use Python 3.11.

#### Port 8888 Already in Use (macOS/Linux)

**Error:** Backend fails to start because port 8888 is already in use.

**Solution (macOS/Linux):**
1. Find processes using port 8888:
   ```bash
   lsof -ti:8888
   ```

2. Kill the processes (replace with actual PIDs from step 1):
   ```bash
   kill -9 58944 93652
   ```

3. Verify port is free:
   ```bash
   lsof -ti:8888
   ```
   (Should return nothing)

**Solution (Windows):**
1. Find processes using port 8888:
   ```powershell
   netstat -ano | findstr :8888
   ```

2. Kill the process (replace PID with actual process ID from step 1):
   ```powershell
   taskkill /PID 12345 /F
   ```

3. Start the backend normally - it will use port 8888 by default.

**Why not change the port?** The frontend is configured to connect to `http://127.0.0.1:8888`. While you can change the backend port with `export API_PORT=8889` (macOS/Linux) or `set API_PORT=8889` (Windows), it's simpler to free up port 8888.

#### MySQL Build Errors During Installation

**Error:** `mysqlclient` build errors during `pip install -r requirements.txt`

##### Linux (Ubuntu/Debian)

Install build tools and MySQL dev headers:
```bash
sudo apt update
sudo apt install \
    build-essential \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config
```

Then re-run the setup:
```bash
bash demo/setup.sh
```

##### macOS

Install Xcode Command Line Tools and MySQL client:
```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install MySQL client via Homebrew
brew install mysql-client

# Add mysql-client to PATH (add to ~/.zshrc or ~/.bashrc)
export PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"
export LDFLAGS="-L/opt/homebrew/opt/mysql-client/lib"
export CPPFLAGS="-I/opt/homebrew/opt/mysql-client/include"
```

Then re-run the setup:
```bash
bash demo/setup.sh
```

##### Windows

**Option 1: Use pre-built wheels (Recommended)**
```powershell
pip install --only-binary :all: mysqlclient
```

**Option 2: Install Microsoft C++ Build Tools**

If pre-built wheels are not available:
1. Download and install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. During installation, select "Desktop development with C++"
3. Install MySQL Connector/C from [MySQL Downloads](https://dev.mysql.com/downloads/connector/c/)
4. Re-run the setup:
   ```bat
   demo\setup_windows.bat
   ```


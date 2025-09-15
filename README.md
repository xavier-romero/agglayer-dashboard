# AggLayer Python Dashboard

A server-side Python dashboard for monitoring custom AggLayer networks, built with FastAPI and web3.py.

## Features

- 🏠 **Home Page**: Overview of all configured environments
- 🔍 **Environment Details**: View all rollups in an environment
- 📋 **Rollup Details**: Detailed information for each rollup
- 🌐 **API Endpoints**: RESTful API for programmatic access
- ⚡ **Server-side**: No browser RPC limitations or CORS issues
- 🎯 **Custom Networks**: Focus on your custom networks only
- 📦 **Self-contained**: All dependencies included, no external files needed

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Your Network**:
   Edit `config.json` to configure your Kurtosis setup:
   ```json
   {
     "rollupManagerContractAddress": "0x6c6c009cC348976dB4A908c92B24433d4F6edA43",
     "rollupManagerContractDeploymentBlock": 39,
     "rpcURL": "http://localhost:61444",
     "aggLayerURL": "http://localhost:63444",
     "l2rpcs": {
       "1": {
         "rpc": "http://localhost:62444",
         "blockExplorer": "http://localhost:8080"
       }
     }
   }
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```

   Or with uvicorn:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Test Configuration** (recommended):
   ```bash
   ./run.sh --test    # Basic configuration test
   ./run.sh --debug   # Detailed startup debug
   ```

5. **Access the Dashboard**:
   - Web UI: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## API Endpoints

- `GET /` - Home page (HTML)
- `GET /rollups` - All rollups page (HTML)
- `GET /rollup/{rollup_id}` - Rollup details (HTML)
- `GET /api/summary` - Environment summary (JSON)
- `GET /api/rollups` - All rollups (JSON)
- `GET /api/rollup/{rollup_id}` - Rollup details (JSON)

## Architecture

- **FastAPI**: Modern, fast web framework with automatic API docs
- **web3.py**: Ethereum blockchain interactions
- **Jinja2**: HTML templating engine
- **Direct Contract Access**: No browser limitations, direct RPC connections
- **Local ABIs**: Contract ABIs included locally, fully self-contained

## Configuration

The `config.json` file supports:

- **rollupManagerContractAddress**: Your rollup manager contract address
- **rollupManagerContractDeploymentBlock**: Block number where contract was deployed
- **rpcURL**: Your L1 RPC endpoint 
- **aggLayerURL**: Your AggLayer endpoint (optional)
- **l2rpcs**: L2 rollup RPC endpoints and block explorers (by rollup ID)

## Advantages over React Dashboard

✅ **No CORS Issues**: Server-side RPC calls  
✅ **Better Performance**: Direct contract access  
✅ **Custom Focus**: Only your networks, no hardcoded defaults  
✅ **Simple Deployment**: Single Python process  
✅ **API Ready**: Built-in REST API  
✅ **Reliable**: No browser environment variables or build steps  
✅ **Self-contained**: All dependencies and ABIs included locally  

## Docker Support

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Development

The application automatically reloads when files change during development:

```bash
uvicorn app:app --reload
```

# AggLayer Python Dashboard

A server-side Python dashboard for monitoring custom AggLayer networks, built with FastAPI and web3.py.

## Features

- 🏠 **Home Page**: Overview of environment with all rollups listed
- 📋 **Rollup Details**: Detailed information for each rollup including certificate data
- ⚡ **Server-side**: No browser RPC limitations or CORS issues
- 🎯 **Custom Networks**: Focus on your custom networks only
- 📦 **Self-contained**: All dependencies included, no external files needed
- 🔗 **AggLayer Integration**: Displays certificate status and settlement information

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
     "rpcURL": "http://localhost:60444/l1/",
     "aggLayerURL": "http://localhost:60444/agglayer/",
     "l2rpcs": {
       "1": "http://localhost:60444/l2/"
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

## Web Interface

The dashboard provides a clean web interface with:

- **`/`** - Home page showing environment overview and all rollups
- **`/rollup/{rollup_id}`** - Individual rollup details with certificate information and settlement history

All data is rendered server-side for optimal performance and reliability.

## Architecture

- **FastAPI**: Modern, fast web framework for HTML templating
- **web3.py**: Ethereum blockchain interactions
- **Jinja2**: HTML templating engine  
- **Direct Contract Access**: No browser limitations, direct RPC connections
- **Local ABIs**: Contract ABIs included locally, fully self-contained

## Configuration

The `config.json` file supports:

- **rollupManagerContractAddress**: Your rollup manager contract address
- **rpcURL**: Your L1 RPC endpoint 
- **aggLayerURL**: Your AggLayer endpoint (optional)
- **l2rpcs**: L2 rollup RPC endpoints (by rollup ID) - now simplified format with direct URL strings

## Advantages over React Dashboard

✅ **No CORS Issues**: Server-side RPC calls  
✅ **Better Performance**: Direct contract access  
✅ **Custom Focus**: Only your networks, no hardcoded defaults  
✅ **Simple Deployment**: Single Python process  
✅ **Clean UI**: Focused web interface with consolidated rollup overview  
✅ **Reliable**: No browser environment variables or build steps  
✅ **Self-contained**: All dependencies and ABIs included locally  

## Docker Support

Build and run with Docker:

```bash
# Build the image
docker build -t agglayer-dashboard .

# Run the container
docker run -p 8000:8000 agglayer-dashboard
```

Or use the provided build script:
```bash
./build-docker.sh
```

## Development

The application automatically reloads when files change during development:

```bash
uvicorn app:app --reload
```

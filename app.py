from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import Dict, List
from config_loader import config_loader
from contract_utils import ContractInteractor

app = FastAPI(title="AggLayer Dashboard", description="Kurtosis Network Dashboard")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Single contract interactor for the single environment
interactor: ContractInteractor = None

def get_interactor() -> ContractInteractor:
    """Get or create contract interactor"""
    global interactor
    if interactor is None:
        env_config = config_loader.get_environment()
        interactor = ContractInteractor(env_config)
    return interactor

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page showing environment summary and all rollups"""
    try:
        contract_interactor = get_interactor()
        summary = contract_interactor.get_environment_summary()
        rollups = contract_interactor.get_all_rollups()
        
        
        # Add network contract addresses to home page
        network_addresses = contract_interactor.get_network_addresses()
        summary["networkAddresses"] = network_addresses
        
        return templates.TemplateResponse("home.html", {
            "request": request,
            "summary": summary,
            "rollups": rollups
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })

@app.get("/rollup/{rollup_id}", response_class=HTMLResponse)
async def rollup_detail(request: Request, rollup_id: int):
    """Rollup detail page"""
    try:
        contract_interactor = get_interactor()
        rollup_data = contract_interactor.get_rollup_data(rollup_id)
        
        if not rollup_data:
            raise HTTPException(status_code=404, detail=f"Rollup {rollup_id} not found")
        
        rollup_data["rollupID"] = rollup_id
        
        # Get additional details if contract is deployed
        if rollup_data["rollupContract"] != "0x0000000000000000000000000000000000000000":
            rollup_data["networkName"] = contract_interactor.get_network_name(rollup_data["rollupContract"])
            rollup_data["trustedSequencerURL"] = contract_interactor.get_trusted_sequencer_url(rollup_data["rollupContract"])
            
            # Get sequencer info (trusted sequencer address, etc.)
            sequencer_info = contract_interactor.get_sequencer_info(rollup_data["rollupContract"])
            rollup_data.update(sequencer_info)
        
        # Network addresses moved to home page - removed from individual rollup
        
        # Get certificate data if aggLayerURL is available
        env_config = config_loader.get_environment()
        if env_config.aggLayerURL:
            certificate_data = contract_interactor.get_certificate_data(rollup_id, env_config.aggLayerURL)
            rollup_data["certificates"] = certificate_data
            
        # Get the single previous settlement by searching backwards from current settlement
        current_block = None
        settled_cert = rollup_data.get("certificates", {}).get("settled")
        if settled_cert and settled_cert.get("settlement_block_number"):
            current_block = settled_cert.get("settlement_block_number")
        
        if current_block:
            previous_settlement = contract_interactor.get_previous_settlement_event(
                rollup_id, current_block, env_config.aggLayerURL
            )
            rollup_data["recentSettlements"] = previous_settlement
        else:
            rollup_data["recentSettlements"] = []
            
        # Get L2 config if available
        l2_config = config_loader.get_l2_config(str(rollup_id))
        rollup_data["l2Config"] = l2_config
        
        return templates.TemplateResponse("rollup.html", {
            "request": request,
            "rollup": rollup_data
        })
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


if __name__ == "__main__":
    print("🚀 Starting FastAPI application...")
    try:
        # Test configuration before starting server
        print("🧪 Testing configuration...")
        test_interactor = get_interactor()
        is_connected = test_interactor.is_connected()
        if is_connected:
            print("✅ RPC connection test successful")
        else:
            print("⚠️  RPC connection test failed - server will start anyway")
        
        print("🌐 Starting uvicorn server...")
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
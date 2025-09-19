from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import Dict, List
from config_loader import config_loader
from contract_utils import ContractInteractor
from web3 import Web3

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
        
        # Add L2 RPC configuration to home page (backward compatibility format)
        l2rpcs = config_loader.get_l2rpcs_dict()
        summary["l2rpcs"] = l2rpcs
        
        # Add agchainmanager_key availability info for each rollup
        for rollup in rollups:
            l2_config = config_loader.get_l2_config(rollup.get("rollupID"))
            rollup["hasAgchainManagerKey"] = bool(l2_config and l2_config.agchainmanager_key)
        
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

@app.post("/toggle-optimistic-mode/{rollup_id}")
async def toggle_optimistic_mode(rollup_id: int):
    """Toggle optimistic mode for a specific rollup"""
    try:
        # Get rollup configuration
        l2_config = config_loader.get_l2_config(rollup_id)
        if not l2_config or not l2_config.agchainmanager_key:
            raise HTTPException(status_code=400, detail="No agchainmanager_key configured for this rollup")
        
        # Get rollup details
        contract_interactor = get_interactor()
        rollups = contract_interactor.get_all_rollups()
        rollup = next((r for r in rollups if r.get("rollupID") == rollup_id), None)
        
        if not rollup:
            raise HTTPException(status_code=404, detail="Rollup not found")
        
        if rollup.get("rollupVerifierType") != 2 or rollup.get("aggchainType") != "FEP":
            raise HTTPException(status_code=400, detail="Optimistic mode toggle only available for FEP AggLayer Gateway rollups")
        
        # Get current optimistic mode state
        current_optimistic_mode = rollup.get("optimisticMode", False)
        rollup_address = rollup.get("rollupContract")
        
        if not rollup_address or rollup_address == "0x0000000000000000000000000000000000000000":
            raise HTTPException(status_code=400, detail="Invalid rollup contract address")
        
        # Connect to web3
        env_config = config_loader.get_environment()
        w3 = Web3(Web3.HTTPProvider(env_config.rpcURL))
        
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Failed to connect to RPC")
        
        # Set up account from private key
        account = w3.eth.account.from_key(l2_config.agchainmanager_key)
        
        # Determine function to call
        if current_optimistic_mode:
            action = "disable"
        else:
            action = "enable"
        
        # Create contract instance with minimal ABI
        contract_abi = [
            {'inputs': [], 'name': 'enableOptimisticMode', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'},
            {'inputs': [], 'name': 'disableOptimisticMode', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}
        ]
        
        contract = w3.eth.contract(address=rollup_address, abi=contract_abi)
        
        # Build transaction
        if current_optimistic_mode:
            transaction = contract.functions.disableOptimisticMode().build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 100000,  # Reasonable gas limit
                'gasPrice': w3.eth.gas_price,
            })
        else:
            transaction = contract.functions.enableOptimisticMode().build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 100000,  # Reasonable gas limit
                'gasPrice': w3.eth.gas_price,
            })
        
        # Sign and send transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, l2_config.agchainmanager_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        return JSONResponse({
            "success": True,
            "action": action,
            "tx_hash": tx_hash.hex(),
            "new_state": not current_optimistic_mode
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-threshold/{rollup_id}")
async def update_threshold(rollup_id: int, new_threshold: int):
    """Update threshold for a specific rollup"""
    try:
        # Get rollup configuration
        l2_config = config_loader.get_l2_config(rollup_id)
        if not l2_config or not l2_config.agchainmanager_key:
            raise HTTPException(status_code=400, detail="No agchainmanager_key configured for this rollup")
        
        # Get rollup details
        contract_interactor = get_interactor()
        rollups = contract_interactor.get_all_rollups()
        rollup = next((r for r in rollups if r.get("rollupID") == rollup_id), None)
        
        if not rollup:
            raise HTTPException(status_code=404, detail="Rollup not found")
        
        if rollup.get("rollupVerifierType") != 2:
            raise HTTPException(status_code=400, detail="Threshold update only available for AggLayer Gateway rollups")
        
        # Check if using default signers (should be False to allow threshold update)
        if rollup.get("useDefaultSigners", True):
            raise HTTPException(status_code=400, detail="Cannot update threshold when using AgglGW signers")
        
        # Validate new threshold
        if new_threshold < 1:
            raise HTTPException(status_code=400, detail="Threshold must be at least 1")
        
        current_signers_count = rollup.get("rollupSignersCount", 0)
        if new_threshold > current_signers_count and current_signers_count > 0:
            raise HTTPException(status_code=400, detail=f"Threshold ({new_threshold}) cannot exceed signers count ({current_signers_count})")
        
        rollup_address = rollup.get("rollupContract")
        if not rollup_address or rollup_address == "0x0000000000000000000000000000000000000000":
            raise HTTPException(status_code=400, detail="Invalid rollup contract address")
        
        # Connect to web3
        env_config = config_loader.get_environment()
        w3 = Web3(Web3.HTTPProvider(env_config.rpcURL))
        
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Failed to connect to RPC")
        
        # Set up account from private key
        account = w3.eth.account.from_key(l2_config.agchainmanager_key)
        
        # Create contract instance with updateSignersAndThreshold ABI
        contract_abi = [
            {
                'inputs': [
                    {'internalType': 'tuple(address,uint256)[]', 'name': 'newSigners', 'type': 'tuple[]', 'components': [
                        {'internalType': 'address', 'name': 'addr', 'type': 'address'},
                        {'internalType': 'uint256', 'name': 'weight', 'type': 'uint256'}
                    ]},
                    {'internalType': 'tuple(address,string)[]', 'name': 'signersToRemove', 'type': 'tuple[]', 'components': [
                        {'internalType': 'address', 'name': 'addr', 'type': 'address'},
                        {'internalType': 'string', 'name': 'reason', 'type': 'string'}
                    ]},
                    {'internalType': 'uint256', 'name': 'newThreshold', 'type': 'uint256'}
                ],
                'name': 'updateSignersAndThreshold',
                'outputs': [],
                'stateMutability': 'nonpayable',
                'type': 'function'
            }
        ]
        
        contract = w3.eth.contract(address=rollup_address, abi=contract_abi)
        
        # Build transaction with empty arrays and new threshold
        transaction = contract.functions.updateSignersAndThreshold([], [], new_threshold).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 200000,  # Higher gas limit for threshold updates
            'gasPrice': w3.eth.gas_price,
        })
        
        # Sign and send transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, l2_config.agchainmanager_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        return JSONResponse({
            "success": True,
            "action": "update_threshold",
            "tx_hash": tx_hash.hex(),
            "old_threshold": rollup.get("rollupThreshold", 0),
            "new_threshold": new_threshold
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
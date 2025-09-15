import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from web3 import Web3
from web3.providers import HTTPProvider
from config_loader import EnvironmentConfig, L2Config

# Load ABI files
def load_abi(filename: str) -> List[Dict]:
    """Load ABI from the local abi directory"""
    try:
        with open(f"abi/{filename}", 'r') as f:
            abi_data = json.load(f)
            return abi_data if isinstance(abi_data, list) else abi_data.get('abi', [])
    except FileNotFoundError:
        print(f"Warning: ABI file {filename} not found")
        return []

class ContractInteractor:
    def __init__(self, env_config: EnvironmentConfig):
        self.env_config = env_config
        
        try:
            print(f"📡 Connecting to RPC: {env_config.rpcURL}")
            self.w3 = Web3(HTTPProvider(env_config.rpcURL))
            
            # Load ABIs
            self.rollup_manager_abi = load_abi("PolygonRollupManagerV2.json")
            self.rollup_abi = load_abi("PolygonZkEVM.json")
            self.bridge_abi = load_abi("PolygonZkEVMBridgeV2.json")
            
            if not self.rollup_manager_abi:
                raise Exception("Failed to load PolygonRollupManagerV2 ABI")
            
            # Initialize rollup manager contract
            print(f"📋 Initializing rollup manager: {env_config.rollupManagerContractAddress}")
            self.rollup_manager = self.w3.eth.contract(
                address=env_config.rollupManagerContractAddress,
                abi=self.rollup_manager_abi
            )
            
        except Exception as e:
            print(f"❌ Error initializing ContractInteractor: {e}")
            raise
    
    def is_connected(self) -> bool:
        """Check if connection to RPC is working"""
        try:
            print(f"🔍 Testing connection to {self.env_config.rpcURL}")
            block_number = self.w3.eth.get_block_number()
            print(f"✅ Connection successful! Latest block: {block_number}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def get_rollup_count(self) -> int:
        """Get total number of rollups"""
        try:
            return self.rollup_manager.functions.rollupCount().call()
        except Exception as e:
            print(f"Error getting rollup count: {e}")
            return 0
    
    def get_network_addresses(self) -> Dict[str, str]:
        """Get key network contract addresses"""
        try:
            addresses = {}
            
            # Get addresses from rollup manager
            addresses["rollupManagerAddress"] = self.rollup_manager.address
            addresses["bridgeAddress"] = self.rollup_manager.functions.bridgeAddress().call()
            addresses["globalExitRootManager"] = self.rollup_manager.functions.globalExitRootManager().call()
            addresses["polAddress"] = self.rollup_manager.functions.pol().call()
            
            # Try to get AggLayer Gateway (might not exist on all networks)
            try:
                addresses["aggLayerGatewayAddress"] = self.rollup_manager.functions.aggLayerGateway().call()
            except:
                addresses["aggLayerGatewayAddress"] = None
            
            return addresses
        except Exception as e:
            print(f"Error getting network addresses: {e}")
            return {}

    def call_agglayer_rpc(self, url: str, method: str, params: List = None) -> Dict:
        """Make an RPC call to AggLayer endpoint"""
        if params is None:
            params = []
            
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1
            }
            
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code != 200:
                raise Exception(f"HTTP error! status: {response.status_code}")
                
            data = response.json()
            
            if "error" in data:
                raise Exception(f"RPC error: {data['error'].get('message', 'Unknown error')}")
                
            return data.get("result")
            
        except Exception as e:
            print(f"AggLayer RPC call failed ({method}): {e}")
            return None

    def get_certificate_data(self, rollup_id: int, agg_layer_url: str) -> Dict:
        """Get AggLayer certificate data for a rollup"""
        if not agg_layer_url:
            return {"settled": None, "pending": None}
            
        try:
            # Get latest settled certificate using RPC calls (same as React app)
            settled = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getLatestSettledCertificateHeader",
                [rollup_id]
            )
            
            # Get latest pending certificate
            pending = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getLatestPendingCertificateHeader", 
                [rollup_id]
            )
            
            return {
                "settled": settled,
                "pending": pending
            }
        except Exception as e:
            print(f"Error fetching certificate data for rollup {rollup_id}: {e}")
            return {"settled": None, "pending": None}

    def get_sequencer_info(self, rollup_contract_address: str) -> Dict:
        """Get sequencer information from rollup contract"""
        try:
            if rollup_contract_address == "0x0000000000000000000000000000000000000000":
                return {}
                
            # Load rollup contract ABI
            rollup_abi = self.load_abi("PolygonZkEVM.json")
            rollup_contract = self.w3.eth.contract(
                address=rollup_contract_address,
                abi=rollup_abi
            )
            
            # Get sequencer info
            sequencer_info = {}
            try:
                sequencer_info["trustedSequencer"] = rollup_contract.functions.trustedSequencer().call()
                sequencer_info["trustedSequencerURL"] = rollup_contract.functions.trustedSequencerURL().call()
            except Exception as e:
                print(f"Note: Could not get sequencer info: {e}")
            
            return sequencer_info
        except Exception as e:
            print(f"Error getting sequencer info: {e}")
            return {}

    def get_rollup_data(self, rollup_id: int) -> Optional[Dict]:
        """Get rollup data for a specific rollup ID"""
        try:
            rollup_data = self.rollup_manager.functions.rollupIDToRollupDataV2(rollup_id).call()
            
            # Convert to dictionary with named fields
            program_vkey = rollup_data[10]  # Updated index for programVKey
            program_vkey_hex = ""
            if program_vkey and hasattr(program_vkey, 'hex'):
                # It's bytes, convert to hex
                program_vkey_hex = program_vkey.hex() if program_vkey != b'\x00' * 32 else ""
            elif isinstance(program_vkey, int) and program_vkey != 0:
                # It's an integer, convert to hex string
                program_vkey_hex = hex(program_vkey)[2:]  # Remove '0x' prefix
            
            # Get verifier type and add classification
            verifier_type = rollup_data[9]
            if verifier_type == 0:
                rollup_type = "zkEVM"
                verifier_type_friendly = "zkEVM"
            elif verifier_type == 1:
                rollup_type = "PP"
                verifier_type_friendly = "Pessimistic Proof (PP)"
            elif verifier_type == 2:
                rollup_type = "ALGateway"
                verifier_type_friendly = "AggLayer Gateway"
            else:
                rollup_type = "Unknown"
                verifier_type_friendly = f"Unknown ({verifier_type})"
            
            # Get rollup type details for consensus/verifier addresses
            rollup_type_info = self.get_rollup_type_details(rollup_data[8])
            
            return {
                "rollupContract": rollup_data[0],                    # Address
                "chainID": rollup_data[1],                           # Integer
                "consensusImplementation": rollup_type_info.get("rollupTypeConsensus", rollup_data[2]), # Use rollup type consensus (corrected)
                "forkID": rollup_data[3],                           # Integer 
                "lastVerifiedBatch": rollup_data[5],                # Integer
                "rollupTypeID": rollup_data[8],                     # Integer 
                "rollupVerifierType": rollup_data[9],               # Integer (raw)
                "rollupVerifierTypeFriendly": verifier_type_friendly, # Human-readable
                "type": rollup_type,                                # Classification for badges
                "programVKey": program_vkey_hex,                    # From [10], converted to hex
                # Add rollup type info (now with corrected mapping)
                **rollup_type_info
            }
        except Exception as e:
            print(f"Error getting rollup data for ID {rollup_id}: {e}")
            return None
    
    def get_rollup_type_details(self, rollup_type_id: int) -> Dict:
        """Get additional details for a rollup type"""
        try:
            rollup_type_data = self.rollup_manager.functions.rollupTypeMap(rollup_type_id).call()
            
            return {
                "rollupTypeConsensus": rollup_type_data[0],   # Consensus implementation (non-zero address)
                "verifier": rollup_type_data[1],              # Verifier contract address (zero for this rollup)
                "rollupTypeForkID": rollup_type_data[2],      # Fork ID from type
                "rollupTypeVerifierType": rollup_type_data[3], # Verifier type
                "obsolete": rollup_type_data[4],              # Obsolete flag
                "genesis": rollup_type_data[5].hex() if rollup_type_data[5] and rollup_type_data[5] != b'\x00' * 32 else "",  # Genesis block hash
                "rollupTypeProgramVKey": rollup_type_data[6].hex() if rollup_type_data[6] and rollup_type_data[6] != b'\x00' * 32 else "",  # Program VKey from type
            }
        except Exception as e:
            print(f"Note: Could not get rollup type details for ID {rollup_type_id}: {e}")
            return {"genesis": "", "verifier": "0x0000000000000000000000000000000000000000"}
    
    def get_network_name(self, rollup_contract_address: str) -> str:
        """Get network name from rollup contract"""
        try:
            rollup_contract = self.w3.eth.contract(
                address=rollup_contract_address,
                abi=self.rollup_abi
            )
            return rollup_contract.functions.networkName().call()
        except Exception as e:
            print(f"Error getting network name for {rollup_contract_address}: {e}")
            return f"Unknown"
    
    def get_trusted_sequencer_url(self, rollup_contract_address: str) -> str:
        """Get trusted sequencer URL from rollup contract"""
        try:
            rollup_contract = self.w3.eth.contract(
                address=rollup_contract_address,
                abi=self.rollup_abi
            )
            return rollup_contract.functions.trustedSequencerURL().call()
        except Exception as e:
            print(f"Error getting sequencer URL for {rollup_contract_address}: {e}")
            return ""
    
    def get_all_rollups(self) -> List[Dict]:
        """Get all rollup information"""
        rollup_count = self.get_rollup_count()
        rollups = []
        
        for rollup_id in range(1, rollup_count + 1):
            rollup_data = self.get_rollup_data(rollup_id)
            if rollup_data:
                # Add additional info
                rollup_data["rollupID"] = rollup_id
                
                # Get network name if contract is deployed
                if rollup_data["rollupContract"] != "0x0000000000000000000000000000000000000000":
                    rollup_data["networkName"] = self.get_network_name(rollup_data["rollupContract"])
                    rollup_data["trustedSequencerURL"] = self.get_trusted_sequencer_url(rollup_data["rollupContract"])
                    rollup_data["isActive"] = True
                else:
                    rollup_data["networkName"] = f"Rollup {rollup_id}"
                    rollup_data["trustedSequencerURL"] = ""
                    rollup_data["isActive"] = False
                
                # Determine rollup type
                verifier_type = rollup_data.get("rollupVerifierType", None)
                if verifier_type == 0:
                    rollup_data["type"] = "zkEVM"  # Could be Validium too, but simplified for now
                elif verifier_type == 1:
                    rollup_data["type"] = "PP"
                elif verifier_type == 2:
                    rollup_data["type"] = "ALGateway"
                else:
                    rollup_data["type"] = "Unknown"
                
                rollups.append(rollup_data)
        
        return rollups

    def get_environment_summary(self) -> Dict:
        """Get summary information for the environment"""
        try:
            rollup_count = self.get_rollup_count()
            rollups = self.get_all_rollups()
            
            # Count active rollups by type
            active_counts = {"zkEVM": 0, "Validium": 0, "PP": 0, "ALGateway": 0}
            for rollup in rollups:
                if rollup.get("isActive", False):
                    rollup_type = rollup.get("type", "Unknown")
                    if rollup_type in active_counts:
                        active_counts[rollup_type] += 1
            
            return {
                "rollupManagerAddress": self.env_config.rollupManagerContractAddress,
                "rpcURL": self.env_config.rpcURL,
                "aggLayerURL": self.env_config.aggLayerURL,
                "rollupCount": rollup_count,
                "activeCounts": active_counts,
                "isConnected": self.is_connected()
            }
        except Exception as e:
            print(f"Error getting environment summary: {e}")
            return {
                "error": str(e),
                "isConnected": False
            }

import json
import asyncio
import requests
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from web3 import Web3
from web3.providers import HTTPProvider
from config_loader import EnvironmentConfig, L2Config

# Set up file logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/rollup_debug.log')
    ]
)
logger = logging.getLogger(__name__)

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
            
            # Cache for static data that doesn't change
            self._static_cache = {}
            self._cache_timestamp = {}
            
            # Pre-load static data at startup
            self._preload_static_data()
            
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
        """Get key network contract addresses (cached)"""
        # Return cached addresses since they don't change
        return self._static_cache.get('network_addresses', {})

    def get_bridge_details(self, bridge_address: str) -> Dict[str, Any]:
        """Get additional details from Bridge contract for enhanced UI"""
        try:
            # Load bridge ABI and create contract instance
            bridge_abi = load_abi("PolygonZkEVMBridgeV2.json")
            if not bridge_abi:
                return {}  # Return empty dict instead of error to not break page
            
            bridge_contract = self.w3.eth.contract(
                address=bridge_address,
                abi=bridge_abi
            )
            
            details = {}
            
            # Helper function to safely call contract functions
            def safe_call(func_name, default_value=None):
                try:
                    return getattr(bridge_contract.functions, func_name)().call()
                except Exception as e:
                    print(f"Warning: Bridge function {func_name} failed: {e}")
                    return default_value
            
            # Helper function for hex conversion
            def safe_hex_call(func_name):
                try:
                    result = getattr(bridge_contract.functions, func_name)().call()
                    if hasattr(result, 'hex'):
                        return result.hex()
                    else:
                        return hex(result) if isinstance(result, int) else str(result)
                except Exception as e:
                    print(f"Warning: Bridge function {func_name} failed: {e}")
                    return None
            
            # Only call functions that we know work from testing
            details["bridgeVersion"] = safe_call("BRIDGE_VERSION", "Unknown")
            details["isEmergencyState"] = safe_call("isEmergencyState", False)
            details["depositCount"] = safe_call("depositCount", 0)
            details["networkID"] = safe_call("networkID", 0)
            
            # Try other basic functions but don't fail if they don't work
            details["lastUpdatedDepositCount"] = safe_call("lastUpdatedDepositCount", 0)
            details["gasTokenAddress"] = safe_call("gasTokenAddress", "0x0000000000000000000000000000000000000000")
            details["gasTokenNetwork"] = safe_call("gasTokenNetwork", 0)
            details["globalExitRootManager"] = safe_call("globalExitRootManager", None)
            details["polygonRollupManager"] = safe_call("polygonRollupManager", None)
            
            # Optional functions that might not exist
            details["wethToken"] = safe_call("WETHToken", None)
            
            # Hex-based functions
            details["currentRoot"] = safe_hex_call("getRoot")
            
            return details
            
        except Exception as e:
            print(f"Warning: Error getting bridge details: {e}")
            return {}  # Return empty dict to not break the page

    def get_global_exit_root_details(self, ger_address: str) -> Dict[str, Any]:
        """Get additional details from Global Exit Root Manager for enhanced UI"""
        try:
            # Create a minimal ABI for the Global Exit Root Manager functions
            ger_abi = [
                {'inputs': [], 'name': 'version', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'pure', 'type': 'function'},
                {'inputs': [], 'name': 'getLastGlobalExitRoot', 'outputs': [{'internalType': 'bytes32', 'name': '', 'type': 'bytes32'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'getRoot', 'outputs': [{'internalType': 'bytes32', 'name': '', 'type': 'bytes32'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'bridgeAddress', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'rollupManager', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'},
            ]
            
            ger_contract = self.w3.eth.contract(address=ger_address, abi=ger_abi)
            
            details = {}
            
            # Helper function to safely call contract functions
            def safe_call(func_name, default_value=None):
                try:
                    return getattr(ger_contract.functions, func_name)().call()
                except Exception as e:
                    print(f"Warning: GER function {func_name} failed: {e}")
                    return default_value
            
            # Helper function for hex conversion
            def safe_hex_call(func_name):
                try:
                    result = getattr(ger_contract.functions, func_name)().call()
                    if hasattr(result, 'hex'):
                        return result.hex()
                    else:
                        return hex(result) if isinstance(result, int) else str(result)
                except Exception as e:
                    print(f"Warning: GER function {func_name} failed: {e}")
                    return None
            
            # Get basic information
            details["gerVersion"] = safe_call("version", "Unknown")
            details["bridgeAddress"] = safe_call("bridgeAddress", None)
            details["rollupManagerAddress"] = safe_call("rollupManager", None)
            
            # Get root information
            details["lastGlobalExitRoot"] = safe_hex_call("getLastGlobalExitRoot")
            details["l1InfoTreeRoot"] = safe_hex_call("getRoot")
            
            return details
            
        except Exception as e:
            print(f"Warning: Error getting Global Exit Root details: {e}")
            return {}  # Return empty dict to not break the page

    def get_agglayer_gateway_details(self, gateway_address: str) -> Dict[str, Any]:
        """Get additional details from AggLayer Gateway for enhanced UI"""
        try:
            # Create ABI for the AggLayer Gateway functions
            gateway_abi = [
                {'inputs': [], 'name': 'version', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'pure', 'type': 'function'},
                {'inputs': [], 'name': 'getThreshold', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'getAggchainSignersCount', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
                {
                    'inputs': [], 
                    'name': 'getAggchainSignerInfos', 
                    'outputs': [{
                        'internalType': 'tuple(address,string)[]', 
                        'name': '', 
                        'type': 'tuple[]',
                        'components': [
                            {'internalType': 'address', 'name': 'addr', 'type': 'address'},
                            {'internalType': 'string', 'name': 'url', 'type': 'string'}
                        ]
                    }], 
                    'stateMutability': 'view', 
                    'type': 'function'
                },
                {'inputs': [], 'name': 'getAggchainMultisigHash', 'outputs': [{'internalType': 'bytes32', 'name': '', 'type': 'bytes32'}], 'stateMutability': 'view', 'type': 'function'},
            ]
            
            gateway_contract = self.w3.eth.contract(address=gateway_address, abi=gateway_abi)
            
            details = {}
            
            # Helper function to safely call contract functions
            def safe_call(func_name, default_value=None):
                try:
                    return getattr(gateway_contract.functions, func_name)().call()
                except Exception as e:
                    print(f"Warning: AggLayer Gateway function {func_name} failed: {e}")
                    return default_value
            
            # Helper function for hex conversion
            def safe_hex_call(func_name):
                try:
                    result = getattr(gateway_contract.functions, func_name)().call()
                    if hasattr(result, 'hex'):
                        return result.hex()
                    else:
                        return hex(result) if isinstance(result, int) else str(result)
                except Exception as e:
                    print(f"Warning: AggLayer Gateway function {func_name} failed: {e}")
                    return None
            
            # Get basic information
            details["gatewayVersion"] = safe_call("version", "Unknown")
            
            # Get multisig information
            details["threshold"] = safe_call("getThreshold", None)
            details["signersCount"] = safe_call("getAggchainSignersCount", None)
            
            # Get signer infos with URLs
            signer_infos_raw = safe_call("getAggchainSignerInfos", [])
            signer_infos_parsed = []
            
            for signer_info in signer_infos_raw:
                try:
                    signer_infos_parsed.append({
                        "address": signer_info[0],
                        "url": signer_info[1] if signer_info[1] else ""
                    })
                except:
                    continue
            
            details["signers"] = signer_infos_parsed
            details["multisigHash"] = safe_hex_call("getAggchainMultisigHash")
            
            return details
            
        except Exception as e:
            print(f"Warning: Error getting AggLayer Gateway details: {e}")
            return {}  # Return empty dict to not break the page
    
    def _find_agglayer_proxy(self, implementation_addr: str) -> str:
        """Try to find the proxy address for AggLayer Gateway implementation"""
        try:
            # EIP-1967 storage slots
            admin_slot = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'
            
            # Known potential proxy addresses (could be expanded with a search algorithm)
            # For now, we use the address provided by the user as it's managed by the rollup manager
            potential_proxies = [
                '0x414e9E227e4b589aF92200508aF5399576530E4e',  # User-provided proxy
                # Could add more discovery logic here
            ]
            
            rollup_manager_addr = self.rollup_manager.address.lower()
            
            for proxy_addr in potential_proxies:
                try:
                    admin_storage = self.w3.eth.get_storage_at(proxy_addr, admin_slot)
                    admin_from_storage = '0x' + admin_storage.hex()[-40:]
                    
                    # Check if this proxy is managed by our rollup manager
                    if admin_from_storage.lower() == rollup_manager_addr:
                        print(f"Found AggLayer Gateway proxy: {proxy_addr} (managed by RM)")
                        return proxy_addr
                        
                except Exception as e:
                    print(f"Error checking proxy {proxy_addr}: {e}")
                    continue
            
            print(f"No proxy found for AggLayer Gateway implementation {implementation_addr}")
            return None
            
        except Exception as e:
            print(f"Error finding AggLayer proxy: {e}")
            return None
    
    def _preload_static_data(self):
        """Preload static data that doesn't change during app lifetime"""
        try:
            print("🔄 Preloading static contract data...")
            
            # Cache network addresses (including proxy detection)
            self._static_cache['network_addresses'] = self._get_network_addresses_uncached()
            
            # Cache contract versions
            addresses = self._static_cache['network_addresses']
            versions = {}
            
            if addresses.get('aggLayerGatewayAddress'):
                try:
                    gateway_abi = [{'inputs': [], 'name': 'version', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'pure', 'type': 'function'}]
                    gateway_contract = self.w3.eth.contract(address=addresses['aggLayerGatewayAddress'], abi=gateway_abi)
                    versions['gateway'] = gateway_contract.functions.version().call()
                except:
                    versions['gateway'] = "Unknown"
            
            try:
                versions['rollupManager'] = self.rollup_manager.functions.ROLLUP_MANAGER_VERSION().call()
            except:
                try:
                    versions['rollupManager'] = self.rollup_manager.functions.version().call()
                except:
                    versions['rollupManager'] = "Unknown"
            
            self._static_cache['versions'] = versions
            print(f"✅ Static data preloaded: {len(self._static_cache)} items cached")
            
        except Exception as e:
            print(f"Warning: Error preloading static data: {e}")
    
    def _get_network_addresses_uncached(self) -> Dict[str, str]:
        """Get network addresses without caching (used internally)"""
        try:
            addresses = {}
            
            # Get addresses from rollup manager
            addresses["rollupManagerAddress"] = self.rollup_manager.address
            addresses["bridgeAddress"] = self.rollup_manager.functions.bridgeAddress().call()
            addresses["globalExitRootManager"] = self.rollup_manager.functions.globalExitRootManager().call()
            addresses["polAddress"] = self.rollup_manager.functions.pol().call()
            
            # Try to get AggLayer Gateway (might not exist on all networks)
            try:
                # Use the address directly returned by rollup manager (as clarified by user)
                addresses["aggLayerGatewayAddress"] = self.rollup_manager.functions.aggLayerGateway().call()
            except:
                addresses["aggLayerGatewayAddress"] = None
            
            return addresses
        except Exception as e:
            print(f"Error getting network addresses: {e}")
            return {}

    def get_rollup_manager_details(self) -> Dict[str, Any]:
        """Get additional details from RollupManager for enhanced UI"""
        try:
            details = {}
            
            # Use cached version if available
            if 'versions' in self._static_cache:
                details["rollupManagerVersion"] = self._static_cache['versions'].get('rollupManager', 'Unknown')
            else:
                # Fallback to direct call
                try:
                    details["rollupManagerVersion"] = self.rollup_manager.functions.ROLLUP_MANAGER_VERSION().call()
                except:
                    try:
                        details["rollupManagerVersion"] = self.rollup_manager.functions.version().call()
                    except:
                        details["rollupManagerVersion"] = "Unknown"
            
            # System status and basic info
            details["isEmergencyState"] = self.rollup_manager.functions.isEmergencyState().call()
            details["rollupTypeCount"] = self.rollup_manager.functions.rollupTypeCount().call()
            
            # Get rollup information
            rollup_count = self.get_rollup_count()
            rollup_details = []
            for rollup_id in range(1, rollup_count + 1):
                try:
                    # Try rollupIDToRollupDataDeserialized first, fallback to rollupIDToRollupDataV2
                    rollup_raw_data = None
                    try:
                        rollup_raw_data = self.rollup_manager.functions.rollupIDToRollupDataDeserialized(rollup_id).call()
                        data_source = "deserialized"
                    except:
                        rollup_raw_data = self.rollup_manager.functions.rollupIDToRollupDataV2(rollup_id).call()
                        data_source = "v2"
                    
                    if rollup_raw_data:
                        rollup_info = self._parse_rollup_raw_data(rollup_id, rollup_raw_data, data_source)
                        rollup_details.append(rollup_info)
                except Exception as e:
                    print(f"Error getting rollup data for ID {rollup_id}: {e}")
                    rollup_details.append({
                        "rollupID": rollup_id,
                        "error": str(e),
                        "status": "Error"
                    })
            
            details["rollups"] = rollup_details
            
            # Timestamps (convert to human readable if needed)
            from datetime import datetime
            
            last_aggregation = self.rollup_manager.functions.lastAggregationTimestamp().call()
            details["lastAggregationTimestamp"] = last_aggregation
            if last_aggregation > 0:
                details["lastAggregationTime"] = datetime.fromtimestamp(last_aggregation).strftime("%Y-%m-%d %H:%M:%S UTC")
                details["lastAggregationRelative"] = self.get_relative_time(last_aggregation)
            else:
                details["lastAggregationTime"] = "Never"
                details["lastAggregationRelative"] = "Never"
            
            # Emergency state recovery time
            emergency_recovery = self.rollup_manager.functions.lastDeactivatedEmergencyStateTimestamp().call()
            details["lastEmergencyRecoveryTimestamp"] = emergency_recovery
            if emergency_recovery > 0:
                details["lastEmergencyRecoveryTime"] = datetime.fromtimestamp(emergency_recovery).strftime("%Y-%m-%d %H:%M:%S UTC")
                details["lastEmergencyRecoveryRelative"] = self.get_relative_time(emergency_recovery)
            else:
                details["lastEmergencyRecoveryTime"] = "Never"
                details["lastEmergencyRecoveryRelative"] = "Never"
            
            # Contract version info
            try:
                details["version"] = self.rollup_manager.functions.version().call()
            except:
                details["version"] = "Unknown"
                
            try:
                details["rollupManagerVersion"] = self.rollup_manager.functions.ROLLUP_MANAGER_VERSION().call()
            except:
                details["rollupManagerVersion"] = "Unknown"
            
            return details
        except Exception as e:
            print(f"Error getting rollup manager details: {e}")
            return {}

    def _parse_rollup_raw_data(self, rollup_id: int, raw_data: tuple, data_source: str) -> Dict[str, Any]:
        """Parse raw rollup data from contract into a readable format"""
        try:
            # Parse according to rollupIDToRollupDataDeserialized ABI structure:
            # [0]: rollupContract, [1]: chainID, [2]: verifier, [3]: forkID, [4]: lastLocalExitRoot
            # [5]: lastBatchSequenced, [6]: lastVerifiedBatch, [7]: _legacyLastPendingState
            # [8]: _legacyLastPendingStateConsolidated, [9]: lastVerifiedBatchBeforeUpgrade, [10]: rollupTypeID, [11]: rollupCompatibilityID
            rollup_info = {
                "rollupID": rollup_id,
                "dataSource": data_source,
                "rollupContract": raw_data[0] if len(raw_data) > 0 else "0x0000000000000000000000000000000000000000",
                "chainID": raw_data[1] if len(raw_data) > 1 else 0,
                "verifier": raw_data[2] if len(raw_data) > 2 else "0x0000000000000000000000000000000000000000",  # This is the verifier field!
                "forkID": raw_data[3] if len(raw_data) > 3 else 0,
                "lastLocalExitRoot": self._format_program_vkey(raw_data[4]) if len(raw_data) > 4 else "",
                # Skip unused fields: [5-9] various batch and legacy fields
                "rollupTypeID": raw_data[10] if len(raw_data) > 10 else 0,
            }
            
            # Get rollupVerifierType from correct index based on ABI
            rollup_info["rollupVerifierType"] = raw_data[11] if len(raw_data) > 11 else 0
            
            # Add human-readable verifier type
            verifier_type = rollup_info["rollupVerifierType"]
            if verifier_type == 0:
                rollup_info["rollupVerifierTypeFriendly"] = "zkEVM"
                rollup_info["type"] = "zkEVM"
            elif verifier_type == 1:
                rollup_info["rollupVerifierTypeFriendly"] = "Pessimistic Proof (PP)"
                rollup_info["type"] = "PP"
            elif verifier_type == 2:
                rollup_info["rollupVerifierTypeFriendly"] = "AggLayer Gateway"
                rollup_info["type"] = "ALGateway"
            else:
                rollup_info["rollupVerifierTypeFriendly"] = f"Unknown ({verifier_type})"
                rollup_info["type"] = "Unknown"
            
            # Determine if rollup is active
            rollup_info["isActive"] = rollup_info["rollupContract"] != "0x0000000000000000000000000000000000000000"
            
            # Get rollup type details if available  
            try:
                rollup_type_details = self.get_rollup_type_details(rollup_info["rollupTypeID"])
                # Only add rollup type details that don't conflict with deserialized data
                if rollup_type_details:
                    rollup_info["rollupTypeConsensus"] = rollup_type_details.get("rollupTypeConsensus", "")
                    rollup_info["rollupTypeForkID"] = rollup_type_details.get("rollupTypeForkID", 0)
                    rollup_info["rollupTypeVerifierType"] = rollup_type_details.get("rollupTypeVerifierType", 0)
                    rollup_info["obsolete"] = rollup_type_details.get("obsolete", False)
                    rollup_info["genesis"] = rollup_type_details.get("genesis", "")
                    rollup_info["rollupTypeProgramVKey"] = rollup_type_details.get("rollupTypeProgramVKey", "")
            except Exception as e:
                print(f"Warning: Could not get rollup type details for rollup {rollup_id}: {e}")
            
            # Multisig information is now lazy-loaded - set placeholder values
            rollup_info["rollupSignersCount"] = None  # Indicates lazy loading needed
            rollup_info["rollupThreshold"] = None
            rollup_info["rollupSigners"] = []
            rollup_info["rollupMultisigHash"] = None
            rollup_info["useDefaultSigners"] = None
            rollup_info["aggchainType"] = None
            rollup_info["optimisticMode"] = None
            
            return rollup_info
            
        except Exception as e:
            print(f"Error parsing rollup data for ID {rollup_id}: {e}")
            return {
                "rollupID": rollup_id,
                "dataSource": data_source,
                "error": str(e),
                "status": "Parse Error"
            }

    def _format_program_vkey(self, vkey_data) -> str:
        """Format program vkey data handling both bytes and int types"""
        try:
            if vkey_data is None:
                return ""
            elif isinstance(vkey_data, bytes):
                # Handle bytes type
                if vkey_data == b'\x00' * len(vkey_data):
                    return ""
                return vkey_data.hex()
            elif isinstance(vkey_data, int):
                # Handle integer type (convert to hex)
                if vkey_data == 0:
                    return ""
                return hex(vkey_data)[2:]  # Remove '0x' prefix
            else:
                # Handle other types by converting to string
                return str(vkey_data)
        except Exception as e:
            print(f"Warning: Could not format program vkey: {e}")
            return ""
    
    def _format_aggchain_type(self, value) -> str:
        """Format AGGCHAIN_TYPE bytes2 value for display"""
        try:
            # Convert bytes2 to integer for comparison
            if isinstance(value, bytes):
                # Convert bytes to int (big-endian)
                int_value = int.from_bytes(value, byteorder='big')
            elif isinstance(value, int):
                int_value = value
            else:
                return str(value)
            
            # Map known values
            if int_value == 0:
                return "ECDSAMultisig"
            elif int_value == 1:
                return "FEP"
            else:
                # Display the hex value for unknown types
                return f"0x{int_value:04x}"
        except:
            return str(value)
    
    def _get_rollup_signers_info(self, rollup_contract_address: str) -> Dict[str, Any]:
        """Get signers information from individual rollup contract"""
        try:
            # ABI for rollup-level signers functions
            rollup_signers_abi = [
                {'inputs': [], 'name': 'getAggchainSignersCount', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'getThreshold', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
                {
                    'inputs': [], 
                    'name': 'getAggchainSignerInfos', 
                    'outputs': [{
                        'internalType': 'tuple(address,string)[]', 
                        'name': '', 
                        'type': 'tuple[]',
                        'components': [
                            {'internalType': 'address', 'name': 'addr', 'type': 'address'},
                            {'internalType': 'string', 'name': 'url', 'type': 'string'}
                        ]
                    }], 
                    'stateMutability': 'view', 
                    'type': 'function'
                },
                {'inputs': [], 'name': 'getAggchainMultisigHash', 'outputs': [{'internalType': 'bytes32', 'name': '', 'type': 'bytes32'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'useDefaultSigners', 'outputs': [{'internalType': 'bool', 'name': '', 'type': 'bool'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'AGGCHAIN_TYPE', 'outputs': [{'internalType': 'bytes2', 'name': '', 'type': 'bytes2'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'optimisticMode', 'outputs': [{'internalType': 'bool', 'name': '', 'type': 'bool'}], 'stateMutability': 'view', 'type': 'function'}
            ]
            
            rollup_contract = self.w3.eth.contract(
                address=rollup_contract_address,
                abi=rollup_signers_abi
            )
            
            def safe_call(func, default_value):
                """Safely call contract function with fallback"""
                try:
                    return func()
                except:
                    return default_value
            
            # Get rollup-level signers info
            signers_count = safe_call(lambda: rollup_contract.functions.getAggchainSignersCount().call(), 0)
            threshold = safe_call(lambda: rollup_contract.functions.getThreshold().call(), 0)
            
            # Get signer infos with URLs
            signer_infos_raw = safe_call(lambda: rollup_contract.functions.getAggchainSignerInfos().call(), [])
            rollup_signers_parsed = []
            
            for signer_info in signer_infos_raw:
                try:
                    rollup_signers_parsed.append({
                        "address": signer_info[0],
                        "url": signer_info[1] if signer_info[1] else ""
                    })
                except:
                    continue
            
            multisig_hash = safe_call(lambda: rollup_contract.functions.getAggchainMultisigHash().call().hex() if rollup_contract.functions.getAggchainMultisigHash().call() else "0x", "0x")
            use_default_signers = safe_call(lambda: rollup_contract.functions.useDefaultSigners().call(), False)
            
            # Get AGGCHAIN_TYPE (for AggLayer Gateway rollups)
            aggchain_type_raw = safe_call(lambda: rollup_contract.functions.AGGCHAIN_TYPE().call(), b'\x00\x00')
            aggchain_type_display = self._format_aggchain_type(aggchain_type_raw)
            
            # Get optimisticMode (only for FEP AggLayer Gateway rollups)
            optimistic_mode = None
            if aggchain_type_display == "FEP":
                optimistic_mode = safe_call(lambda: rollup_contract.functions.optimisticMode().call(), False)
            
            result = {
                "rollupSignersCount": signers_count,
                "rollupThreshold": threshold,
                "rollupSigners": rollup_signers_parsed,
                "rollupMultisigHash": multisig_hash,
                "useDefaultSigners": use_default_signers,
                "aggchainType": aggchain_type_display,
                "optimisticMode": optimistic_mode
            }
            
            return result
            
        except Exception as e:
            return {
                "rollupSignersCount": 0,
                "rollupThreshold": 0,
                "rollupSigners": [],
                "rollupMultisigHash": "0x",
                "useDefaultSigners": False,
                "aggchainType": "N/A",
                "optimisticMode": None
            }

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
        """Get AggLayer certificate data for a rollup with enhanced L1 transaction info"""
        if not agg_layer_url:
            return {"settled": None, "pending": None, "latest_known": None, "epoch_config": None}
            
        try:
            # Get latest settled certificate using RPC calls (same as React app)
            settled = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getLatestSettledCertificateHeader",
                [rollup_id]
            )
            
            # Enhance settled certificate with L1 transaction data
            if settled and settled.get('settlement_tx_hash'):
                try:
                    l1_data = self.get_settlement_transaction_data(settled['settlement_tx_hash'])
                    settled.update(l1_data)
                except Exception as e:
                    print(f"Warning: Could not get L1 settlement data: {e}")
            
            # Get latest pending certificate
            pending = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getLatestPendingCertificateHeader", 
                [rollup_id]
            )
            
            # Get latest known certificate (any status) - provides additional context
            latest_known = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getLatestKnownCertificateHeader",
                [rollup_id]
            )
            
            # Enhance latest known certificate with L1 data if it has settlement info
            if latest_known and latest_known.get('settlement_tx_hash'):
                try:
                    l1_data = self.get_settlement_transaction_data(latest_known['settlement_tx_hash'])
                    latest_known.update(l1_data)
                except Exception as e:
                    print(f"Warning: Could not get L1 settlement data for latest known: {e}")
            
            # Get epoch configuration for timing context
            epoch_config = self.call_agglayer_rpc(
                agg_layer_url,
                "interop_getEpochConfiguration",
                []
            )
            
            return {
                "settled": settled,
                "pending": pending,
                "latest_known": latest_known,
                "epoch_config": epoch_config
            }
        except Exception as e:
            print(f"Error fetching certificate data for rollup {rollup_id}: {e}")
            return {"settled": None, "pending": None, "latest_known": None, "epoch_config": None}

    def get_relative_time(self, timestamp: int) -> str:
        """Convert timestamp to relative time string like '5 minutes ago'"""
        try:
            from datetime import datetime
            
            current_time = datetime.now()
            settlement_time = datetime.fromtimestamp(timestamp)
            time_diff = current_time - settlement_time
            
            total_seconds = int(time_diff.total_seconds())
            
            if total_seconds < 60:
                return f"{total_seconds} seconds ago"
            elif total_seconds < 3600:  # Less than 1 hour
                minutes = total_seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif total_seconds < 86400:  # Less than 1 day
                hours = total_seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif total_seconds < 2592000:  # Less than 30 days
                days = total_seconds // 86400
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                months = total_seconds // 2592000
                return f"{months} month{'s' if months != 1 else ''} ago"
                
        except Exception as e:
            print(f"Error calculating relative time: {e}")
            return ""

    def get_settlement_transaction_data(self, tx_hash: str) -> Dict:
        """Get additional data from the L1 settlement transaction including L1 Info Root from events"""
        try:
            from datetime import datetime
            
            # Get transaction receipt
            tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Get block data for timestamp
            block = self.w3.eth.get_block(tx_receipt.blockNumber)
            
            # Convert timestamp to human-readable format
            settlement_timestamp = block.timestamp
            settlement_datetime = datetime.fromtimestamp(settlement_timestamp)
            
            # Base settlement data
            settlement_data = {
                "settlement_block_number": tx_receipt.blockNumber,
                "settlement_timestamp": settlement_timestamp,
                "settlement_datetime": settlement_datetime.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "settlement_relative_time": self.get_relative_time(settlement_timestamp),
                "settlement_gas_used": tx_receipt.gasUsed,
                "settlement_status": "Success" if tx_receipt.status == 1 else "Failed",
                "settlement_block_hash": block.hash.hex(),
                "settlement_block_gas_used": block.gasUsed,
                "settlement_block_gas_limit": block.gasLimit
            }
            
            # Try to extract L1 Info Root and other event data from settlement transaction
            try:
                # Event signature for VerifyPessimisticStateTransition
                event_signature = "0xdf47e7dbf79874ec576f516c40bc1483f7c8ddf4b45bfd4baff4650f1229a711"
                
                for log in tx_receipt.logs:
                    if log.address.lower() == self.rollup_manager.address.lower():
                        if log.topics[0].hex() == event_signature:
                            # Decode VerifyPessimisticStateTransition event
                            trusted_aggregator = '0x' + log.topics[2].hex()[-40:]  # Last 40 chars for address
                            
                            # Decode data part (6 bytes32 values)
                            data = log.data.hex()[2:]  # Remove 0x
                            prev_pessimistic_root = '0x' + data[0:64]
                            new_pessimistic_root = '0x' + data[64:128]
                            prev_local_exit_root = '0x' + data[128:192]
                            new_local_exit_root = '0x' + data[192:256]
                            l1_info_root = '0x' + data[256:320]
                            
                            # Add the event data to settlement data
                            settlement_data.update({
                                "settlement_trusted_aggregator": trusted_aggregator,
                                "settlement_prev_pessimistic_root": prev_pessimistic_root,
                                "settlement_new_pessimistic_root": new_pessimistic_root,
                                "settlement_l1_info_root": l1_info_root
                            })
                            break
                            
            except Exception as e:
                print(f"Warning: Could not decode settlement events for {tx_hash}: {e}")
            
            return settlement_data
            
        except Exception as e:
            print(f"Error getting settlement transaction data for {tx_hash}: {e}")
            return {}

    def get_previous_settlement_event(self, rollup_id: int, current_settlement_block: int, agg_layer_url: str = None) -> List[Dict]:
        """Get the single previous settlement event by searching backwards from current settlement block"""
        try:
            from datetime import datetime
            
            if not current_settlement_block or current_settlement_block <= 0:
                print("⚠️ No valid current settlement block provided")
                return []
            
            print(f"🔍 Searching backwards from block {current_settlement_block - 1} for the previous settlement...")
            
            # Event signature for VerifyPessimisticStateTransition
            event_signature = "0xdf47e7dbf79874ec576f516c40bc1483f7c8ddf4b45bfd4baff4650f1229a711"
            
            # Search backwards in chunks for efficiency (1000 blocks at a time)
            chunk_size = 1000
            search_block = current_settlement_block - 1
            
            while search_block > 0:
                from_block = max(0, search_block - chunk_size)
                to_block = search_block
                
                print(f"   📋 Searching blocks {from_block} to {to_block}...")
                
                # Create filter for the specific event on rollup manager
                event_filter = {
                    'fromBlock': from_block,
                    'toBlock': to_block,
                    'address': self.rollup_manager.address,
                    'topics': [
                        event_signature,
                        f"0x{rollup_id:064x}"  # rollup_id as indexed parameter (64 hex chars)
                    ]
                }
                
                # Get the logs
                logs = self.w3.eth.get_logs(event_filter)
                
                if logs:
                    print(f"   ✅ Found {len(logs)} settlement event(s) in this range")
                    # Get the most recent one (highest block number)
                    latest_log = max(logs, key=lambda x: x.blockNumber)
                    
                    # Decode the settlement event
                    settlement = self._decode_settlement_event(latest_log)
                    if settlement:
                        print(f"   🎯 Previous settlement found at block {settlement['block_number']}")
                        
                        # Try to enrich with certificate data from AggLayer
                        if agg_layer_url and settlement.get('transaction_hash'):
                            settlement = self._enrich_settlement_with_certificate_data(
                                settlement, rollup_id, agg_layer_url
                            )
                        
                        return [settlement]  # Return as list for consistency
                
                # Move to next chunk
                search_block = from_block - 1
                if from_block == 0:
                    break
            
            print(f"   📝 No previous settlements found back to block 0")
            return []
            
        except Exception as e:
            print(f"Error getting previous settlement event: {e}")
            return []
    
    def _decode_settlement_event(self, log) -> Dict:
        """Helper function to decode a single settlement event log"""
        try:
            from datetime import datetime
            
            # Decode VerifyPessimisticStateTransition event
            # rollupID (indexed), trustedAggregator (indexed), then 6 bytes32 values in data
            rollup_id_from_log = int(log.topics[1].hex(), 16)
            trusted_aggregator = '0x' + log.topics[2].hex()[-40:]  # Last 40 chars for address
            
            # Decode data part (6 bytes32 values)
            data = log.data.hex()[2:]  # Remove 0x
            prev_pessimistic_root = '0x' + data[0:64]
            new_pessimistic_root = '0x' + data[64:128]
            prev_local_exit_root = '0x' + data[128:192]
            new_local_exit_root = '0x' + data[192:256]
            l1_info_root = '0x' + data[256:320]
            
            # Get block info for timestamp
            block = self.w3.eth.get_block(log.blockNumber)
            settlement_datetime = datetime.fromtimestamp(block.timestamp)
            
            # Get transaction receipt for gas information
            settlement_gas_used = None
            settlement_block_hash = None
            try:
                tx_receipt = self.w3.eth.get_transaction_receipt(log.transactionHash)
                settlement_gas_used = tx_receipt.gasUsed
                settlement_block_hash = block.hash.hex()
            except Exception as e:
                print(f"Warning: Could not get transaction receipt for gas info: {e}")
            
            return {
                "block_number": log.blockNumber,
                "transaction_hash": log.transactionHash.hex(),
                "timestamp": block.timestamp,
                "datetime": settlement_datetime.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "relative_time": self.get_relative_time(block.timestamp),
                "rollup_id": rollup_id_from_log,
                "trusted_aggregator": trusted_aggregator,
                "prev_pessimistic_root": prev_pessimistic_root,
                "new_pessimistic_root": new_pessimistic_root,
                "prev_local_exit_root": prev_local_exit_root,
                "new_local_exit_root": new_local_exit_root,
                "l1_info_root": l1_info_root,
                "settlement_gas_used": settlement_gas_used,
                "settlement_block_hash": settlement_block_hash
            }
        except Exception as e:
            print(f"Warning: Could not decode settlement event: {e}")
            return None
    
    def _enrich_settlement_with_certificate_data(self, settlement: Dict, rollup_id: int, agg_layer_url: str) -> Dict:
        """Get certificate metadata for a settlement using the local exit roots to match certificates"""
        try:
            settlement_tx_hash = settlement.get('transaction_hash')
            prev_local_exit_root = settlement.get('prev_local_exit_root')
            new_local_exit_root = settlement.get('new_local_exit_root')
            
            if not settlement_tx_hash:
                return settlement
                
            print(f"   🔍 Searching AggLayer for certificate with settlement_tx_hash: {settlement_tx_hash[:10]}...")
            
            # Strategy: Use the local exit roots to find the certificate
            # Each certificate has prev_local_exit_root and new_local_exit_root
            # We can search certificates to find one with matching roots
            try:
                # Get current latest settled certificate as reference
                latest_settled = self.call_agglayer_rpc(agg_layer_url, "interop_getLatestSettledCertificateHeader", [rollup_id])
                if not latest_settled:
                    print(f"   ⚠️ Could not get latest settled certificate")
                    raise Exception("No latest settled certificate")
                    
                # Check if the current latest settled certificate matches our settlement
                if latest_settled.get('settlement_tx_hash') == settlement_tx_hash:
                    print(f"   ✅ Settlement matches the current latest certificate")
                    settlement.update({
                        'height': latest_settled.get('height'),
                        'epoch_number': latest_settled.get('epoch_number'),
                        'certificate_index': latest_settled.get('certificate_index'),
                        'certificate_id': latest_settled.get('certificate_id')
                    })
                    return settlement
                
                # If not the latest, get the latest known certificate and work backwards
                latest_known = self.call_agglayer_rpc(agg_layer_url, "interop_getLatestKnownCertificateHeader", [rollup_id])
                if latest_known and latest_known.get('certificate_id'):
                    # Try to get the certificate by ID and check if it matches
                    cert_header = self.call_agglayer_rpc(agg_layer_url, "interop_getCertificateHeader", [latest_known['certificate_id']])
                    if cert_header:
                        print(f"   📋 Retrieved certificate header for ID: {latest_known['certificate_id'][:10]}...")
                        
                        # Check if this certificate matches our settlement by comparing exit roots
                        if (cert_header.get('prev_local_exit_root') == prev_local_exit_root and 
                            cert_header.get('new_local_exit_root') == new_local_exit_root):
                            print(f"   ✅ Found matching certificate by exit root comparison")
                            settlement.update({
                                'height': cert_header.get('height'),
                                'epoch_number': cert_header.get('epoch_number'),
                                'certificate_index': cert_header.get('certificate_index'),
                                'certificate_id': cert_header.get('certificate_id')
                            })
                            return settlement
                        else:
                            print(f"   🔍 Exit roots don't match, this is likely a different certificate")
                            print(f"      Settlement prev_root: {prev_local_exit_root}")
                            print(f"      Certificate prev_root: {cert_header.get('prev_local_exit_root')}")
                            
            except Exception as e:
                print(f"   ⚠️ Error during AggLayer certificate search: {e}")
            
            # Enhanced approach: since we have exit root information, provide more context
            settlement.update({
                'height': 'N/A',
                'epoch_number': 'N/A',
                'certificate_index': 'N/A',
                'certificate_id': 'N/A'
            })
            
            print(f"   📋 Provided historical certificate context for settlement {settlement_tx_hash[:10]}...")
            return settlement
            
        except Exception as e:
            print(f"Warning: Could not enrich settlement with certificate data: {e}")
            # Provide meaningful context even when search fails
            tx_hash = settlement.get('transaction_hash', 'unknown')[:10]
            settlement.update({
                'height': f'Certificate for {tx_hash}...',
                'epoch_number': f'Certificate for {tx_hash}...',
                'certificate_index': f'Certificate for {tx_hash}...',
                'certificate_id': f'Certificate for {tx_hash}...'
            })
            return settlement
            
    # Keep the old function for backwards compatibility but mark as deprecated
    def get_recent_settlement_events(self, rollup_id: int, blocks_back: int = 50, exclude_latest_settlement_block: int = None) -> List[Dict]:
        """DEPRECATED: Use get_previous_settlement_event instead"""
        if exclude_latest_settlement_block:
            return self.get_previous_settlement_event(rollup_id, exclude_latest_settlement_block)
        else:
            # Fallback to old behavior
            try:
                from datetime import datetime
                
                current_block = self.w3.eth.get_block_number()
                to_block = current_block
                from_block = max(0, current_block - blocks_back)
                print(f"🔍 Searching for settlement events from block {from_block} to {to_block}")
                
                # Event signature for VerifyPessimisticStateTransition
                event_signature = "0xdf47e7dbf79874ec576f516c40bc1483f7c8ddf4b45bfd4baff4650f1229a711"
                
                # Create filter for the specific event on rollup manager
                event_filter = {
                    'fromBlock': from_block,
                    'toBlock': to_block,
                    'address': self.rollup_manager.address,
                    'topics': [
                        event_signature,
                        f"0x{rollup_id:064x}"  # rollup_id as indexed parameter (64 hex chars)
                    ]
                }
                
                # Get the logs
                logs = self.w3.eth.get_logs(event_filter)
                print(f"📋 Found {len(logs)} settlement events for rollup {rollup_id}")
                
                settlements = []
                for log in logs:
                    settlement = self._decode_settlement_event(log)
                    if settlement:
                        settlements.append(settlement)
                
                # Sort by block number (most recent first)
                settlements.sort(key=lambda x: x["block_number"], reverse=True)
                return settlements
                
            except Exception as e:
                print(f"Error getting recent settlement events: {e}")
                return []

    def get_sequencer_info(self, rollup_contract_address: str) -> Dict:
        """Get sequencer information from rollup contract"""
        try:
            if rollup_contract_address == "0x0000000000000000000000000000000000000000":
                return {}
                
            # Get sequencer info
            sequencer_info = {}
            
            # Try different ABIs as different rollup types may have different interfaces
            abi_files = ["AggchainFEP.json", "PolygonZkEVM.json", "PolygonValidiumEtrog.json"]
            
            for abi_file in abi_files:
                try:
                    rollup_abi = load_abi(abi_file)
                    rollup_contract = self.w3.eth.contract(
                        address=rollup_contract_address,
                        abi=rollup_abi
                    )
                    
                    # Try to get sequencer info
                    sequencer_info["trustedSequencer"] = rollup_contract.functions.trustedSequencer().call()
                    sequencer_info["trustedSequencerURL"] = rollup_contract.functions.trustedSequencerURL().call()
                    
                    print(f"Successfully got sequencer info using {abi_file}")
                    break  # Success, exit the loop
                    
                except Exception as e:
                    print(f"Failed to get sequencer info using {abi_file}: {e}")
                    continue  # Try next ABI
            
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
                "verifier": rollup_data[2],                         # Verifier address
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
                "verifier": rollup_type_data[1],              # Verifier contract address (zero address is EXPECTED for PP and AggLayer Gateway types)
                "rollupTypeForkID": rollup_type_data[2],      # Fork ID from type
                "rollupTypeVerifierType": rollup_type_data[3], # Verifier type (0=zkEVM, 1=PP, 2=AggLayer Gateway)
                "obsolete": rollup_type_data[4],              # Obsolete flag
                "genesis": self._format_program_vkey(rollup_type_data[5]) if rollup_type_data[5] else "",  # Genesis block hash
                "rollupTypeProgramVKey": self._format_program_vkey(rollup_type_data[6]) if rollup_type_data[6] else "",  # Program VKey from type
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
                    
                    # Get sequencer info (trusted sequencer address)
                    sequencer_info = self.get_sequencer_info(rollup_data["rollupContract"])
                    rollup_data.update(sequencer_info)
                    
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
                
                # Multisig information is now lazy-loaded via API to improve page load performance
                # Set placeholder values - actual data will be fetched when multisig section is expanded
                rollup_data["rollupSignersCount"] = None  # Indicates lazy loading needed
                rollup_data["rollupThreshold"] = None
                rollup_data["rollupSigners"] = []
                rollup_data["rollupMultisigHash"] = None
                rollup_data["useDefaultSigners"] = None
                rollup_data["aggchainType"] = None
                rollup_data["optimisticMode"] = None
                
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
            
            # Get epoch configuration if AggLayer URL is available
            epoch_config = None
            if self.env_config.aggLayerURL:
                try:
                    epoch_config = self.call_agglayer_rpc(
                        self.env_config.aggLayerURL,
                        "interop_getEpochConfiguration",
                        []
                    )
                except Exception as e:
                    print(f"Warning: Could not get epoch configuration: {e}")
            
            # Get network addresses (cached)
            network_addresses = self.get_network_addresses()
            
            # For now, only get basic info for home page load
            # Detailed info will be loaded on-demand when sections are expanded
            basic_info = {
                "isConnected": self.is_connected(),
                "rollupCount": rollup_count,
                "activeCounts": active_counts,
                "versions": self._static_cache.get('versions', {})
            }
            
            # Get full details (but with addresses cached for speed)
            rollup_manager_details = self.get_rollup_manager_details()
            bridge_details = self.get_bridge_details(network_addresses.get("bridgeAddress")) if network_addresses.get("bridgeAddress") else {}
            ger_details = self.get_global_exit_root_details(network_addresses.get("globalExitRootManager")) if network_addresses.get("globalExitRootManager") else {}
            agglayer_details = self.get_agglayer_gateway_details(network_addresses.get("aggLayerGatewayAddress")) if network_addresses.get("aggLayerGatewayAddress") else {}
            
            return {
                "rollupManagerAddress": self.env_config.rollupManagerContractAddress,
                "rpcURL": self.env_config.rpcURL,
                "aggLayerURL": self.env_config.aggLayerURL,
                "rollupCount": rollup_count,
                "activeCounts": active_counts,
                "isConnected": self.is_connected(),
                "epochConfig": epoch_config,
                "rollupManagerDetails": rollup_manager_details,
                "bridgeDetails": bridge_details,
                "gerDetails": ger_details,
                "aggLayerDetails": agglayer_details,
                "basicInfo": basic_info
            }
        except Exception as e:
            print(f"Error getting environment summary: {e}")
            return {
                "error": str(e),
                "isConnected": False
            }
    
    def _get_basic_rollup_manager_details(self) -> Dict[str, Any]:
        """Get basic rollup manager info (fast version for initial page load)"""
        try:
            # Only load essential info, skip expensive operations like individual rollup details
            details = {
                "rollupManagerVersion": self._static_cache.get('versions', {}).get('rollupManager', 'Unknown'),
                "isEmergencyState": self.rollup_manager.functions.isEmergencyState().call(),
                "rollupTypeCount": self.rollup_manager.functions.rollupTypeCount().call(),
            }
            return details
        except Exception as e:
            print(f"Warning: Error getting basic rollup manager details: {e}")
            return {}
    
    def _get_basic_bridge_details(self, bridge_address: str) -> Dict[str, Any]:
        """Get basic bridge info (fast version for initial page load)"""
        if not bridge_address:
            return {}
        try:
            # Only get essential info, skip deposit counts and other expensive calls
            bridge_abi = [
                {'inputs': [], 'name': 'BRIDGE_VERSION', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'isEmergencyState', 'outputs': [{'internalType': 'bool', 'name': '', 'type': 'bool'}], 'stateMutability': 'view', 'type': 'function'},
            ]
            bridge_contract = self.w3.eth.contract(address=bridge_address, abi=bridge_abi)
            
            details = {
                "bridgeVersion": bridge_contract.functions.BRIDGE_VERSION().call(),
                "isEmergencyState": bridge_contract.functions.isEmergencyState().call(),
            }
            return details
        except Exception as e:
            print(f"Warning: Error getting basic bridge details: {e}")
            return {}
    
    def _get_basic_ger_details(self, ger_address: str) -> Dict[str, Any]:
        """Get basic GER info (fast version for initial page load)"""
        if not ger_address:
            return {}
        try:
            # Only get version info
            ger_abi = [
                {'inputs': [], 'name': 'version', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'pure', 'type': 'function'},
            ]
            ger_contract = self.w3.eth.contract(address=ger_address, abi=ger_abi)
            
            details = {
                "gerVersion": ger_contract.functions.version().call(),
            }
            return details
        except Exception as e:
            print(f"Warning: Error getting basic GER details: {e}")
            return {}
    
    def _get_basic_agglayer_details(self, gateway_address: str) -> Dict[str, Any]:
        """Get basic AggLayer Gateway info (fast version for initial page load)"""
        if not gateway_address:
            return {}
        try:
            # Only get basic info, skip signers list and expensive calls
            gateway_abi = [
                {'inputs': [], 'name': 'version', 'outputs': [{'internalType': 'string', 'name': '', 'type': 'string'}], 'stateMutability': 'pure', 'type': 'function'},
                {'inputs': [], 'name': 'getThreshold', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
                {'inputs': [], 'name': 'getAggchainSignersCount', 'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}], 'stateMutability': 'view', 'type': 'function'},
            ]
            gateway_contract = self.w3.eth.contract(address=gateway_address, abi=gateway_abi)
            
            details = {
                "gatewayVersion": gateway_contract.functions.version().call(),
                "threshold": gateway_contract.functions.getThreshold().call(),
                "signersCount": gateway_contract.functions.getAggchainSignersCount().call(),
                # Skip signers list for now - will be loaded when expanded
            }
            return details
        except Exception as e:
            print(f"Warning: Error getting basic AggLayer Gateway details: {e}")
            return {}

import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class EnvironmentConfig:
    rollupManagerContractAddress: str
    rpcURL: str
    aggLayerURL: Optional[str] = None

@dataclass
class L2Config:
    rollupID: int
    l2rpc: str
    agchainmanager_key: str

class ConfigLoader:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise Exception(f"Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in config file: {e}")
    
    def get_environment(self) -> EnvironmentConfig:
        """Get the single environment configuration"""
        try:
            return EnvironmentConfig(
                rollupManagerContractAddress=self.config["rollupManagerContractAddress"],
                rpcURL=self.config["rpcURL"],
                aggLayerURL=self.config.get("aggLayerURL")
            )
        except KeyError as e:
            raise Exception(f"Missing required configuration field: {e}")
        except Exception as e:
            raise Exception(f"Error loading environment configuration: {e}")
    
    def get_l2_config(self, rollup_id: int) -> Optional[L2Config]:
        """Get L2 RPC configuration for a specific rollup"""
        l2rpcs = self.config.get("l2rpcs", [])
        for l2_config in l2rpcs:
            if l2_config.get("rollupID") == rollup_id:
                return L2Config(
                    rollupID=l2_config["rollupID"],
                    l2rpc=l2_config["l2rpc"],
                    agchainmanager_key=l2_config["agchainmanager_key"]
                )
        return None
    
    def get_all_l2_configs(self) -> List[L2Config]:
        """Get all L2 RPC configurations"""
        l2rpcs = self.config.get("l2rpcs", [])
        configs = []
        for l2_config in l2rpcs:
            try:
                configs.append(L2Config(
                    rollupID=l2_config["rollupID"],
                    l2rpc=l2_config["l2rpc"],
                    agchainmanager_key=l2_config["agchainmanager_key"]
                ))
            except KeyError:
                continue  # Skip invalid entries
        return configs
    
    def get_l2rpcs_dict(self) -> Dict[str, str]:
        """Get L2 RPCs in the old dict format for backward compatibility"""
        l2rpcs = self.config.get("l2rpcs", [])
        result = {}
        for l2_config in l2rpcs:
            try:
                result[str(l2_config["rollupID"])] = l2_config["l2rpc"]
            except KeyError:
                continue
        return result

# Global config instance
if os.getenv("CONFIG_FILE"):
    config_loader = ConfigLoader(os.getenv("CONFIG_FILE"))
else:
    config_loader = ConfigLoader()

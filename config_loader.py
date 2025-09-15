import json
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class EnvironmentConfig:
    rollupManagerContractAddress: str
    rollupManagerContractDeploymentBlock: int
    rpcURL: str
    aggLayerURL: Optional[str] = None

@dataclass
class L2Config:
    rpc: str

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
                rollupManagerContractDeploymentBlock=self.config["rollupManagerContractDeploymentBlock"],
                rpcURL=self.config["rpcURL"],
                aggLayerURL=self.config.get("aggLayerURL")
            )
        except KeyError as e:
            raise Exception(f"Missing required configuration field: {e}")
        except Exception as e:
            raise Exception(f"Error loading environment configuration: {e}")
    
    def get_l2_config(self, rollup_id: str) -> Optional[L2Config]:
        """Get L2 RPC configuration for a specific rollup"""
        l2rpcs = self.config.get("l2rpcs", {})
        return l2rpcs.get(rollup_id, None)

# Global config instance
config_loader = ConfigLoader()
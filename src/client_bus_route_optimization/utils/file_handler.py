import yaml
import pickle
import json
from pathlib import Path

# load and save YAML files
class JsonRepository():
    @staticmethod
    def load(file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {file_path}")
        with open(path, "r") as f:
            return yaml.safe_load(f)

    @staticmethod
    def save(data, file_path: str):
        path = Path(file_path)
        with open(path, "w") as f:
            yaml.safe_dump(data, f)

# load and save PKL files
class PklRepository():
    @staticmethod
    def load(file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PKL file not found: {file_path}")
        with open(path, "rb") as f:
            return pickle.load(f)

    @staticmethod
    def save(data, file_path: str):
        path = Path(file_path)
        with open(path, "wb") as f:
            pickle.dump(data, f)

# load and save JSON files
class YamlRepository():
    @staticmethod
    def load(config_path: str):
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(path, "r") as f:
            return yaml.safe_load(f)

    @staticmethod
    def save(data, file_path: str):
        path = Path(file_path)
        with open(path, "w") as f:
            yaml.safe_dump(data, f)
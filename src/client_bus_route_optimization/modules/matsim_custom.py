"""
Custom MATSim Scenario Module

This module provides functionality to run custom MATSim scenarios with user-defined
configurations, names, and paths. It's separate from the main matsim.py to allow
easy modification or removal when not needed.

Features:
- Build vehicle schedules with custom configurations
- Generate config files with custom names (instead of worker_id)
- Run complete custom scenarios with A_pop and P_pop configurations
"""

from client_bus_route_optimization.utils.file_handler import YamlRepository, JsonRepository
from client_bus_route_optimization.modules.matsim import (
    remove_all_existing_bus_services,
    add_line_to_services,
    change_type_of_bus
)
from pathlib import Path
import logging

logging.getLogger(__name__)

try:
    import genet
    logging.info("Genet module imported successfully in matsim_custom.")
except ImportError:
    logging.error("Genet module not found. Please ensure it is installed.")
    genet = None


def build_config_file_custom(name, template_path, output):
    """Build config file with custom name instead of worker_id.
    
    Args:
        name: Custom name to replace {{WORKER}} placeholder
        template_path: Path to the template config file
        output: Path where the generated config will be saved
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    content = template_path.read_text(encoding="utf-8")

    # Replace placeholder with custom name
    content = content.replace("{{WORKER}}", name)

    # Write output
    output.write_text(content, encoding="utf-8")

    logging.info(f"✔ Generated config: {output}")


def build_vehicle_schedule_custom(config_data, output_path, config_path):
    """Build vehicle schedule for custom scenario.
    
    Args:
        config_data: Dict containing A_pop and P_pop arrays
        output_path: Path where to save the generated files
        config_path: Path to main config YAML file
    
    Returns:
        Path to the output directory
    """
    # load config
    config = YamlRepository.load(config_path)

    # load route set
    terminal_pairs_set = JsonRepository.load(config["terminal_pairs_path"])
    
    # load A_pop, P_pop
    A_pop = config_data.get("A_pop", [])
    P_pop = config_data.get("P_pop", [])

    network_path =  config["network_path"]
    schedule_path = config["schedule_path"]
    vehicle_path = config["vehicle_path"]
    coordinated_system = config["coordinate_system"]

    n = genet.read_matsim(
        path_to_network=network_path, epsg=coordinated_system, path_to_schedule=schedule_path,
        path_to_vehicles=vehicle_path
    )

    # remove existing bus services
    remove_all_existing_bus_services(n)

    # add new line to services
    for i, line_idx in enumerate(P_pop):
        if line_idx == 0:
            continue
        line = terminal_pairs_set[i]["lines"][line_idx - 1]
        # add bus config to service (schedule)
        add_line_to_services(n,line)

    # change type of bus
    change_type_of_bus(n,config["type_of_bus"])

    # write to matsim
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    n.write_to_matsim(output_path)
    
    logging.info(f"✔ Generated vehicle schedule at: {output_path}")
    
    return output_path


def run_matsim_custom(config, input_path, output_path, name):
    """Run MATSim simulation for custom scenario.
    
    Args:
        config: Main config dictionary
        input_path: Path to input files (network, schedule, config)
        output_path: Path to save output files
        name: Custom scenario name for logging
    """
    import subprocess
    import shutil
    import os
    import stat
    import time
    
    def remove_readonly(func, path, exc_info):
        """Helper to remove read-only files on Windows."""
        os.chmod(path, stat.S_IWRITE)
        func(path)
    
    def force_delete_folder(folder_path):
        """Delete folder with retry mechanism."""
        if not os.path.exists(folder_path):
            return
        
        max_retries = 10
        for i in range(max_retries):
            try:
                shutil.rmtree(folder_path, onerror=remove_readonly)
                logging.info(f"✔ Deleted folder: {folder_path}")
                break
            except OSError as e:
                if i < max_retries - 1:
                    logging.warning(f"⚠️ Cannot delete {folder_path} (Attempt {i + 1}). Waiting 1s... Error: {e.strerror}")
                    time.sleep(1)
                else:
                    logging.error(f"❌ Critical error: Cannot delete {folder_path} after {max_retries} attempts.")
                    raise e
    
    # Clean output folder
    force_delete_folder(output_path)
    
    # Create eval directory for MATSim output
    eval_dir = Path(output_path) / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"✔ Created eval directory: {eval_dir}")
    
    # Run MATSim
    cmd = [
        "java",
        "--add-opens=java.base/java.nio=ALL-UNNAMED",
        "-jar", config["matsim_path"], "sim",
        "--cfg", str(Path(input_path) / "config_eval.yaml"),
        "--matsim-cfg", str(Path(input_path) / "config.xml"),
        "--out", str(Path(output_path) / "eval" / "score.bin"),
        "--log-file", f"logs/matsim/{name}.log",
        "--signature", name
    ]
    
    logging.info(f"🚀 Running MATSim for scenario: {name}")
    subprocess.run(cmd)
    logging.info(f"✔ MATSim simulation completed for: {name}")


def read_score_custom(output_path):
    """Read score from binary file.
    
    Args:
        output_path: Path to output directory containing eval/score.bin
        
    Returns:
        float: The score value
    """
    import struct
    
    score_file = Path(output_path) / "eval" / "score.bin"
    with open(score_file, "rb") as f:
        data = f.read(64)
    score = struct.unpack('>d', data)[0]
    return score


def run_custom_scenario(config_data, name, config_path="config/config.yaml", 
                       input_base_path="data/input", 
                       output_base_path="data/output"):
    """Run custom MATSim scenario with custom configuration.
    
    This is the main function to run a complete custom scenario. It will:
    1. Build the vehicle schedule based on A_pop and P_pop
    2. Generate MATSim config files
    3. Generate evaluation config files
    4. Run MATSim simulation
    5. Return the score
    
    Args:
        config_data: Dict containing A_pop and P_pop arrays
        name: Custom name for this scenario (replaces worker_id)
        config_path: Path to main config YAML file (default: "config/config.yaml")
        input_base_path: Base path for input files (default: "data/input")
        output_base_path: Base path for output files (default: "data/output")
    
    Returns:
        float: The simulation score
        
    Example:
        >>> custom_config = {
        ...     "A_pop": [0, 1, 0, 0, ...],
        ...     "P_pop": [0, 1, 0, 0, ...]
        ... }
        >>> score = run_custom_scenario(
        ...     config_data=custom_config,
        ...     name="my_scenario_v1",
        ...     config_path="config/config.yaml"
        ... )
        >>> print(f"Score: {score}")
    """
    # Create paths
    input_path = Path(input_base_path) / name
    output_path = Path(output_base_path) / name
    
    # Step 1: Build vehicle schedule
    logging.info(f"Step 1/4: Building vehicle schedule for '{name}'")
    build_vehicle_schedule_custom(config_data, input_path, config_path)
    
    # Load config for template paths
    config = YamlRepository.load(config_path)
    
    # Step 2: Build config file for MATSim
    logging.info(f"Step 2/4: Building MATSim config files for '{name}'")
    template_config_path = Path(config["config_path"])
    new_config_path = input_path / "config.xml"
    build_config_file_custom(name, template_config_path, new_config_path)
    
    # Step 3: Build config evaluation
    template_config_eval = Path(config["config_eval_path"])
    new_config_eval_path = input_path / "config_eval.yaml"
    build_config_file_custom(name, template_config_eval, new_config_eval_path)
    
    # Step 4: Run MATSim simulation
    logging.info(f"Step 3/4: Running MATSim simulation for '{name}'")
    run_matsim_custom(config, input_path, output_path, name)
    
    # Step 5: Read and return score
    logging.info(f"Step 4/4: Reading score for '{name}'")
    score = read_score_custom(output_path)
    
    logging.info(f"✔ Custom scenario '{name}' completed successfully")
    logging.info(f"✔ Final score: {score}")
    
    return score


if __name__ == "__main__":
    """Test custom scenario functionality"""
    
    # print("=" * 70)
    # print("BASE LINE")
    # print("=" * 70)
    
    # # Example custom configuration
    # baseline_config = {
    #     "A_pop": [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    #     "P_pop": [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    # }
    
    # # Test 1: Run custom scenario and get score
    # print("\nTest 1: Run custom scenario with name 'test_scenario_v1'")
    # print("-" * 70)
    # try:
    #     score = run_custom_scenario(
    #         config_data=baseline_config,
    #         name="base_line",
    #         config_path="config/config.yaml"
    #     )
        
    #     print(f"✓ Simulation completed successfully!")
    #     print(f"✓ Final Score: {score}")
            
    # except Exception as e:
    #     print(f"✗ Error: {e}")
    #     import traceback
    #     traceback.print_exc()
    
    # Test 2: Another scenario with different name
    pbil_config = {
        "A_pop": [0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
       0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0],
        "P_pop": [0, 0, 2, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
       0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
       0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0]
    }
    print("\n" + "=" * 70)
    print("Test 2: Run PBIL")
    print("-" * 70)
    try:
        score = run_custom_scenario(
            config_data=pbil_config,
            name="pbil_optimization_v2_gen4",
            config_path="config/config.yaml"
        )
        
        print(f"✓ Simulation completed successfully!")
        print(f"✓ Final Score: {score}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("Testing Complete!")
    print("=" * 70)

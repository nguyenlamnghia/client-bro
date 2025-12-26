import logging
import os
from pathlib import Path

import typer
from multiprocessing import Process
from client_bus_route_optimization.modules.worker_node import WorkerNode
from client_bus_route_optimization.utils.logger import setup_logging
from client_bus_route_optimization.utils.file_handler import YamlRepository

setup_logging()

app = typer.Typer(help="Run Worker Node for Bus Route Optimization")

def run_worker(host,i):
    setup_logging()

    # load config
    config_path = Path("config/config.yaml")
    config = YamlRepository.load(config_path.as_posix())

    input_path = Path(config["workers_input_path"]) / f"worker{i}"
    output_path = Path(config["workers_output_path"]) / f"worker{i}"

    # Mkdir foler for worker if not exists
    os.makedirs(input_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)

    worker = WorkerNode(host,i)
    worker.start()

@app.command("start", help="")
def start(
        host: str = typer.Argument("localhost", help="Địa chỉ host của master node"),
        process : int = typer.Argument(1, help="Số lượng process worker")
):

    # proceed to start worker nodes
    processes = []

    for i in range(process):
        p = Process(target=run_worker, args=(host,i,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

def main():
    app()

if __name__ == "__main__":
    main()
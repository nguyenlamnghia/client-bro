import logging

import typer
from multiprocessing import Process
from client_bus_route_optimization.modules.worker_node import WorkerNode
from client_bus_route_optimization.utils.logger import setup_logging

setup_logging()

try:
    import genet
    logging.info("Genet module imported successfully.")
except ImportError:
    logging.error("Genet module not found. Please ensure it is installed.")
    genet = None

app = typer.Typer(help="Run Worker Node for Bus Route Optimization")

def run_worker(host):
    setup_logging()
    worker = WorkerNode(host)
    worker.start()

@app.command("start", help="")
def start(
        host: str = typer.Argument("localhost", help="Địa chỉ host của master node"),
        process : int = typer.Argument(1, help="Số lượng process worker")
):

    # proceed to start worker nodes
    processes = []

    for _ in range(process):
        p = Process(target=run_worker, args=(host,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

def main():
    app()

if __name__ == "__main__":
    main()
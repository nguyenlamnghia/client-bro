import logging
import os
import time
import threading
from pathlib import Path

import typer
from multiprocessing import Process
from client_bus_route_optimization.modules.worker_node import WorkerNode
from client_bus_route_optimization.utils.logger import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

# Default paths - tương ứng với giá trị mặc định trong scenario config
DEFAULT_WORKERS_INPUT_PATH = "data/input/worker"
DEFAULT_WORKERS_OUTPUT_PATH = "data/output"

# Escalating restart delays (phút). Mỗi lần có process lỗi, dùng delay tiếp theo.
# Reset về đầu nếu không có lỗi trong STABLE_RESET_TIME giây.
RESTART_DELAYS_MINUTES = [5, 15, 30, 45, 60, 90, 120]
STABLE_RESET_TIME = 3600  # 1 tiếng không lỗi → reset delay về 5 phút

app = typer.Typer(help="Run Worker Node for Bus Route Optimization")

def run_worker(host, i):
    setup_logging()

    input_path = Path(DEFAULT_WORKERS_INPUT_PATH) / f"worker{i}"
    output_path = Path(DEFAULT_WORKERS_OUTPUT_PATH) / f"worker{i}"

    # Mkdir folder for worker if not exists
    os.makedirs(input_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)

    worker = WorkerNode(host, i)
    worker.start()


def start_worker(host, worker_id, processes):
    """Khởi động một worker process."""
    p = Process(target=run_worker, args=(host, worker_id,))
    p.start()
    processes[worker_id] = p
    logger.info(f"Worker {worker_id} đã khởi động (PID: {p.pid})")
    return p


def stop_worker(worker_id, processes):
    """Dừng một worker process."""
    p = processes.get(worker_id)
    if p and p.is_alive():
        logger.info(f"Đang dừng Worker {worker_id} (PID: {p.pid})...")
        p.terminate()
        p.join(timeout=10)
        if p.is_alive():
            logger.warning(f"Worker {worker_id} không dừng được, kill...")
            p.kill()
            p.join(timeout=5)


def stop_all_workers(processes):
    """Dừng tất cả worker processes đang chạy."""
    for worker_id in list(processes.keys()):
        stop_worker(worker_id, processes)


def delayed_restart_worker(host, worker_id, delay_minutes, processes, pending_restarts):
    """Chờ delay rồi restart worker. Chạy trên thread riêng."""
    logger.info(
        f"Worker {worker_id} sẽ được restart sau {delay_minutes} phút..."
    )
    time.sleep(delay_minutes * 60)

    # Restart worker
    logger.info(f"Đang restart Worker {worker_id} sau {delay_minutes} phút chờ...")
    start_worker(host, worker_id, processes)

    # Xóa khỏi danh sách pending
    pending_restarts.discard(worker_id)


@app.command("start", help="")
def start(
        host: str = typer.Argument("localhost", help="Địa chỉ host của master node"),
        process: int = typer.Argument(1, help="Số lượng process worker")
):
    delay_index = 0  # Vị trí hiện tại trong RESTART_DELAYS_MINUTES (dùng chung cho tất cả worker)
    last_failure_time = None  # Thời điểm lần lỗi gần nhất

    processes = {}  # {worker_id: Process}
    pending_restarts = set()  # worker_ids đang chờ restart

    # Khởi động tất cả worker
    for i in range(process):
        start_worker(host, i, processes)
    logger.info(f"Đã khởi động {process} worker(s). Bắt đầu giám sát...")

    try:
        while True:
            # Reset delay nếu không có lỗi trong STABLE_RESET_TIME
            if last_failure_time and delay_index > 0:
                stable_duration = time.time() - last_failure_time
                if stable_duration >= STABLE_RESET_TIME:
                    logger.info(
                        f"Không có lỗi trong {STABLE_RESET_TIME // 60} phút. "
                        f"Reset delay về {RESTART_DELAYS_MINUTES[0]} phút."
                    )
                    delay_index = 0
                    last_failure_time = None

            # Kiểm tra từng worker
            for worker_id, p in list(processes.items()):
                if p.is_alive() or worker_id in pending_restarts:
                    continue

                p.join()

                if p.exitcode == 0:
                    # Worker thoát bình thường (KeyboardInterrupt), không restart
                    logger.info(f"Worker {worker_id} thoát bình thường (exit code 0). Không restart.")
                    del processes[worker_id]
                    continue

                # Worker lỗi → lấy delay hiện tại và schedule restart
                current_delay = RESTART_DELAYS_MINUTES[
                    min(delay_index, len(RESTART_DELAYS_MINUTES) - 1)
                ]

                logger.error(
                    f"Worker {worker_id} thoát với exit code {p.exitcode}. "
                    f"Chờ {current_delay} phút trước khi restart "
                    f"(delay level {delay_index + 1}/{len(RESTART_DELAYS_MINUTES)})."
                )

                # Đánh dấu đang chờ restart
                pending_restarts.add(worker_id)

                # Tăng delay cho lần lỗi tiếp theo
                last_failure_time = time.time()
                if delay_index < len(RESTART_DELAYS_MINUTES) - 1:
                    delay_index += 1

                # Restart trên thread riêng để không block monitoring các worker khác
                restart_thread = threading.Thread(
                    target=delayed_restart_worker,
                    args=(host, worker_id, current_delay, processes, pending_restarts),
                    daemon=True,
                )
                restart_thread.start()

            # Thoát nếu tất cả worker đã thoát bình thường và không có pending restart
            active_or_pending = any(
                p.is_alive() for p in processes.values()
            ) or len(pending_restarts) > 0
            if not active_or_pending and len(processes) == 0:
                logger.info("Tất cả worker đã thoát bình thường. Kết thúc.")
                break

            # Kiểm tra mỗi 5 giây
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("Nhận tín hiệu dừng từ người dùng. Đang dừng tất cả worker...")
        pending_restarts.clear()  # Hủy các pending restart
        stop_all_workers(processes)
        logger.info("Đã dừng tất cả worker.")

def main():
    app()

if __name__ == "__main__":
    main()
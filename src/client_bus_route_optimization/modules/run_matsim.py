import logging
import os
import shutil
import stat
import struct
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Thời gian chờ tối đa để score.bin được tạo sau khi MATSim kết thúc
SCORE_WAIT_TIMEOUT = 60  # seconds
SCORE_WAIT_INTERVAL = 0.5  # seconds


def remove_readonly(func, path, exc_info):
    """
    Hàm callback giúp shutil.rmtree xóa được file Read-Only trên Windows.
    Nó sẽ cấp quyền ghi (S_IWRITE) rồi thử xóa lại.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def force_delete_folder(folder_path):
    """
    Xóa folder an toàn với cơ chế thử lại (Retry) và xử lý Read-only.
    """
    folder_path = Path(folder_path)

    if not folder_path.exists():
        return

    max_retries = 10
    for i in range(max_retries):
        try:
            shutil.rmtree(folder_path, onerror=remove_readonly)
            logger.info(f"✔ Đã xóa thư mục: {folder_path}")
            break
        except OSError as e:
            if i < max_retries - 1:
                logger.info(
                    f"⚠️ Không thể xóa {folder_path} (Lần {i + 1}). "
                    f"Đang chờ 1s... Lỗi: {e.strerror}"
                )
                time.sleep(1)
            else:
                logger.info(
                    f"❌ Lỗi nghiêm trọng: Không thể xóa {folder_path} sau {max_retries} lần thử."
                )
                raise e


def ensure_eval_dir(config, worker_id) -> Path:
    """
    Dọn sạch và đảm bảo thư mục output/eval tồn tại trước khi chạy MATSim.
    """
    eval_dir = Path(config["workers_output_path"]) / f"worker{worker_id}" / "eval"
    force_delete_folder(eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)
    return eval_dir


def ensure_log_dir() -> Path:
    """
    Đảm bảo thư mục log cho MATSim tồn tại.
    """
    log_dir = Path("logs/matsim")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def wait_for_score(score_path: Path, timeout: int = SCORE_WAIT_TIMEOUT) -> None:
    """
    Chờ tới khi score.bin xuất hiện, ném lỗi nếu hết thời gian.
    """
    start = time.time()
    while time.time() - start < timeout:
        if score_path.exists():
            return
        time.sleep(SCORE_WAIT_INTERVAL)
    raise FileNotFoundError(f"score.bin không được tạo sau {timeout}s: {score_path}")


def read_score(score_path: Path) -> float:
    with score_path.open("rb") as f:
        data = f.read(64)
    return struct.unpack(">d", data)[0]


def run_matsim(config, worker_id, score_path: Path, log_dir: Path):
    cmd = [
        "java",
        "--add-opens=java.base/java.nio=ALL-UNNAMED",
        "-jar",
        config["matsim_path"],
        "--cfg",
        f"{config['workers_input_path']}/worker{worker_id}/config_eval.yaml",
        "--matsim-cfg",
        f"{config['workers_input_path']}/worker{worker_id}/config.xml",
        "--out",
        score_path.as_posix(),
        "--log-file",
        (log_dir / f"worker{worker_id}.log").as_posix(),
        "--signature",
        f"worker{worker_id}",
    ]

    completed = subprocess.run(cmd, capture_output=True, text=True)

    if completed.returncode != 0:
        logger.error(
            "MATSim exit code %s for worker %s. stdout: %s stderr: %s",
            completed.returncode,
            worker_id,
            completed.stdout,
            completed.stderr,
        )
        raise RuntimeError(f"MATSim failed for worker {worker_id} (exit {completed.returncode})")


def run_worker_task(config, worker_id):
    eval_dir = ensure_eval_dir(config, worker_id)
    log_dir = ensure_log_dir()
    score_path = eval_dir / "score.bin"

    run_matsim(config, worker_id, score_path, log_dir)
    wait_for_score(score_path)
    return read_score(score_path)

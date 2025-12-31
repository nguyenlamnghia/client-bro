import subprocess
import time
import psutil  # pip install psutil
import os

import os
import shutil
import stat
import time
import logging

logger = logging.getLogger(__name__)
def remove_readonly(func, path, exc_info):
    """
    Hàm callback giúp shutil.rmtree xóa được file Read-Only trên Windows.
    Nó sẽ cấp quyền ghi (S_IWRITE) rồi thử xóa lại.
    """
    # Clear bộ nhớ đệm stat để đảm bảo quyền truy cập được cập nhật
    os.chmod(path, stat.S_IWRITE)
    # Thử gọi lại hàm xóa (unlink hoặc rmdir)
    func(path)

def force_delete_folder(folder_path):
    """
    Xóa folder an toàn với cơ chế thử lại (Retry) và xử lý Read-only.
    """
    if not os.path.exists(folder_path):
        return

    max_retries = 10
    for i in range(max_retries):
        try:
            # onerror=remove_readonly: Tự động sửa lỗi Read-only
            shutil.rmtree(folder_path, onerror=remove_readonly)
            logger.info(f"✔ Đã xóa thư mục: {folder_path}")
            break  # Xóa thành công thì thoát vòng lặp
        except OSError as e:
            # Nếu vẫn lỗi (thường là do file đang bị Java lock)
            if i < max_retries - 1:
                logger.info(f"⚠️ Không thể xóa {folder_path} (Lần {i + 1}). Đang chờ 1s... Lỗi: {e.strerror}")
                time.sleep(1)  # Chờ 1 giây để file được nhả ra
            else:
                logger.info(f"❌ Lỗi nghiêm trọng: Không thể xóa {folder_path} sau {max_retries} lần thử.")
                raise e  # Ném lỗi ra để dừng chương trình nếu cần

def read_score(config, id):
    import struct
    with open(f"{config['workers_output_path']}/worker{id}/eval/score.bin", "rb") as f:
        data = f.read(64)
    score = struct.unpack('>d', data)[0]
    return score

def run_matsim(config, id):
    cmd = [
        "java",
        "--add-opens=java.base/java.nio=ALL-UNNAMED",
        "-jar", config["matsim_path"],
        "--cfg", f"{config['workers_input_path']}/worker{id}/config_eval.yaml",
        "--matsim-cfg", f"{config['workers_input_path']}/worker{id}/config.xml",
        "--out", f"{config['workers_output_path']}/worker{id}/eval/score.bin",
        "--log-file", f"logs/matsim/worker{id}.log",
        "--signature", f"worker{id}"
    ]

    # Gọi hàm thay vì subprocess.run(cmd)
    # run_matsim_safe(cmd)
    subprocess.run(cmd)

def run_worker_task(config, id):
    force_delete_folder(f"{config['workers_output_path']}/worker{id}/")
    run_matsim(config, id)
    return read_score(config, id)

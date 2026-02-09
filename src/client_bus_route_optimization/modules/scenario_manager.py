import os
import zipfile
import logging
import urllib.request
import shutil
import time
from pathlib import Path
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

SCENARIOS_BASE_DIR = Path("data/input/scenarios")


def ensure_scenario(host: str, scenario: str) -> Path:
    """
    Kiểm tra xem scenario đã tồn tại trong thư mục input/scenarios chưa.
    Nếu chưa, tải từ server và giải nén.
    Sử dụng file lock để tránh race condition khi nhiều process cùng download.

    :param host: Địa chỉ host của server (dùng để download scenario)
    :param scenario: Tên scenario cần kiểm tra/download
    :return: Đường dẫn tới thư mục scenario
    """
    scenario_dir = SCENARIOS_BASE_DIR / scenario

    # Kiểm tra nhanh trước khi acquire lock (tránh lock không cần thiết)
    if scenario_dir.exists() and any(scenario_dir.iterdir()):
        logger.info(f"Scenario '{scenario}' đã tồn tại tại {scenario_dir}")
        return scenario_dir

    # Tạo thư mục scenarios nếu chưa tồn tại
    os.makedirs(SCENARIOS_BASE_DIR, exist_ok=True)

    # Sử dụng file lock để đảm bảo chỉ 1 process download tại 1 thời điểm
    lock_path = SCENARIOS_BASE_DIR / f"{scenario}.lock"
    lock = FileLock(str(lock_path), timeout=300)  # timeout 5 phút

    try:
        with lock:
            # Kiểm tra lại sau khi acquire lock (process khác có thể đã download xong)
            if scenario_dir.exists() and any(scenario_dir.iterdir()):
                logger.info(f"Scenario '{scenario}' đã tồn tại tại {scenario_dir}")
                return scenario_dir

            # Download zip từ server
            url = f"http://{host}:8080/{scenario}/{scenario}.zip"
            zip_path = SCENARIOS_BASE_DIR / f"{scenario}.zip"

            logger.info(f"Đang tải scenario '{scenario}' từ {url} ...")

            try:
                urllib.request.urlretrieve(url, str(zip_path))
                logger.info(f"Đã tải xong scenario zip: {zip_path}")
            except Exception as e:
                logger.error(f"Không thể tải scenario '{scenario}' từ {url}: {e}")
                raise RuntimeError(f"Không thể tải scenario '{scenario}' từ {url}") from e

            # Giải nén zip
            try:
                temp_extract_dir = SCENARIOS_BASE_DIR / f"_temp_{scenario}"
                os.makedirs(temp_extract_dir, exist_ok=True)

                with zipfile.ZipFile(str(zip_path), 'r') as zip_ref:
                    zip_ref.extractall(str(temp_extract_dir))

                logger.info(f"Đã giải nén scenario zip vào thư mục tạm: {temp_extract_dir}")

                # Kiểm tra xem bên trong zip có folder con trùng tên scenario không
                extracted_items = list(temp_extract_dir.iterdir())

                if (len(extracted_items) == 1
                        and extracted_items[0].is_dir()
                        and extracted_items[0].name == scenario):
                    # Zip chứa folder con trùng tên -> di chuyển folder con ra ngoài
                    shutil.move(str(extracted_items[0]), str(scenario_dir))
                else:
                    # Zip không chứa folder con trùng tên -> di chuyển toàn bộ nội dung
                    os.makedirs(scenario_dir, exist_ok=True)
                    for item in extracted_items:
                        dest = scenario_dir / item.name
                        shutil.move(str(item), str(dest))

                # Xóa thư mục tạm
                if temp_extract_dir.exists():
                    shutil.rmtree(str(temp_extract_dir), ignore_errors=True)

                logger.info(f"Đã giải nén scenario vào {scenario_dir}")

            except zipfile.BadZipFile as e:
                logger.error(f"File zip không hợp lệ: {zip_path}: {e}")
                raise RuntimeError(f"File zip scenario '{scenario}' không hợp lệ") from e
            finally:
                # Xóa file zip sau khi giải nén
                if zip_path.exists():
                    os.remove(zip_path)
                    logger.info(f"Đã xóa file zip: {zip_path}")

    except Timeout:
        logger.error(f"Timeout khi chờ lock để download scenario '{scenario}'")
        raise RuntimeError(f"Timeout khi chờ download scenario '{scenario}'")

    return scenario_dir

import pika, json, random, time, logging, os
from logging.handlers import RotatingFileHandler
import socket
import uuid
from datetime import datetime
import subprocess

from client_bus_route_optimization.modules.matsim import build_vehicle_schedule
from client_bus_route_optimization.utils.file_handler import YamlRepository
from client_bus_route_optimization.modules.run_matsim import run_worker_task

def build_log_path(base_log_path: str):
    """
    base_log_path/
        DD-MM-YYYY/
            HHMMSS/
    """
    now = datetime.now()

    date_dir = now.strftime("%d-%m-%Y")
    time_dir = now.strftime("%H%M%S")
    full_log_path = os.path.join(
        base_log_path,
        date_dir,
        time_dir
    )

    os.makedirs(full_log_path, exist_ok=True)
    return full_log_path


# tạo ra thư mục log_pth/DDMMYY/HHMMSS/log_file_name
class DistributeSystemWorkerLogger:
    def __init__(self, process_id: int, log_path: str, id: int):
        log_path = build_log_path(log_path)

        # Tạo log cho từng máy
        hostname = socket.gethostname()  # Lấy tên máy (Terminal)
        ip_addr = socket.gethostbyname(hostname)  # Lấy IP
        self.node_id = f"Worker:{hostname}-IP:{ip_addr}-Process:{process_id}"
        log_format = logging.Formatter(f"%(asctime)s  [{self.node_id}]  [%(levelname)s] : %(message)s")

        self.DSLogger = logging.getLogger(f"{self.node_id}")
        self.DSLogger.setLevel(logging.DEBUG)

        file_log_handler = RotatingFileHandler(os.path.join(log_path, f"worker_process_{id}_logs.log"),
                                               maxBytes=10 * 1024 * 1024,
                                               backupCount=5,
                                               encoding='utf-8')
        file_log_handler.setLevel(logging.DEBUG)
        file_log_handler.setFormatter(log_format)

        console_log_handler = logging.StreamHandler()
        console_log_handler.setLevel(logging.DEBUG)
        console_log_handler.setFormatter(log_format)

        self.DSLogger.addHandler(file_log_handler)
        self.DSLogger.addHandler(console_log_handler)

        # Tạo log tổng hơp
        all_logs = RotatingFileHandler(
            os.path.join(log_path, f"worker_process_{id}_full_logs.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )

        all_logs.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        all_logs.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(all_logs)


class WorkerNode:
    def connect_rabbitmq(self, host):
        RETRY_DELAYS = [5, 10, 20, 40, 80]
        last_exception = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            try:
                self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=host, heartbeat=600))
                self.channel = self.connection.channel()

                self.logger.DSLogger.info(f"Kết nối RabbitMQ thành công tới host {host}")
                return

            except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError,
                    pika.exceptions.ConnectionClosedByBroker) as e:
                last_exception = e
                self.logger.DSLogger.warning(
                    f"[Retry {attempt}/5] Không kết nối được RabbitMQ ({e}). "
                    f"Thử lại sau {delay}s..."
                )
                time.sleep(delay)

        self.logger.DSLogger.error(
            f"Không thể kết nối RabbitMQ tới host {host} sau 5 lần retry"
        )
        raise last_exception

    def __init__(self, host, id, log_path: str = "logs"):
        os.makedirs(log_path, exist_ok=True)  # Neu folder ton tai thi bo qua, chua ton tai thi tao

        self.logger = DistributeSystemWorkerLogger(process_id=id, log_path=log_path, id=id)
        self.logger.DSLogger.info("DANG KHOI TAO WORKER.......")

        self.id = id
        self.connect_rabbitmq(host)

        self.channel.queue_declare(queue="task_queue", durable=True)
        self.channel.queue_declare(queue="result_queue", durable=True)
        self.logger.DSLogger.info(f"Khoi tao than cong cac queue")

        self.logger.DSLogger.info("DA KHOI TAO XONG WORKER")

    def run_task(self, msg: str) -> str:
        """
        Lay data de tao ra transit schedule, sau do chay matsim

        :param msg: data dau vao de tao nen file transit schedule
        :return: dict chua ket qua cua lan chay nay {id : result}
        :rtype: str
        """

        input = json.loads(msg)
        build_vehicle_schedule(input, self.id)

        config = YamlRepository.load("config/config.yaml")

        # run matsim
        # add minus to minimize score
        score = run_worker_task(config, self.id)        # remove minus to new eval

        output_dict = {"id": input["id"], "result": score}
        output = json.dumps(output_dict)
        return output

    def cb_on_task(self, channel, method, properties, body):
        data = body.decode()
        task_id = json.loads(data)["id"]
        self.logger.DSLogger.debug(f"TASK_ID {task_id} Worker consume task tu Server")

        result: str = self.run_task(data)
        self.logger.DSLogger.debug(f"TASK_ID {task_id} Worker da tao ra result cho task")

        self.channel.basic_publish(exchange="", routing_key="result_queue", body=result)
        self.channel.basic_ack(delivery_tag=method.delivery_tag)
        self.logger.DSLogger.debug(f"TASK_ID {task_id} Worker publish result cua task len Server")

    def start(self):
        try:
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(queue="task_queue", on_message_callback=self.cb_on_task)
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.logger.DSLogger.info("DUNG WORKER CUONG CHE TU NGUOI DUNG")


if __name__ == "__main__":
    host = "localhost"
    worker = WorkerNode(host=host)
    worker.start()
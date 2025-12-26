import pika, json, random, time, logging
from logging.handlers import RotatingFileHandler
import socket
import uuid
from datetime import datetime
import subprocess

from client_bus_route_optimization.modules.matsim import build_vehicle_schedule
from client_bus_route_optimization.utils.file_handler import YamlRepository


class WorkerNode:
    def setup_logger(self):
        # --- BƯỚC TẠO ĐỊNH DANH NODE ---
        hostname = socket.gethostname()  # Lấy tên máy (Terminal)
        ip_addr = socket.gethostbyname(hostname)  # Lấy IP
        session_id = datetime.now().strftime("%H%M%S")  # Mã phiên chạy theo giờ phút giây
        self.node_id = f"Worker-{hostname}-SESSION-{session_id}-SOCKET-{ip_addr}"
        self.logger = logging.getLogger(f"{self.node_id}")

        # self.logger.setLevel(logging.DEBUG)
        # file_format = logging.Formatter(f'%(asctime)s - [{self.node_id}] - %(levelname)s - %(message)s')
        #
        # log_filename = f"log_worker_{self.node_id}.log"
        # all_log_handler = RotatingFileHandler(log_filename, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        # all_log_handler.setLevel(logging.DEBUG)
        # all_log_handler.setFormatter(file_format)
        #
        # console_log = logging.StreamHandler()
        # console_log.setLevel(logging.DEBUG)
        # console_log.setFormatter(file_format)
        #
        # self.logger.addHandler(all_log_handler)
        # self.logger.addHandler(console_log)

    def __init__(self, host, id):
        self.id = id
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host))
        self.setup_dict: dict = {}
        self.channel = self.connection.channel()
        self.private_setup_queue = self.channel.queue_declare(queue="", exclusive=True)
        self.name_private_setup_queue = self.private_setup_queue.method.queue

        self.channel.queue_declare(queue="task_queue", durable=True)
        self.channel.queue_declare(queue="request_queue", durable=True)
        self.channel.queue_declare(queue="result_queue", durable=True)
        self.setup_logger()
        self.logger.info("==================================PHIEN CHAY MOI===================================")
        self.logger.info("Da khoi tao xong")


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

        # create a empty result file
        with open(f"{config["workers_output_path"]}/worker{self.id}/result.txt", 'w') as f:
            f.write("")

        subprocess.run([
            "java",
            "-jar",
            config["matsim_path"],
            f"--config-path={config["workers_input_path"]}/worker{self.id}/config.xml",
            f"--result-txt-path={config["workers_output_path"]}/worker{self.id}/result.txt"
        ])

        # read result
        with open(f"{config['workers_output_path']}/worker{self.id}/result.txt", 'r') as f:
            score = float(f.read().strip())

        output_dict = {"id": input["id"], "result": score}
        output = json.dumps(output_dict)
        return output

        # time.sleep(0.5)
        # output_dict = {"id": input["id"], "result": random.randint(1, 100)}
        # output = json.dumps(output_dict)
        # return output

    def cb_on_task(self, channel, method, properties, body):
        self.logger.info(f" Da nhan data : {body.decode()}")
        data = body.decode()
        result: str = self.run_task(data)
        self.logger.info(" Da chay xong matsim, day ket qua len result_queue")
        self.channel.basic_publish(exchange="", routing_key="result_queue", body=result)
        self.channel.basic_ack(delivery_tag=method.delivery_tag)

    def setup(self):
        """
        Set up, luu cac file config o day
        """
        self.channel.basic_publish(exchange="", routing_key="request_queue",
                                   properties=pika.BasicProperties(reply_to=self.name_private_setup_queue),
                                   body="i need setup urls")
        for meth, props, body in self.channel.consume(queue=self.name_private_setup_queue, auto_ack=True):
            self.setup_dict = json.loads(body.decode())
            print(f"[x] Da nhan duoc setup: {self.setup_dict}")
            break
        self.logger.info("Da cau hinh xong cac file set up")

    def start(self):
        # self.setup()
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue="task_queue", on_message_callback=self.cb_on_task)
        self.channel.start_consuming()


if __name__ == "__main__":
    host = "localhost"
    worker = WorkerNode(host=host)
    worker.start()
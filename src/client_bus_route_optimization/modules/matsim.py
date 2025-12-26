
from client_bus_route_optimization.utils.file_handler import YamlRepository, PklRepository
from pathlib import Path
import logging
import xml.etree.ElementTree as ET

logging.getLogger(__name__)

try:
    import genet
    logging.info("Genet module imported successfully.")
except ImportError:
    logging.error("Genet module not found. Please ensure it is installed.")
    genet = None

def build_config_file(worker_id, template_path, output):

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    content = template_path.read_text(encoding="utf-8")

    # Replace placeholder
    content = content.replace("{{WORKER}}", f"worker{worker_id}")

    # Write output
    output.write_text(content, encoding="utf-8")

    logging.info(f"✔ Generated config: {output}")

def change_type_of_bus(n,type_of_bus):
    # change type of vehicles
    vehicle_changed = 0
    for veh_attrs in n.schedule.vehicles.values():
        if veh_attrs['type'] == 'bus':
            vehicle_changed += 1
            veh_attrs['type'] = type_of_bus
    # print(f"Changed {vehicle_changed} vehicle type to", init_config["type_of_bus"])

def remove_all_existing_bus_services(n):
    # Remove existing pt and bus services from schedule
    list_pt_service = n.schedule.services_on_modal_condition('pt')
    list_bus_service = n.schedule.services_on_modal_condition('bus')
    list_pt_bus_service = list(set(list_pt_service + list_bus_service))
    try:
        n.schedule.remove_services(list_pt_bus_service)
    except UnboundLocalError as e:
        print("No existing bus services to remove.")

def add_line_to_services(n,line):
    route_objs = []
    for route_data in line["routes"]:
        route_obj = genet.Route(
            route_short_name=route_data["short_name"],
            mode='bus',
            headway_spec=route_data["headway_spec"],
            arrival_offsets=route_data["arrival_offsets"],
            departure_offsets=route_data["departure_offsets"],
            await_departure=route_data["await_departure"],
            id=route_data["route_id"],
            stops=[n.schedule.stop(stop_id) for stop_id in route_data["stops"]],
            network_links=route_data["routes"],
        )
        route_objs.append(route_obj)
    service_obj = genet.Service(
        id = line["line_id"],
        routes = route_objs,
        name = line["line_id"]
    )
    n.schedule.add_service(service_obj)

def save_matsim(n, output_path):
    n.write_to_matsim(output_path)

def build_vehicle_schedule(data, worker_id):
    # load config
    config = YamlRepository.load("config/config.yaml")

    # load route set
    route_set = PklRepository.load(config["route_set_path"])
    print(data)
    print(type(data))
    # load A_pop, P_pop
    A_pop = data["config"]["A_pop"]
    P_pop = data["config"]["P_pop"]

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
        line = route_set[i]["lines"][line_idx - 1]
        # add bus config to service (schedule)
        add_line_to_services(n,line)

    # change type of bus
    change_type_of_bus(n,config["type_of_bus"])

    # write to matsim
    input_path = Path(config["workers_input_path"]) / f"worker{worker_id}"
    n.write_to_matsim(input_path)

    # build config file
    template_config_path = Path(config["config_path"])
    new_config_path = input_path / "config.xml"
    build_config_file(worker_id, template_config_path, new_config_path)





import multiprocessing
import time
import os
import psutil
import subprocess
import threading

# config
def load_config(filepath):
    config = {}
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=')
                config[key.strip()] = int(value.strip())
    return config

config = load_config('config.txt')

THRESHOLD_HIGH = config.get('THRESHOLD_HIGH', 75)
THRESHOLD_LOW = config.get('THRESHOLD_LOW', 60)
CHECK_INTERVAL = config.get('CHECK_INTERVAL', 2)
HIGH_CPU_DURATION = config.get('HIGH_CPU_DURATION', 10)
LOW_CPU_DURATION = config.get('LOW_CPU_DURATION', 15)

print("[CONFIG] Loaded Configuration:")
print(f"  THRESHOLD_HIGH = {THRESHOLD_HIGH}")
print(f"  THRESHOLD_LOW = {THRESHOLD_LOW}")
print(f"  CHECK_INTERVAL = {CHECK_INTERVAL}")
print(f"  HIGH_CPU_DURATION = {HIGH_CPU_DURATION}")
print(f"  LOW_CPU_DURATION = {LOW_CPU_DURATION}\n")


# flags
migrated = False
low_cpu_start_time = None
high_cpu_start_time = None
gcp_vm_created = False


# GCP config
PROJECT_ID = "vcc-assignment3-454514"
ZONE = "asia-south2-a"
MACHINE_TYPE = "n1-standard-1"
IMAGE_FAMILY = "ubuntu-2204-lts"
IMAGE_PROJECT = "ubuntu-os-cloud"

vm_name = ""
vm_log_thread = None
vm_log_thread_stop_event = threading.Event()


# local tasks
def cpu_intensive_task(task_name):
    print(f"[{task_name}] Starting locally on PID {os.getpid()}...")
    x = 0
    iteration = 0

    while True:
        for _ in range(10**7):
            x += 1

        iteration += 1
        if iteration % 3 == 0:
            print(f"[{task_name}] Running locally on PID {os.getpid()}")


# running tasks are multiple processes 
def start_tasks(task_names, processes):
    for name in task_names:
        p = multiprocessing.Process(target=cpu_intensive_task, args=(name,))
        p.start()
        processes[name] = p
        print(f"[SERVER] Started {name} (PID {p.pid})")


# stopping processes
def stop_tasks(task_names, processes):
    for name in task_names:
        p = processes.get(name)
        if p and p.is_alive():
            p.terminate()
            p.join()
            print(f"[SERVER] Stopped {name} (PID {p.pid})")
            del processes[name]


# function to create VM on GCP and migrate 2 tasks if CPU Usage exceeds threshold
# this function creates GCP only if GCP VM hasn't been created already
def create_gcp_vm_if_needed():
    global vm_name, gcp_vm_created, vm_log_thread, vm_log_thread_stop_event

    if gcp_vm_created:
        print(f"[MIGRATION] GCP VM {vm_name} already exists. Skipping creation.")
        return

    vm_name = f"scaled-vm-{int(time.time())}"
    print(f"[MIGRATION] Creating GCP VM: {vm_name}")

    create_vm_command = [
        "gcloud", "compute", "instances", "create", vm_name,
        "--zone", ZONE,
        "--machine-type", MACHINE_TYPE,
        "--image-family", IMAGE_FAMILY,
        "--image-project", IMAGE_PROJECT,
        "--project", PROJECT_ID
    ]

    try:
        subprocess.run(create_vm_command, check=True)
        print(f"[MIGRATION] VM {vm_name} created successfully!")
        gcp_vm_created = True

        print("[MIGRATION] Waiting 30 seconds for VM to boot...")
        time.sleep(30)

        scp_command = [
            "gcloud", "compute", "scp",
            "gcp_tasks.py", f"{vm_name}:~/",
            "--zone", ZONE,
            "--project", PROJECT_ID
        ]
        subprocess.run(scp_command, check=True)
        print(f"[MIGRATION] gcp_tasks.py copied to VM {vm_name}.")

        # Start log streaming thread
        vm_log_thread_stop_event.clear()
        vm_log_thread = threading.Thread(target=stream_gcp_vm_logs, args=(vm_name,))
        vm_log_thread.daemon = True
        vm_log_thread.start()

    except subprocess.CalledProcessError as e:
        print(f"[MIGRATION] Failed to create VM: {e}")


# start the 2 tasks on GCP VM
def start_tasks_on_gcp_vm():
    print(f"[MIGRATION] Starting tasks on GCP VM {vm_name}...")

    ssh_command = [
        "gcloud", "compute", "ssh",
        vm_name,
        "--zone", ZONE,
        "--project", PROJECT_ID,
        "--command", "nohup python3 -u ~/gcp_tasks.py > ~/gcp_tasks.log 2>&1 &"
    ]

    try:
        subprocess.run(ssh_command, check=True)
        print(f"[MIGRATION] Started gcp_tasks.py on VM {vm_name}.")
    except subprocess.CalledProcessError as e:
        print(f"[MIGRATION] Failed to start tasks on VM: {e}")


# stop 2 tasks on GCP and migrate them back to local VM if CPU Usage has stabilized
# on local VM
def stop_tasks_on_gcp_vm():
    print(f"[MIGRATION] Stopping tasks on GCP VM {vm_name}...")

    ssh_command = [
        "gcloud", "compute", "ssh",
        vm_name,
        "--zone", ZONE,
        "--project", PROJECT_ID,
        "--command", "pkill -f gcp_tasks.py"
    ]

    try:
        subprocess.run(ssh_command, check=True)
        print(f"[MIGRATION] Stopped tasks on GCP VM {vm_name}.")
    except subprocess.CalledProcessError as e:
        print(f"[MIGRATION] Failed to stop tasks on VM: {e}")


# Print the output from tasks that are being executed on GCP VM
def stream_gcp_vm_logs(vm_name):
    print(f"[LOG] Streaming logs from {vm_name}...")

    ssh_command = [
        "gcloud", "compute", "ssh", vm_name,
        "--zone", ZONE,
        "--project", PROJECT_ID,
        "--command", "tail -f ~/gcp_tasks.log"
    ]

    try:
        process = subprocess.Popen(ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while not vm_log_thread_stop_event.is_set():
            line = process.stdout.readline()
            if line:
                print(f"[GCP VM LOG] {line.strip()}")

        process.terminate()

    except subprocess.CalledProcessError as e:
        print(f"[LOG] Failed to stream logs from {vm_name}: {e}")


# Before exiting code, delete GCP VM
def delete_gcp_vm():
    global vm_name, gcp_vm_created, vm_log_thread_stop_event

    if gcp_vm_created and vm_name:
        print(f"[CLEANUP] Deleting VM {vm_name}...")

        vm_log_thread_stop_event.set()
        if vm_log_thread:
            vm_log_thread.join(timeout=5)

        delete_command = [
            "gcloud", "compute", "instances", "delete", vm_name,
            "--zone", ZONE,
            "--project", PROJECT_ID,
            "--quiet"
        ]

        try:
            subprocess.run(delete_command, check=True)
            print(f"[CLEANUP] VM {vm_name} deleted.")
        except subprocess.CalledProcessError as e:
            print(f"[CLEANUP] Failed to delete VM {vm_name}: {e}")

    vm_name = ""
    gcp_vm_created = False


# monitoring CPU Usage and when to migrate to GCP or migrate back to local VM
def monitor_and_manage():
    global migrated, low_cpu_start_time, high_cpu_start_time

    processes = {}
    local_tasks = ['Task 1', 'Task 2', 'Task 3', 'Task 4']
    migrated_tasks = ['Task 3', 'Task 4']

    start_tasks(local_tasks, processes)

    try:
        while True:
            cpu_usage = psutil.cpu_percent(interval=1)
            print(f"[MONITOR] CPU Usage: {cpu_usage}%")

            if cpu_usage > THRESHOLD_HIGH and not migrated:
                if high_cpu_start_time is None:
                    high_cpu_start_time = time.time()
                    print(f"[ACTION] High CPU detected. Starting timer...")

                elif time.time() - high_cpu_start_time >= HIGH_CPU_DURATION:
                    print("[ACTION] CPU has been high for 10 seconds. Migrating tasks...")

                    # stop migrated tasks locally
                    stop_tasks(migrated_tasks, processes)

                    # create GCP VM if not created before
                    create_gcp_vm_if_needed()

                    # start tasks on GCP VM
                    start_tasks_on_gcp_vm()

                    migrated = True
                    low_cpu_start_time = None
                    high_cpu_start_time = None

            elif cpu_usage <= THRESHOLD_HIGH and not migrated:
                if high_cpu_start_time is not None:
                    print(f"[ACTION] CPU dropped. Resetting high CPU timer.")
                high_cpu_start_time = None


            if migrated:
                if cpu_usage < THRESHOLD_LOW:
                    if low_cpu_start_time is None:
                        low_cpu_start_time = time.time()
                        print("[ACTION] CPU low. Starting timer to bring tasks back...")

                    elif time.time() - low_cpu_start_time >= LOW_CPU_DURATION:
                        print("[ACTION] CPU stable. Bringing tasks back locally...")

                        # stop tasks on GCP VM but do not delete VM
                        stop_tasks_on_gcp_vm()

                        # start tasks locally again
                        start_tasks(migrated_tasks, processes)

                        migrated = False
                        low_cpu_start_time = None

                else:
                    if low_cpu_start_time is not None:
                        print(f"[ACTION] CPU rose again. Resetting low CPU timer.")
                    low_cpu_start_time = None

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("[MONITOR] Stopped by user. Cleaning up...")

        if migrated:
            stop_tasks_on_gcp_vm()  # stop tasks on GCP VM

        stop_tasks(local_tasks, processes)  # stop local tasks
        delete_gcp_vm()   # delete created VM, if any


if __name__ == "__main__":
    monitor_and_manage()

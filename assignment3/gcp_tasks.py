import multiprocessing
import time

def cpu_intensive_task(name, delay):
    print(f"[{name}] Starting on GCP!", flush=True)
    x = 0
    iteration = 0
    while True:
        for _ in range(10**7):
            x += 1
        iteration += 1
        if iteration % 3 == 0:
            print(f"[{name}] Running on GCP", flush=True)

if __name__ == '__main__':
    p3 = multiprocessing.Process(target=cpu_intensive_task, args=('Task 3', 0.3))
    p4 = multiprocessing.Process(target=cpu_intensive_task, args=('Task 4', 0.4))
    p3.start()
    p4.start()
    p3.join()
    p4.join()

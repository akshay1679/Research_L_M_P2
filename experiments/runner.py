# experiments/runner.py
# Paper-faithful emulation runner

import subprocess
import time

RUNS = 50   # Paper uses 200; 50 acceptable for software emulation

for run in range(RUNS):
    print(f"Run {run + 1}/{RUNS}")

    sub = subprocess.Popen([
        "python3", "src/mqtt/subscriber.py",
        "--broker", "10.0.0.5",
        "--topic", "rt/topic",
        "--deadline", "0.05",
        "--logfile", f"results_run_{run}.csv"
    ])

    time.sleep(2)

    pub = subprocess.Popen([
        "python3", "src/mqtt/publisher.py",
        "--broker", "10.0.0.5",
        "--topic", "rt/topic",
        "--Ci", "0.01",
        "--Ti", "0.02",
        "--Di", "0.05",
        "--Pi", "5"
    ])

    time.sleep(10)

    pub.terminate()
    sub.terminate()

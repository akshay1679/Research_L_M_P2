# experiments/plot_results.py
# Paper-faithful result visualization (Box plots)

import csv
import glob
import matplotlib.pyplot as plt

def load_latencies(pattern):
    latencies = []
    for file in glob.glob(pattern):
        with open(file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                latencies.append(float(row['latency']))
    return latencies

def load_deadline_miss(pattern):
    misses = []
    for file in glob.glob(pattern):
        with open(file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                misses.append(int(row['miss']))
    return misses

# ----------------------------------------------------
# Load results
# ----------------------------------------------------
ts_latencies = load_latencies("results_run_*.csv")

# If you later run NTS experiments, change pattern
# nts_latencies = load_latencies("nts_results_run_*.csv")

# ----------------------------------------------------
# Box plot for End-to-End Latency (Paper Fig. style)
# ----------------------------------------------------
plt.figure()
plt.boxplot([ts_latencies], labels=['TS Traffic'])
plt.ylabel("End-to-End Latency (seconds)")
plt.title("End-to-End Latency Distribution")
plt.grid(True)
plt.show()

# ----------------------------------------------------
# Deadline Miss Ratio
# ----------------------------------------------------
misses = load_deadline_miss("results_run_*.csv")
dmr = sum(misses) / len(misses)

print(f"Deadline Miss Ratio: {dmr:.4f}")


# How to Fix the MRT-MQTT Experiment Environment

The experiment failed because the **Ryu SDN Controller** is incompatible with **Python 3.12**, which is the default system version. Specifically, the `eventlet` library that Ryu relies on performs low-level networking hacks that broke in Python 3.12 (due to the removal of `ssl.wrap_socket` and other changes).

To fix this, you must run the project in a **Python 3.9** environment.

## Step 1: Install Python 3.9

You need to install Python 3.9 alongside your system Python. On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.9 python3.9-venv python3.9-dev
```

## Step 2: Recreate the Virtual Environment

Delete the broken Python 3.12 environment and create a new one using Python 3.9.

1.  **Remove existing venv**:
    ```bash
    rm -rf vem
    ```

2.  **Create new venv with Python 3.9**:
    ```bash
    python3.9 -m venv vem
    ```

3.  **Activate it**:
    ```bash
    source vem/bin/activate
    ```

## Step 3: Install Dependencies

Now install the required packages. Note that we use `ryu` instead of `ryu-network`.

```bash
pip install --upgrade pip setuptools wheel
pip install ryu mininet paho-mqtt scapy networkx numpy matplotlib ipaddress eventlet==0.33.3
```

> **Note**: `eventlet==0.33.3` is stable for Ryu on Python 3.9.

## Step 4: Run the Experiment

Now that the environment is correct, the orchestration script `run_experiment_v2.py` should work without modification (it looks for the `vem` directory).

```bash
sudo vem/bin/python run_experiment_v2.py
```

## Checklist for Verification
- [ ] Check `results.csv`: It should contain rows of data (send/recv times).
- [ ] Check `ryu.log`: It should show "Connected to switch..." messages logic instead of crashing.

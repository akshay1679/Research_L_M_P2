# MRT-MQTT: Scalable Real-Time SDN-Based MQTT Framework

This repository contains the implementation of the **MRT-MQTT Framework**, a research project integrating SDN (Software-Defined Networking) with MQTT to provide deterministic real-time communication for industrial IoT.

## Project Structure

```bash
.
├── src/
│   ├── controller/          # SDN Controller logic (Ryu)
│   │   ├── sdn_controller.py   # Main Controller App
│   │   ├── routing.py          # Path calculation
│   │   └── holistic_analysis.py # Schedulability Analysis
│   ├── network_manager/     # Edge logic
│   │   └── rt_nm.py            # RT-Network Manager (Sniffer & Coordinator)
│   └── mqtt/               # MQTT Clients
│       ├── publisher.py        # RT/BE Publisher
│       └── subscriber.py       # Subscriber with logging
├── mininet/
│   └── topology.py          # Mininet Topology & OpenFlow 1.3 switch config
├── vem/                     # Python 3.9 Virtual Environment (Target for execution)
├── run_experiment_v2.py     # Main Experiment Orchestrator
├── reproduce_issue.py       # Debug script for IP assignment
├── architecture.md          # Detailed Architecture Description
└── requirements.txt         # Python dependencies
```

## Prerequisites

-   **OS:** Linux (Ubuntu 20.04/22.04 recommended)
-   **Python:** 3.9 (Required for Ryu compatibility)
-   **Dependencies:**
    -   Ryu SDN Framework
    -   Mininet
    -   Open vSwitch (OVS)
    -   Mosquitto MQTT Broker
    -   Scapy
    -   Paho-MQTT
    -   Eventlet==0.33.3

## Setup

1.  **Virtual Environment:**
    The project uses a dedicated Python 3.9 virtual environment located in `./vem`.
    Do not use the system Python 3.12, as it is incompatible with Ryu.

2.  **Dependencies:**
    Installed within `vem`. To reinstall or verify:
    ```bash
    source vem/bin/activate
    pip install -r requirements.txt
    ```

## Running the Experiment

To run the full MRT-MQTT experiment:

1.  **Clean Up (Important):**
    Mininet and OVS can leave artifacts. Always clean before running.
    ```bash
    sudo ip -all netns delete
    sudo mn -c
    ```

2.  **Execute the Orchestrator:**
    Use `sudo` and the `vem` python executable.
    ```bash
    sudo vem/bin/python run_experiment_v2.py
    ```

### What Happens During Execution?
1.  **Topology Creation:** Mininet builds the Multi-Edge topology (Hosts, Switches, Links).
2.  **Controller Start:** Launches the Ryu Controller in the background.
3.  **Network Config:**
    -   Switches configured to **OpenFlow 1.3**.
    -   Host interfaces configured (offloading disabled to fix TCP checksums).
    -   VETH pair (`cp0` <-> `s1-ethX`) created for Control Plane connectivity.
4.  **Service Launch:**
    -   **Mosquitto Brokers** start on Edge Nodes (h5, h10, h15).
    -   **RT-NM** starts on Edge Nodes to sniff traffic.
5.  **Traffic Generation:**
    -   **Subscriber (h4)** connects to Broker (h5).
    -   **TS Publisher (h1)** connects and requests admission (High Priority).
    -   **BE Publisher (h3)** connects (Best Effort).
    -   **Background Traffic (Iperf)** runs to simulate congestion.
6.  **Completion:** Services stop, and results are saved.

## Results

-   **`results.csv`:** Contains the primary metrics:
    -   `send`: Timestamp of message sending.
    -   `recv`: Timestamp of message receipt.
    -   `latency`: End-to-end latency.
    -   `deadline`: Flow deadline.
    -   `miss`: Boolean (1 if Deadline Missed, 0 otherwise).

-   **Logs:**
    -   `ryu.log`: Controller decision logs (PacketIn, Admission, Flow Install).
    -   `h5_rt_nm.log`: RT-NM packet processing logs.
    -   `publisher.log`: Publisher admission status.

## Troubleshooting

-   **"Network is down" / Connectivity Issues:**
    -   Ensure `ip -all netns delete` is run to remove stale namespaces.
    -   Check `h5_ip_debug.log` to verify interface status.
-   **Packet Loss / TCP Handshake Failures:**
    -   Ensure NIC offloading is disabled (handled automatically by `run_experiment_v2.py`).
-   **Ryu Crashes:**
    -   Ensure you are using `vem/bin/python` (Python 3.9).

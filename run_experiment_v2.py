import sys
import time
import subprocess
import os
import signal
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI
try:
    from mininet.nodelib import NAT
except ImportError:
    NAT = None
    info("Warning: NAT not found in mininet.nodelib\n")
import socket

def get_host_ip():
    """Detect the host's primary IP address (reachable from Mininet hosts)"""
    try:
        # Use hostname -I to get all IPs and pick the first non-loopback one
        output = subprocess.check_output(['hostname', '-I']).decode().strip()
        ips = output.split()
        for ip in ips:
             if not ip.startswith('127.'):
                  return ip
        return "127.0.0.1"
    except Exception:
        return "127.0.0.1"

# Ensure we can import modules from the current directory
sys.path.append(os.getcwd())

try:
    from mininet.topology import MRT_MQTT_Topo
except ImportError:
    # Fallback or try importing from file path if package structure issues
    sys.path.append('mininet')
    from topology import MRT_MQTT_Topo

def run_experiment():
    setLogLevel('info')
    
    # Get absolute paths for executables
    # We use local ryu installed in 'ryu' directory
    ryu_manager = os.path.abspath("ryu/bin/ryu-manager")
    ryu_manager = os.path.abspath("ryu/bin/ryu-manager")
    python_exec = sys.executable 
    
    # We will use a dedicated Host Interface IP "10.0.0.254"
    host_ip = "10.0.0.254"
    info(f"*** Using Host Interface IP: {host_ip}\n") 

    # 1. Start Ryu Controller
    info('*** Starting Ryu Controller\n')
    # Add 'src' and 'ryu' to PYTHONPATH
    src_path = os.path.join(os.getcwd(), 'src')
    ryu_path = os.path.join(os.getcwd(), 'ryu')
    env = os.environ.copy()
    
    python_path_items = [src_path, ryu_path]
    if 'PYTHONPATH' in env:
        python_path_items.append(env['PYTHONPATH'])
    env['PYTHONPATH'] = os.pathsep.join(python_path_items)
    
    # Use module syntax for ryu-manager to allow relative imports within the package
    # Listen on ALL interfaces (0.0.0.0) so Mininet hosts can reach it
    controller_cmd = [sys.executable, ryu_manager, "--ofp-tcp-listen-port", "6633", "controller.sdn_controller"]
    
    # Redirect output to log file to avoid clutter
    with open("ryu.log", "w") as ryu_log:
        ryu_process = subprocess.Popen(controller_cmd, stdout=ryu_log, stderr=ryu_log, env=env)
    
    time.sleep(10) # Give Ryu time to start

    info('*** Checking if Ryu is listening on 6633\n')
    os.system("netstat -tulpn | grep 6633")

    # 2. Start Mininet
    info('*** Starting Mininet\n')
    topo = MRT_MQTT_Topo()
    # using RemoteController to connect to our background Ryu instance on port 6633
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633), link=TCLink)
    
    net.start()
    
    # 2.0 Configure Host Link for Controller Access (Manual VETH)
    # Replaces broken addNAT logic
    info('*** Setting up Control/Data Plane connection (cp0 <-> s1-ethX)\n')
    os.system("ip link delete cp0 2>/dev/null") # Cleanup prev
    os.system("ip link add cp0 type veth peer name cp1")
    os.system("ip link set cp0 up")
    os.system("ip link set cp1 up")
    os.system(f"ip addr add {host_ip}/8 dev cp0")
    
    # Attach cp1 to s1 (Gateway for Edge A)
    s1 = net.get('s1')
    s1.attach('cp1')
    
    # 2.1 Configure OVS Queues (Item 6, 7, 15)
    info('*** Configuring OVS Queues and QoS\n')
    for sw in net.switches:
        # Create QoS and Queues
        # Queue 0: Best Effort (Min 1M, Max 100M)
        # Queue 1: Real-Time (Min 50M, Max 100M)
        # Warning: syntax depends on OVS version, this is standard OVSDB
        cmd = f"ovs-vsctl -- set Port {sw.name}-eth1 qos=@newqos -- " \
              f"--id=@newqos create QoS type=linux-htb other-config:max-rate=100000000 queues:0=@q0 queues:1=@q1 -- " \
              f"--id=@q0 create Queue other-config:min-rate=1000000 other-config:max-rate=100000000 -- " \
              f"--id=@q1 create Queue other-config:min-rate=50000000 other-config:max-rate=100000000"
        # We should apply to all active ports. For simplicity applying to eth1 (uplink?)
        # Better: apply to all ports of the switch
        for intf in sw.intfList():
            if intf.name != 'lo':
                 sw.cmd(f"ovs-vsctl -- set Port {intf.name} qos=@newqos -- " \
                        f"--id=@newqos create QoS type=linux-htb other-config:max-rate=100000000 queues:0=@q0 queues:1=@q1 -- " \
                        f"--id=@q0 create Queue other-config:min-rate=1000000 other-config:max-rate=100000000 -- " \
                        f"--id=@q1 create Queue other-config:min-rate=50000000 other-config:max-rate=100000000")

    try:
        # Wait for switches to connect to controller
        info('*** Waiting for switches to connect...\n')
        time.sleep(5)
        
        info('*** Running PingAll to verify connectivity...\n')
        net.pingAll()

        # Disable offloading on all hosts (Fix TCP Checksums)
        for h in net.hosts:
            for intf in h.intfList():
                h.cmd(f'ethtool -K {intf.name} rx off tx off sg off tso off ufo off gso off gro off lro off')

        # 3. Start MQTT Brokers & RT-NM (Item 10)
        brokers = ['h5', 'h10', 'h15']
        for broker_name in brokers:
            host = net.get(broker_name)
            info(f'*** Starting Broker & RT-NM on {broker_name}\n')
            # Run mosquitto in background with log redirection, NOT daemon mode (-d) to capture stdout/stderr
            host.cmd(f'mosquitto -c mosquitto.conf > {broker_name}_mosq.log 2>&1 &')
            
            # Wait for Mosquitto to start
            info(f'*** Waiting for Broker on {broker_name}...\n')
            retries = 20
            while retries > 0:
                # Check if port 1883 is listening
                out = host.cmd('netstat -tln | grep :1883')
                if ':1883' in out:
                     break
                time.sleep(0.5)
                retries -= 1
            
            # Force interface up and log state
            host.cmd(f'ip link set {broker_name}-eth0 up')
            host.cmd(f'ethtool -K {broker_name}-eth0 rx off tx off sg off tso off ufo off gso off gro off lro off')
            host.cmd(f'ip addr > {broker_name}_ip_debug.log')
            
            # Start RT-NM
            # Interface: h5-eth0
            # Pass detected host_ip as --controller
            # Use python -u for unbuffered output
            rt_nm_cmd = f"{python_exec} -u src/network_manager/rt_nm.py {broker_name}-eth0 --controller {host_ip} > {broker_name}_rt_nm.log 2>&1 &"
            host.cmd(rt_nm_cmd)
        
        info('*** Waiting 10s for services to stabilize...\n')
        time.sleep(10)

        # 4. Run Subscriber on h4 (Edge A)
        sub_host = net.get('h4')
        broker_ip = net.get('h5').IP()
        info(f'*** Starting Subscriber on h4 connecting to {broker_ip}\n')
        sub_cmd = f"{python_exec} src/mqtt/subscriber.py --broker {broker_ip} --topic rt/topic --deadline 0.05 --logfile results.csv > subscriber.log 2>&1 &"
        sub_host.cmd(sub_cmd)

        time.sleep(1)

        # 5. Run Publisher on h1 (TS Flow)
        pub_host = net.get('h1')
        info(f'*** Starting TS Publisher on h1 connecting to {broker_ip}\n')
        # Pi=5 (High Priority)
        pub_cmd = f"{python_exec} src/mqtt/publisher.py --broker {broker_ip} --topic rt/topic --Ci 0.01 --Ti 0.05 --Pi 5 > publisher.log 2>&1 &"
        pub_host.cmd(pub_cmd)

        # 6. Run BE Publisher on h3 (Item 12)
        be_host = net.get('h3')
        info(f'*** Starting NT-S (Best Effort) Publisher on h3\n')
        # Pi=10 (Low Priority)
        be_cmd = f"{python_exec} src/mqtt/publisher.py --broker {broker_ip} --topic rt/topic --Ci 0.01 --Ti 0.05 --Pi 10 > be_publisher.log 2>&1 &"
        be_host.cmd(be_cmd)

        
        info('*** Waiting 5s for Publishers to connect...\n')
        time.sleep(5)

        # 7. Background Interference (Item 13)
        # Using iperf between Edge A and Edge B
        info('*** Starting Background Traffic (Iperf)\n')
        h2 = net.get('h2')
        h6 = net.get('h6') # In Edge B
        h6.cmd('iperf -s -u &')
        # 10Mbps UDP Background traffic
        h2.cmd('iperf -c 10.0.0.6 -u -b 10M -t 20 &')

        info('*** Experiment Running for 20 seconds...\n')
        time.sleep(20)

        info('*** Experiment Completed. Stopping services.\n')
        
        # Kill publisher/subscriber manually if needed (mininet cleanup normally kills processes started via cmd?)
        # For background processes with &, they might linger.
        # pub_host.cmd('kill %python3') 

    except Exception as e:
        info(f'*** Error: {e}\n')
    
    finally:
        info('*** Stopping Network\n')
        net.stop()
        
        info('*** Killing Ryu Controller\n')
        os.kill(ryu_process.pid, signal.SIGTERM)
        ryu_process.wait()
        
        # Cleanup mosquitto processes
        os.system("sudo pkill mosquitto")
        # Cleanup python processes started by mininet logic if any linger?
        os.system("ip link delete cp0 2>/dev/null")
        # But be careful not to kill ourself.

if __name__ == '__main__':
    run_experiment()

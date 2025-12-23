
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import sys
import os

# Ensure import paths
sys.path.append(os.getcwd())
try:
    from mininet.topology import MRT_MQTT_Topo
except ImportError:
    sys.path.append('mininet')
    from topology import MRT_MQTT_Topo

def check_ips():
    setLogLevel('info')
    topo = MRT_MQTT_Topo()
    # Mock controller not needed for IP check, but needed for Mininet init
    net = Mininet(topo=topo, controller=None, link=TCLink)
    
    info('*** Starting Network (Dry Run)\n')
    # We must construct it manually or just use start() but without controller it might hang if waiting?
    # Actually Mininet w/o controller fails ping but IPs are assigned by start().
    # We can use OVSController or None.
    
    # We just want to check if Mininet assigns IPs.
    # net.build() # Mininet builds by default
    try:
        from mininet.nodelib import NAT
        net.addNAT(name='nat0', ip='10.0.0.254/8').configDefault = lambda: None
    except:
        pass
    
    info('*** Checking IP assignments\n')
    for h in net.hosts:
        print(f"Host {h.name}: IP={h.IP()}")
        
    net.stop()

if __name__ == '__main__':
    check_ips()

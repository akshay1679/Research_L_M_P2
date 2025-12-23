#!/usr/bin/python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

class MRT_MQTT_Topo(Topo):
    """
    Topology for MRT-MQTT Framework (Fig. 15 of the paper)
    3 Edge Networks (A, B, C)
    8 OpenFlow Switches (s1-s8)
    Controller (c0)
    Links 100Mbit/s
    """

    def build(self):
        # Create Switches
        # Core/Inter-connection switches
        s1 = self.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')
        s2 = self.addSwitch('s2', cls=OVSKernelSwitch, protocols='OpenFlow13')
        s3 = self.addSwitch('s3', cls=OVSKernelSwitch, protocols='OpenFlow13')
        s4 = self.addSwitch('s4', cls=OVSKernelSwitch, protocols='OpenFlow13') # Central interconnect?
        s5 = self.addSwitch('s5', cls=OVSKernelSwitch, protocols='OpenFlow13') # Central interconnect?
        # Based on Fig 15 visual approximation:
        # S1 connects Edge A
        # S2 connects Edge B
        # S3 connects Edge C
        # S4, S5, S6, S7, S8 seem to form the core network path options for Multipath
        
        # Let's align with the description: "Eight OF-switches (labeled s1 to s8)"
        # And "LAA = { hEN.A, s1...}, LAB = {hEN.A, s1, s4, s2, h10}, LAC = {hEN.A, s1, s4, s5, s3, h15}"
        # This implies:
        # s1 is gateway for Edge A
        # s2 is gateway for Edge B
        # s3 is gateway for Edge C
        # s1 - s4 - s2 (Path to B)
        # s1 - s4 - s5 - s3 (Path to C)
        
        # Let's add all 8 switches
        switches = {}
        # Manually add s1-s5 to dict since we created them
        switches['s1'] = s1
        switches['s2'] = s2
        switches['s3'] = s3
        switches['s4'] = s4
        switches['s5'] = s5
        
        for i in range(6, 9):
            switches[f's{i}'] = self.addSwitch(f's{i}', cls=OVSKernelSwitch, protocols='OpenFlow13')

        # Create Hosts for Edge Network A (Connected to s1)
        # 9 nodes (h1-h3 publishers, h4 subscriber, h5 broker/ort-nm, h6-h8...?)
        # Paper says: "nine nodes (h1 to h3, h6 to h8, and h11 to h13) in each edge network, designated as MQTT publishers."
        # Wait, "In such scenarios... h1 to h3... in each edge network" - check wording.
        # "setup features nine nodes (h1 to h3, h6 to h8, and h11 to h13) in each edge network"
        # This sentence is slightly confusing. It probably means:
        # Edge A: h1, h2, h3 (pubs), h4 (sub), h5 (broker)
        # Edge B: h6, h7, h8 (pubs)... actually let's follow the numbers in the text strictly.
        # "h1 to h3, h6 to h8, and h11 to h13 ... designated as MQTT publishers" -> Total 9 publishers globally?
        # Ah, "h1 to h3" (in EN.A?), "h6 to h8" (in EN.B?), "h11 to h13" (in EN.C?)
        # Let's re-read carefully: "nodes (h1 to h3, h6 to h8, and h11 to h13) in each edge network" -> No, "h1, h2, h3" are in EN.A likely.
        # "One subscriber located at nodes h4, h9, and h14" -> h4 in A, h9 in B, h14 in C
        # "Broker and ORT-NM hosted on nodes h5, h10, and h15" -> h5 in A, h10 in B, h15 in C.

        # So:
        # EN.A: s1
        #   Publishers: h1, h2, h3
        #   Subscriber: h4
        #   Broker: h5
        # EN.B: s2
        #   Publishers: h6, h7, h8
        #   Subscriber: h9
        #   Broker: h10
        # EN.C: s3
        #   Publishers: h11, h12, h13
        #   Subscriber: h14
        #   Broker: h15
        
        # Links: 100Mbit/s
        linkop = {'bw': 100}

        # --- Edge A ---
        h1 = self.addHost('h1') # TS Pub
        h2 = self.addHost('h2') # TS Pub
        h3 = self.addHost('h3') # NTS Pub
        h4 = self.addHost('h4') # Sub
        h5 = self.addHost('h5') # Broker/ORT-NM
        
        self.addLink(h1, switches['s1'], **linkop)
        self.addLink(h2, switches['s1'], **linkop)
        self.addLink(h3, switches['s1'], **linkop)
        self.addLink(h4, switches['s1'], **linkop)
        self.addLink(h5, switches['s1'], **linkop)

        # --- Edge B ---
        h6 = self.addHost('h6')
        h7 = self.addHost('h7')
        h8 = self.addHost('h8')
        h9 = self.addHost('h9')
        h10 = self.addHost('h10') # Broker/ORT-NM
        
        self.addLink(h6, switches['s2'], **linkop)
        self.addLink(h7, switches['s2'], **linkop)
        self.addLink(h8, switches['s2'], **linkop)
        self.addLink(h9, switches['s2'], **linkop)
        self.addLink(h10, switches['s2'], **linkop)

        # --- Edge C ---
        h11 = self.addHost('h11')
        h12 = self.addHost('h12')
        h13 = self.addHost('h13')
        h14 = self.addHost('h14')
        h15 = self.addHost('h15') # Broker/ORT-NM
        
        self.addLink(h11, switches['s3'], **linkop)
        self.addLink(h12, switches['s3'], **linkop)
        self.addLink(h13, switches['s3'], **linkop)
        self.addLink(h14, switches['s3'], **linkop)
        self.addLink(h15, switches['s3'], **linkop)

        # --- Core Network Interconnections ---
        # Reconstructing from path descriptions:
        # LAA = {..., s1, s1...} -> Local
        # LAB = s1 -> s4 -> s2
        # LAC = s1 -> s4 -> s5 -> s3
        
        self.addLink(switches['s1'], switches['s4'], **linkop)
        self.addLink(switches['s4'], switches['s2'], **linkop) # Path to B
        self.addLink(switches['s4'], switches['s5'], **linkop)
        self.addLink(switches['s5'], switches['s3'], **linkop) # Path to C
        
        # Add extra switches/links to form a mesh or redundant paths for multipath experiments
        # "Eight OF-switches (labeled s1 to s8)"
        # We used s1, s2, s3, s4, s5.
        # Need to connect s6, s7, s8 to provide alternative paths.
        # Let's create a partial mesh as implied by "Dynamic multipath routing".
        # Assuming some standard redundant connections:
        # self.addLink(switches['s1'], switches['s6'], **linkop)
        # self.addLink(switches['s6'], switches['s7'], **linkop)
        # self.addLink(switches['s7'], switches['s2'], **linkop) # Alternate path to B?
        
        # self.addLink(switches['s6'], switches['s8'], **linkop)
        # self.addLink(switches['s8'], switches['s3'], **linkop) # Alternate path to C?
        
        # Inter-switch links
        # self.addLink(switches['s4'], switches['s6'], **linkop)
        # self.addLink(switches['s5'], switches['s8'], **linkop)


def run():
    topo = MRT_MQTT_Topo()
    net = Mininet(topo=topo, controller=RemoteController, link=TCLink)
    
    info('*** Starting network\n')
    net.start()
    
    info('*** Running CLI\n')
    CLI(net)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()

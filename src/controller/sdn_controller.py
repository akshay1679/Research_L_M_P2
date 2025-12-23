from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.topology.api import get_switch, get_link
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib.packet import packet, ethernet, ether_types
from webob import Response
import json

from .routing import RoutingEngine
from .flow_manager import FlowManager
from .of_db import OFDatabase
from .holistic_analysis import HolisticAnalysis


class RT_MQTT_Controller(app_manager.RyuApp):
    """
    Paper-faithful MRT-MQTT SDN Controller
    Includes ARP flooding for connectivity.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(RT_MQTT_Controller, self).__init__(*args, **kwargs)

        wsgi = kwargs['wsgi']
        wsgi.register(RTAPI, {'controller': self})

        self.routing = RoutingEngine()
        self.of_db = OFDatabase()
        self.analysis = HolisticAnalysis(self.of_db)
        self.datapaths = {}

    # -------------------------------------------------
    # SWITCH REGISTRATION
    # -------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # TABLE-MISS RULE: DROP EVERYTHING BY DEFAULT (PacketIn happens if no match?)
        # Actually default in OF1.3 is drop, we need to install a rule to send to controller
        # if we want PacketIn.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        instructions = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                     actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=0,
            match=match,
            instructions=instructions
        )
        datapath.send_msg(mod)

    # -------------------------------------------------
    # PACKET-IN HANDLER (ARP FLOODING)
    # -------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        
        self.logger.info("PacketIn: dpid=%s, src=%s, dst=%s, type=%s, in_port=%s", 
                         datapath.id, eth.src, eth.dst, eth.ethertype, in_port)

        # Determine output port
        # For simplicity in this experiment, we FLOOD everything we don't know
        # to ensure ARP and initial connectivity works.
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        self.logger.info("Flooding packet out")

    # -------------------------------------------------
    # TOPOLOGY UPDATE
    # -------------------------------------------------
    def update_topology(self):
        switches = get_switch(self, None)
        links = get_link(self, None)

        edges = []
        for link in links:
            # We assume link.src.port_no is the port on src switch connected to dst
            edges.append((link.src.dpid, link.dst.dpid, 1, link.src.port_no))

        self.routing.update_topology(edges)

    # -------------------------------------------------
    # CORE RT REQUEST HANDLER (Paper Section 4.2)
    # -------------------------------------------------
    def handle_rt_request(self, req):
        """
        Admission control + path installation
        """
        self.update_topology()

        if self.of_db.exists(req['src'], req):
            return {'status': 'EXISTS'}

        # NOTE: src/dst DPIDs must be mapped properly
        # Here we assume fixed DPIDs for emulation
        src_dpid = 1
        dst_dpid = 3

        path = self.routing.find_shortest_path(
            src_dpid, dst_dpid, req['BWi']
        )

        if not path:
            return {'status': 'REJECTED'}

        # SCHEDULABILITY ANALYSIS
        if not self.analysis.is_schedulable(req, path):
            self.logger.warning("Flow rejected by Holistic Analysis (Deadline Miss)")
            return {'status': 'REJECTED_SCHEDULING'}

        self.of_db.add_entry(
            src=req['src'],
            subscribers=[req['dst']],
            rt_props=req,
            path=path
        )

        self.install_rt_flows(path, req)

        return {'status': 'ACCEPTED', 'path': path}

    def handle_rt_deletion(self, req):
        if not self.of_db.exists(req['src'], req):
            return {'status': 'NOT_FOUND'}
        
        # We need the path to delete flows on switches
        # Ideally OF_DB stores the path.
        # of_db.exists just checks list. I need get_entry logic or iterate.
        to_remove = [e for e in self.of_db.get_all() 
                     if e.publisher == req['src'] and e.subscribers == [req['dst']]]
        
        for entry in to_remove:
            self.delete_rt_flows(entry.path, req)
            self.of_db.remove_entry(req['src'], [req['dst']])
            
        return {'status': 'DELETED'}

    def delete_rt_flows(self, path, req):
        src_ip = req['src']
        dst_ip = req['dst']
        
        for dpid in path:
            datapath = self.datapaths.get(dpid)
            if not datapath: continue
            
            fm = FlowManager(datapath)
            match = datapath.ofproto_parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip
            )
            fm.delete_flow(match)

    # -------------------------------------------------
    # FLOW INSTALLATION (NO FLOODING)
    # -------------------------------------------------
    def install_rt_flows(self, path, req):
        """
        Install deterministic forwarding rules with explicit port and match
        """
        priority = int(req.get('Pi', 10))
        src_ip = req['src']
        dst_ip = req['dst']

        for i in range(len(path) - 1):
            curr_dpid = path[i]
            next_dpid = path[i + 1]
            
            datapath = self.datapaths.get(curr_dpid)
            if not datapath:
                continue

            # Get Output Port
            out_port = self.routing.get_port(curr_dpid, next_dpid)
            if out_port is None:
                self.logger.error("No port found for %s -> %s", curr_dpid, next_dpid)
                continue

            fm = FlowManager(datapath)
            parser = datapath.ofproto_parser

            # SPECIFIC FLOW MATCH (Item 5)
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip
            )
            
            # QUEUE SELECTION (Item 6, 7, 15)
            # Paper: High Priority maps to RT Queue (1), Best Effort to Default (0)
            # We assume Pi < 8 is RT (e.g. 5), Pi >= 8 is Best Effort (e.g. 10)
            queue_id = 1 if priority < 8 else 0
            
            # EXPLICIT FORWARDING with Queue
            actions = [
                parser.OFPActionSetQueue(queue_id),
                parser.OFPActionOutput(out_port)
            ]

            fm.add_flow(priority=priority,
                        match=match,
                        actions=actions)

    # -------------------------------------------------
    # MULTICAST HANDLING (Items 8, 9)
    # -------------------------------------------------
    def handle_multicast_join(self, req):
        """
        req: {src: SubIP, dst: BrokerIP, topic: Topic...}
        """
        # We define the Group ID based on Topic (hash) or manually assignment
        # For simplicity, we use a single group ID = 1
        group_id = 1
        broker_ip = req['dst'] # Subscriber sends to Broker to subscribe
        sub_ip = req['src']
        
        # We want a tree ROOTED at Broker, leading to Subscribers
        if not hasattr(self, 'multicast_groups'):
            self.multicast_groups = {} # { broker_ip: [sub_ips] }
            
        if broker_ip not in self.multicast_groups:
            self.multicast_groups[broker_ip] = []
        if sub_ip not in self.multicast_groups[broker_ip]:
            self.multicast_groups[broker_ip].append(sub_ip)
            
        subs = self.multicast_groups[broker_ip]
        
        # Compute Tree
        tree = self.routing.find_multicast_tree(self.get_dpid(broker_ip), [self.get_dpid(s) for s in subs])
        
        # Install Group Entries
        self.install_multicast_groups(tree, group_id, broker_ip)
        
        return {'status': 'JOINED', 'tree': tree}

    def get_dpid(self, ip):
        # Map IP to DPID (Simulated mapping)
        # h1-h3 (10.0.0.1-3) -> s1 (1)
        # h6-h8 -> s2 (2)
        # h11-h13 -> s3 (3)
        # Broker h5 (10.0.0.5) -> s1 (1)
        # Broker h10 -> s2
        ip_last = int(ip.split('.')[-1])
        if ip_last <= 5: return 1
        if ip_last <= 10: return 2
        return 3

    def install_multicast_groups(self, tree, group_id, broker_ip):
        for dpid, next_hops in tree.items():
            datapath = self.datapaths.get(dpid)
            if not datapath: continue
            
            parser = datapath.ofproto_parser
            ofproto = datapath.ofproto
            
            buckets = []
            for nh in next_hops:
                port = self.routing.get_port(dpid, nh)
                if port:
                    actions = [parser.OFPActionOutput(port)]
                    buckets.append(parser.OFPBucket(actions=actions))
            
            # Install Group
            req = parser.OFPGroupMod(datapath, ofproto.OFPGC_ADD,
                                     ofproto.OFPGT_ALL, group_id, buckets)
            datapath.send_msg(req)
            
            # Install Flow pointing to Group
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=broker_ip, ipv4_dst="224.0.0.1") # Multicast IP
            actions = [parser.OFPActionGroup(group_id)]
            
            self.install_flow_raw(datapath, 10, match, actions)

    def install_flow_raw(self, datapath, priority, match, actions):
         mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match, 
            instructions=[datapath.ofproto_parser.OFPInstructionActions(
                datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)])
         datapath.send_msg(mod)


# -------------------------------------------------
# REST API (RT-NM → CONTROLLER)
# -------------------------------------------------
class RTAPI(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(RTAPI, self).__init__(req, link, data, **config)
        self.ctrl = data['controller']

    @route('rt_mqtt', '/rt_mqtt/register', methods=['POST'])
    def register(self, req, **kwargs):
        body = json.loads(req.body)
        
        # Check if Multicast
        if body.get('is_multicast'):
            result = self.ctrl.handle_multicast_join(body)
        else:
            result = self.ctrl.handle_rt_request(body)
            
        return Response(
            content_type='application/json',
            body=json.dumps(result)
        )

    @route('rt_mqtt_del', '/rt_mqtt/remove', methods=['POST'])
    def remove(self, req, **kwargs):
        body = json.loads(req.body)
        result = self.ctrl.handle_rt_deletion(body)
        return Response(
            content_type='application/json',
            body=json.dumps(result)
        )

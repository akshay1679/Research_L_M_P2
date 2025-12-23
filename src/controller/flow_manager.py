from ryu.ofproto import ofproto_v1_3


class FlowManager:
    """
    Deterministic Flow Installer for MRT-MQTT
    -----------------------------------------
    - No learning switch
    - No flooding
    - Exact path enforcement
    - Paper-faithful SDN behavior
    """

    def __init__(self, datapath):
        self.datapath = datapath
        self.ofproto = datapath.ofproto
        self.parser = datapath.ofproto_parser

    def add_flow(self, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """
        Install a single OpenFlow rule
        """
        inst = [
            self.parser.OFPInstructionActions(
                self.ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = self.parser.OFPFlowMod(
            datapath=self.datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )

        self.datapath.send_msg(mod)

    def delete_flow(self, match):
        """
        Delete OpenFlow rules matching the criteria
        """
        mod = self.parser.OFPFlowMod(
            datapath=self.datapath,
            command=self.ofproto.OFPFC_DELETE,
            out_port=self.ofproto.OFPP_ANY,
            out_group=self.ofproto.OFPG_ANY,
            match=match
        )
        self.datapath.send_msg(mod)

    # -------------------------------------------------
    # PAPER-FAITHFUL PATH INSTALLATION
    # -------------------------------------------------
    def install_path_flows(self, path, next_hop_ports, priority):
        """
        Install deterministic forwarding rules along a path.

        Parameters:
        -----------
        path : list
            List of switch DPIDs in order (e.g., [1, 4, 5, 3])

        next_hop_ports : dict
            {(current_dpid, next_dpid): output_port}

        priority : int
            Flow priority derived from Pi (RT priority)
        """

        for i in range(len(path) - 1):
            curr_dpid = path[i]
            next_dpid = path[i + 1]

            # Only install rule on THIS switch
            if self.datapath.id != curr_dpid:
                continue

            out_port = next_hop_ports.get((curr_dpid, next_dpid))
            if out_port is None:
                raise RuntimeError(
                    f"No port mapping for link {curr_dpid} -> {next_dpid}"
                )

            # MATCH ALL IP PACKETS (paper assumes per-flow matching)
            match = self.parser.OFPMatch(
                eth_type=0x0800
            )

            actions = [
                self.parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                priority=priority,
                match=match,
                actions=actions
            )

    # -------------------------------------------------
    # DROP RULE (DEFAULT BEHAVIOR)
    # -------------------------------------------------
    def install_drop_rule(self):
        """
        Install a default drop rule (table-miss)
        """
        match = self.parser.OFPMatch()
        actions = []

        self.add_flow(
            priority=0,
            match=match,
            actions=actions
        )

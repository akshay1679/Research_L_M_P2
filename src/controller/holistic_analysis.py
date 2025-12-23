import math

class HolisticAnalysis:
    """
    Holistic Schedulability Analysis & Trajectory Analysis
    Paper Section IV-C & V
    """

    def __init__(self, of_db):
        self.of_db = of_db

    def is_schedulable(self, candidate_flow, path):
        """
        Check if the candidate flow and all existing flows remain schedulable.
        
        Args:
            candidate_flow: dict with keys 'Ci', 'Ti', 'Di' (in ms or seconds)
            path: list of DPIDs
            
        Returns:
            bool: True if schedulable
        """
        # Create a temporary list of all flows including the candidate
        all_flows = list(self.of_db.get_all())
        
        # Convert candidate flow to an object capable of analysis
        # (Assuming of_db stores objects with .rt_props)
        class CandidateEntry:
            def __init__(self, props, flow_path):
                self.rt_props = props
                self.path = flow_path
        
        candidate_entry = CandidateEntry(candidate_flow, path)
        all_flows.append(candidate_entry)
        
        # Check end-to-end response time for ALL flows
        for flow in all_flows:
            if not self._check_flow_deadline(flow, all_flows):
                return False
                
        return True

    def _check_flow_deadline(self, flow, all_flows):
        """
        Validation: End-to-End Delay <= Deadline
        D_e2e = Sum(R_node) + Sum(Delay_link) <= Di
        """
        props = flow.rt_props
        deadline = float(props.get('Di', 1.0)) # seconds
        
        e2e_delay = self._calculate_e2e_delay(flow, all_flows)
        
        return e2e_delay <= deadline

    def _calculate_e2e_delay(self, target_flow, all_flows):
        # Sum of node response times + link delays
        total_delay = 0.0
        
        path = target_flow.path
        if not path:
            return float('inf')

        # Node Delay (WCRT)
        for dpid in path:
            wcrt = self._calculate_node_wcrt(dpid, target_flow, all_flows)
            total_delay += wcrt
            
        # Link Delay (Trajectory)
        # Assuming fixed link delay for now or derived from length
        # Paper implies Trajectory Analysis includes link propagation
        link_delay_per_hop = 0.0001 # 100 microseconds assumption
        total_delay += (len(path) - 1) * link_delay_per_hop
        
        return total_delay

    def _calculate_node_wcrt(self, dpid, target_flow, all_flows):
        """
        Compute WCRT at a specific switch.
        R_i = C_i + Sum(ceil(R_i/T_j) * C_j) for j in HP(i)
        """
        # Filter flows that strictly pass through this node
        contending_flows = [f for f in all_flows if (dpid in f.path)]
        
        # Identify higher priority flows
        # Paper: Smaller Pi = Higher Priority? Or Larger? 
        # Standard MQTT: Larger Pi = Higher Priority (usually).
        # Let's assume standard behavior: Higher Pi is Higher Priority.
        target_prio = int(target_flow.rt_props.get('Pi', 0))
        target_exec = float(target_flow.rt_props.get('Ci', 0)) / 1000.0 # ms -> s conversion if needed
        
        hp_flows = []
        for f in contending_flows:
            if f == target_flow:
                continue
            f_prio = int(f.rt_props.get('Pi', 0))
            if f_prio > target_prio:
                hp_flows.append(f)
                
        # Iterative WCRT calculation
        # R_0 = C_i
        # R_{n+1} = C_i + Sum(ceil(R_n / T_j) * C_j)
        
        current_R = target_exec
        while True:
            interference = 0.0
            for hp in hp_flows:
                hp_exec = float(hp.rt_props.get('Ci', 0)) / 1000.0
                hp_period = float(hp.rt_props.get('Ti', 1.0))
                
                if hp_period <= 0: continue
                
                interference += math.ceil(current_R / hp_period) * hp_exec
                
            new_R = target_exec + interference
            
            if new_R > float(target_flow.rt_props.get('Di', 1.0)):
                return new_R # Early exit if deadline missed
            
            if abs(new_R - current_R) < 1e-9:
                return new_R # Converged
            
            current_R = new_R


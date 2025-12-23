from .rt_nm import RT_NetworkManager
# In a full implementation, ORT-NM would have additional logic to 
# communicate with other ORT-NMs or the central controller to set up MSDP/PIM-SM.
# For this emulation, it functions similarly to RT-NM but tags requests as "Edge-Aware".

class ORT_NetworkManager(RT_NetworkManager):
    def __init__(self, interface="eth0", edge_id="A"):
        super().__init__(interface)
        self.edge_id = edge_id

    def notify_controller(self, src, dst, props):
        # We add Edge ID to the request so Controller knows where it came from
        try:
            data = {
                'edge_id': self.edge_id,
                'src': src,
                'dst': dst,
                'Ci': float(props.get('Ci', 0)),
                'Pi': int(props.get('Pi', 0)),
                'Ti': float(props.get('Ti', 0)),
                'Di': float(props.get('Di', 0)),
                'BWi': float(props.get('BWi', 0)),
                'is_multicast': True # Trigger MRT logic in controller
            }
            # requests.post(CONTROLLER_URL, json=data)
            print(f"[ORT-NM-{self.edge_id}] Notifying controller for Multicast Setup: {data}")
        except ValueError:
            pass

if __name__ == "__main__":
    import sys
    edge = "A"
    if len(sys.argv) > 1:
        edge = sys.argv[1]
    
    nm = ORT_NetworkManager(edge_id=edge)
    nm.start()

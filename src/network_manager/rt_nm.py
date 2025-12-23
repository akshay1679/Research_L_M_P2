# src/network_manager/rt_nm.py
# RT Network Manager (RT-NM)
# Paper: "Extending MQTT with Real-Time Communication Services Based on SDN"
# Section IV-A, Fig. 3

from scapy.all import sniff, TCP, IP
import struct
import requests

# Controller REST endpoint (paper: RT-NM → Controller)
import argparse

# Controller REST endpoint (paper: RT-NM → Controller)
# Default to localhost, but can be overridden
DEFAULT_CONTROLLER_IP = "127.0.0.1"
CONTROLLER_URL_TEMPLATE = "http://{}:8080/rt_mqtt/register"

class RT_NetworkManager:
    """
    RT-NM:
    - Passively sniffs MQTT packets
    - Extracts real-time attributes from MQTT v5 User Properties
    - Notifies SDN controller for admission control
    """

    def __init__(self, interface="eth0", controller_ip=DEFAULT_CONTROLLER_IP):
        self.interface = interface
        self.controller_url = CONTROLLER_URL_TEMPLATE.format(controller_ip)
        self.controller_ip = controller_ip

    # ---------------------------------------------------
    # Start packet sniffing (OUT-OF-BAND as per paper)
    # ---------------------------------------------------
    def start(self):
        import time
        import scapy.config
        scapy.config.conf.use_pcap = True # Force pcap if available
        
        print(f"[RT-NM] Starting on interface {self.interface}")
        
        fallback = False
        while True:
            target_iface = "any" if fallback else self.interface
            try:
                print(f"[RT-NM] Sniffing on {target_iface}...")
                sniff(
                    iface=target_iface,
                    filter="tcp port 1883",
                    prn=self._packet_handler,
                    store=0
                )
                # If sniff returns properly (e.g. timeout), we might exit loop or retry
                # But here we don't expect it to return unless error.
                # If it returns fast, assume error.
                print("[RT-NM] Sniff returned. Retrying...")
                time.sleep(1)
            except Exception as e:
                print(f"[RT-NM] Sniff error: {e}. Retrying in 1s...")
                time.sleep(1)
                fallback = True # Try 'any' next time

    # ---------------------------------------------------
    # Packet handler
    # ---------------------------------------------------
    def _packet_handler(self, packet):
        # Debug: Print every packet
        print(f"DEBUG PKT: {packet.summary()}")
        
        if not (packet.haslayer(IP) and packet.haslayer(TCP)):
            return

        payload = bytes(packet[TCP].payload)
        if not payload:
            return

        # MQTT Control Packet Type (high nibble of byte 0)
        msg_type = (payload[0] & 0xF0) >> 4
        print(f"DEBUG: Payload len={len(payload)}, msg_type={msg_type}")

        # MQTT v5 packets of interest
        # 1 = CONNECT, 3 = PUBLISH, 8 = SUBSCRIBE, 14 = DISCONNECT
        if msg_type not in (1, 3, 8, 14):
            return

        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        
        if msg_type == 14:
            print(f"[RT-NM] Detected DISCONNECT from {src_ip}")
            self._notify_controller_removal(src_ip, dst_ip)
            return

        props = self._extract_user_properties(payload)
        print(f"DEBUG: Extracted props: {props}")
        
        # Only notify controller if RT attributes exist
        if props:
            print(f"[RT-NM] Notifying controller for {src_ip}->{dst_ip}")
            self._notify_controller(
                src_ip=src_ip,
                dst_ip=dst_ip,
                msg_type=msg_type,
                rt_props=props
            )

    def _notify_controller_removal(self, src, dst):
        try:
            data = {'src': src, 'dst': dst}
            # Need to append /remove to URL base
            # Need to append /remove to URL base
            # Current controller_url = .../register
            # We assume .../remove
            url = self.controller_url.replace('register', 'remove')
            requests.post(url, json=data, timeout=1)
            print(f"[RT-NM] Requested flow removal for {src}->{dst}")
        except:
            pass

    # ---------------------------------------------------
    # MQTT v5 User Property extraction
    # ---------------------------------------------------
    def _extract_user_properties(self, payload):
        """
        Best-effort MQTT v5 User Property extraction.
        Property Identifier: 0x26
        Keys: Ci, Pi, Ti, Di, BWi
        """

        properties = {}
        keys = [b"Ci", b"Pi", b"Ti", b"Di", b"BWi"]

        try:
            # Skip Fixed Header
            idx = 1
            multiplier = 1
            remaining_length = 0

            # Decode Remaining Length (MQTT spec)
            while True:
                encoded_byte = payload[idx]
                remaining_length += (encoded_byte & 127) * multiplier
                multiplier *= 128
                idx += 1
                if (encoded_byte & 128) == 0:
                    break

            # Search for UTF-8 encoded key-value pairs
            for key in keys:
                # UTF-8 string format: 2 bytes length + string
                pattern = b"\x00" + bytes([len(key)]) + key
                pos = payload.find(pattern)

                if pos != -1:
                    val_len_pos = pos + len(pattern)
                    val_len = struct.unpack(
                        "!H", payload[val_len_pos:val_len_pos + 2]
                    )[0]
                    val_start = val_len_pos + 2
                    val = payload[val_start:val_start + val_len].decode("utf-8")
                    properties[key.decode()] = val

        except Exception:
            # Parsing errors are ignored (paper allows passive monitoring)
            return {}

        return properties

    # ---------------------------------------------------
    # Notify SDN Controller (NO decision logic here)
    # ---------------------------------------------------
    def _notify_controller(self, src_ip, dst_ip, msg_type, rt_props):
        """
        Sends RT requirements to SDN controller.
        Admission control is NOT done here (paper compliance).
        """

        try:
            data = {
                "src": src_ip,
                "dst": dst_ip,
                "msg_type": msg_type,  # CONNECT / PUBLISH / SUBSCRIBE
                "Ci": float(rt_props.get("Ci", 0)),
                "Pi": int(rt_props.get("Pi", 0)),
                "Ti": float(rt_props.get("Ti", 0)),
                "Di": float(rt_props.get("Di", 0)),
                "BWi": float(rt_props.get("BWi", 0)),
            }

            response = requests.post(self.controller_url, json=data, timeout=5)
            
            # ADMISSION ACK (Item 1)
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get('status') == 'ACCEPTED':
                    import paho.mqtt.publish as publish
                    print(f"[RT-NM] Flow Admitted! Notifying {src_ip}")
                    # Publish ACK to sys/control/<src_ip>
                    # Assuming RT-NM runs on the Broker Node, so localhost:1883 is the broker
                    publish.single(
                        topic=f"sys/control/{src_ip}",
                        payload="ACCEPTED",
                        hostname="localhost",
                        port=1883
                    )
                else:
                    print(f"[RT-NM] Flow Rejected: {res_data.get('status')}")

        except Exception as e:
            # Controller may not be running yet
            print("[RT-NM] Controller unreachable or Error:", e)


# ---------------------------------------------------
# Standalone execution
# ---------------------------------------------------
if __name__ == "__main__":
    import sys

    iface = "eth0"
    
    parser = argparse.ArgumentParser()
    parser.add_argument('interface', nargs='?', default='eth0', help='Network interface to sniff')
    parser.add_argument('--controller', default=DEFAULT_CONTROLLER_IP, help='IP address of the SDN Controller')
    args = parser.parse_args()

    nm = RT_NetworkManager(interface=args.interface, controller_ip=args.controller)
    nm.start()


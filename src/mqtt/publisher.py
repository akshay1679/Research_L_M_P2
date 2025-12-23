import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties, PacketTypes
import time
import json
import argparse

class RTPublisher:
    def __init__(self, broker, port, topic, rt_props):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.rt_props = rt_props # Dist of RT properties
        self.client = mqtt.Client(protocol=mqtt.MQTTv5)

    def start(self):
        self.client.on_message = self.on_message
        self.control_topic = f"sys/control/{self.get_ip_address()}"
        self.admission_event = False
        
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()
        
        self.client.subscribe(self.control_topic)

        # Prepare User Properties
        # Paho requires list of tuples (key, value)
        user_properties = []
        for k, v in self.rt_props.items():
            user_properties.append((k, str(v)))

        properties = Properties(PacketTypes.PUBLISH)
        properties.UserProperty = user_properties

        print(f"Requesting Admission on {self.control_topic}...")
        # Send Probe to rt/request to trigger RT-NM
        # We use a distinct topic for requests so we don't pollute the data channel yet
        self.client.publish("rt/request", payload="ADMISSION_REQ", qos=1, properties=properties)
        
        # Block until admitted (Item 1)
        timeout = 10
        start_wait = time.time()
        while not self.admission_event:
            time.sleep(0.1)
            if time.time() - start_wait > timeout:
                print("Admission Timed Out! Exiting.")
                return

        print(f"Admission Granted! Publishing to {self.topic} with props {self.rt_props}")
        
        while True:
            msg = f"RT-Data-{time.time()}"
            self.client.publish(self.topic, payload=msg, qos=1, properties=properties)
            time.sleep(float(self.rt_props.get('Ti', 1.0)))

    def on_message(self, client, userdata, msg):
        if msg.topic == self.control_topic:
            payload = msg.payload.decode()
            if payload == "ACCEPTED":
                self.admission_event = True
                print("Received Admission Acceptance!")

    def get_ip_address(self):
        import socket
        try:
            # Hack to get local IP used for connection
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.broker, self.port))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="test/topic")
    parser.add_argument("--Ci", default="10")
    parser.add_argument("--Pi", default="1")
    parser.add_argument("--Ti", default="1.0")
    parser.add_argument("--Di", default="0.5")
    parser.add_argument("--BWi", default="100")
    args = parser.parse_args()

    props = {
        'Ci': args.Ci,
        'Pi': args.Pi,
        'Ti': args.Ti,
        'Di': args.Di,
        'BWi': args.BWi
    }

    pub = RTPublisher(args.broker, args.port, args.topic, props)
    pub.start()

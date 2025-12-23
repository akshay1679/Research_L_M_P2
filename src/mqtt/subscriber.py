# src/mqtt/subscriber.py

import paho.mqtt.client as mqtt
import time
import csv
import argparse

def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(userdata['topic'], qos=1)

def on_message(client, userdata, msg):
    recv_time = time.time()
    payload = msg.payload.decode()

    try:
        send_time = float(payload.split("-")[-1])
        latency = recv_time - send_time
    except:
        latency = 0

    deadline = float(userdata['deadline'])
    miss = 1 if latency > deadline else 0

    with open(userdata['logfile'], 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([send_time, recv_time, latency, deadline, miss])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--deadline", required=True)
    parser.add_argument("--logfile", default="results.csv")
    args = parser.parse_args()

    with open(args.logfile, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["send", "recv", "latency", "deadline", "miss"])

    client = mqtt.Client(protocol=mqtt.MQTTv5,
                         userdata={
                             'topic': args.topic,
                             'deadline': args.deadline,
                             'logfile': args.logfile
                         })

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, 1883, 60)
    client.loop_forever()

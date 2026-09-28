# ─── RANGER V3 START: 08-gps-ingest ───
"""Checkpoint probe: print NavSatFix messages from the robot via rosbridge."""
import time
import roslibpy

client = roslibpy.Ros(host='192.168.55.1', port=9090)
client.run()
print('connected:', client.is_connected)


def on_msg(m):
    print('GPS FROM ROBOT:', m['status']['status'], m['latitude'], m['longitude'])


topic = roslibpy.Topic(client, '/fix', 'sensor_msgs/msg/NavSatFix')
topic.subscribe(on_msg)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    topic.unsubscribe()
    client.terminate()
# ─── RANGER V3 END: 08-gps-ingest ───
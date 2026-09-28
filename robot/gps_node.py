# ─── RANGER V3 START: 08-gps-ingest ───
"""Reads NMEA from a serial port, publishes sensor_msgs/NavSatFix on /fix."""
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
import serial
import pynmea2


class GpsNode(Node):
    def __init__(self):
        super().__init__('gps_node')
        self.port = self.declare_parameter('port', '/dev/ttyTHS1').value
        self.baud = self.declare_parameter('baud', 9600).value
        self.frame_id = self.declare_parameter('frame_id', 'gps').value
        self.pub = self.create_publisher(NavSatFix, '/fix', 10)
        self.ser = serial.Serial(self.port, self.baud, timeout=0)
        self.buf = b''
        self.create_timer(0.05, self.tick)
        self.get_logger().info(f'reading {self.port} @ {self.baud}')

    def tick(self):
        n = self.ser.in_waiting
        if not n:
            return
        self.buf += self.ser.read(n)
        *lines, self.buf = self.buf.split(b'\n')
        for raw in lines:
            line = raw.decode('ascii', errors='replace').strip()
            if line.startswith(('$GPGGA', '$GNGGA')):
                self.handle_gga(line)

    def handle_gga(self, line):
        try:
            msg = pynmea2.parse(line)
        except pynmea2.ParseError:
            self.get_logger().warn(f'bad NMEA: {line}')
            return
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = self.frame_id
        fix.status.service = NavSatStatus.SERVICE_GPS
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        if msg.gps_qual and int(msg.gps_qual) > 0:
            fix.status.status = NavSatStatus.STATUS_FIX
            fix.latitude = msg.latitude
            fix.longitude = msg.longitude
            fix.altitude = float(msg.altitude) if msg.altitude not in (None, '') else math.nan
        else:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude = fix.longitude = fix.altitude = math.nan
        self.pub.publish(fix)
        self.get_logger().info(
            f'fix {fix.latitude:.6f}, {fix.longitude:.6f} status={fix.status.status}')


def main():
    rclpy.init()
    node = GpsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ser.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 08-gps-ingest ───

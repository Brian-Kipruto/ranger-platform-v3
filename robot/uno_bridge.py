# ─── RANGER V3 START: 14-uno-bridge ───
"""The only owner of the Uno's serial port (F14 5a, ADR-0021 seam).

    /ranger/cmd_vel  (geometry_msgs/Twist, normalised: see uno_protocol)  ->  M lines
    S lines  ->  /ranger/uno_status   (std_msgs/String, the raw S line)
    G lines  ->  /ranger/geiger_counts (std_msgs/UInt32)  [radiation_node count_source:=uno]

Stops, outermost first: cmd_vel stale for cmd_stale_s -> one M,0,0, then silence; the
Uno stops by itself 250 ms after the last M; the RC switch (SwA) decides whether M
lines drive at all.

    python3 uno_bridge.py --ros-args \\
      -p port:=/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_3433031323135171F0F0-if00

Parameters: port, baud (115200), max_pwm (120: blocks testing until the motor noise
fix, F14 5a), cmd_stale_s (0.25), send_hz (20.0), boot_wait_s (2.0: opening the port
resets the Uno; nothing is written while its bootloader runs).
"""
import time

import rclpy
import serial
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String, UInt32

from uno_protocol import CmdGate, parse_line, twist_to_pwm

DEFAULT_PORT = '/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_3433031323135171F0F0-if00'


class UnoBridge(Node):
    def __init__(self):
        super().__init__('uno_bridge')
        self.port = self.declare_parameter('port', DEFAULT_PORT).value
        baud = self.declare_parameter('baud', 115200).value
        self.max_pwm = self.declare_parameter('max_pwm', 120).value
        stale_s = self.declare_parameter('cmd_stale_s', 0.25).value
        send_hz = self.declare_parameter('send_hz', 20.0).value
        boot_wait_s = self.declare_parameter('boot_wait_s', 2.0).value

        self.gate = CmdGate(stale_s)
        self.status_pub = self.create_publisher(String, '/ranger/uno_status', 10)
        self.geiger_pub = self.create_publisher(UInt32, '/ranger/geiger_counts', 10)
        self.create_subscription(Twist, '/ranger/cmd_vel', self.on_cmd_vel, 10)

        self.ser = serial.Serial(self.port, baud, timeout=0)
        self.write_after = time.monotonic() + boot_wait_s
        self.buf = b''
        self.mode = None
        self.create_timer(0.01, self.read_tick)
        self.create_timer(1.0 / send_hz, self.send_tick)
        self.get_logger().info(
            f'{self.port} @ {baud}, max_pwm={self.max_pwm}, stale after {stale_s}s, '
            f'{send_hz} Hz, writes start in {boot_wait_s}s')

    def on_cmd_vel(self, msg):
        left, right = twist_to_pwm(msg.linear.x, msg.angular.z, self.max_pwm)
        self.gate.on_cmd(left, right, time.monotonic())

    def send_tick(self):
        now = time.monotonic()
        if now < self.write_after:
            return
        line = self.gate.tick(now)
        if line is None:
            return
        self.ser.write(line.encode('ascii'))
        if self.gate.stale_stop:
            age_ms = (now - self.gate.last) * 1000.0
            self.get_logger().info(f'cmd_vel stale {age_ms:.0f} ms: sent M,0,0')

    def read_tick(self):
        try:
            n = self.ser.in_waiting
        except OSError as exc:
            self.get_logger().fatal(f'{self.port}: {exc}')
            raise SystemExit(1)
        if not n:
            return
        self.buf += self.ser.read(n)
        *lines, self.buf = self.buf.split(b'\n')
        for raw in lines:
            line = raw.decode('ascii', errors='replace').strip()
            parsed = parse_line(line)
            if parsed is None:
                continue
            kind, value = parsed
            if kind == 'G':
                self.geiger_pub.publish(UInt32(data=value))
            else:
                self.status_pub.publish(String(data=line))
                if value['mode'] != self.mode:
                    self.get_logger().info(
                        f"uno mode {self.mode} -> {value['mode']}: rc_ok={value['rc_ok']} "
                        f"pwm={value['left']},{value['right']} m_age={value['m_age_ms']} ms "
                        f"rc_age={value['rc_age_ms']} ms")
                    self.mode = value['mode']


def main():
    rclpy.init()
    node = UnoBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            node.ser.write(b'M,0,0\n')
        except Exception:
            pass
        node.ser.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 14-uno-bridge ───

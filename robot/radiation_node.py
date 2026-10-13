# ─── RANGER V3 START: 13-sensor-sim ───
"""Publishes ranger_msgs/Radiation on /ranger/radiation at 1 Hz (F13, ADR-0020).

The Geiger seam: counts come from a COUNT SOURCE (sensor_sources.py), are
windowed into CPM, and go out labelled with that source's claim. Today the
only source is `sim` (the GM tube is dead), so every message says SIMULATED.
The real tube is a new COUNT_SOURCES entry plus `-p count_source:=<name>`;
nothing in this file changes.

    python3 radiation_node.py --ros-args -p count_source:=sim -p background_cpm:=30.0
    ros2 param set /radiation_node hotspot_cpm 400.0     # demo hot spot (a float!)
    ros2 param set /radiation_node hotspot_cpm 0.0       # back to background

Parameters: count_source (sim), background_cpm (30.0), hotspot_cpm (0.0),
window_s (60.0), usvh_per_cpm (NaN = no dose until the tube's factor is known).
"""
import math

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from ranger_msgs.msg import Radiation

from sensor_sources import COUNT_SOURCES, CpmWindow, radiation_fields

TICK_S = 1.0


class RadiationNode(Node):
    def __init__(self):
        super().__init__('radiation_node')
        name = self.declare_parameter('count_source', 'sim').value
        if name not in COUNT_SOURCES:
            raise SystemExit(f'count_source {name!r} unknown; have {sorted(COUNT_SOURCES)}')
        background = self.declare_parameter('background_cpm', 30.0).value
        self.declare_parameter('hotspot_cpm', 0.0)
        window_s = self.declare_parameter('window_s', 60.0).value
        self.usvh_per_cpm = self.declare_parameter('usvh_per_cpm', math.nan).value
        self.frame_id = self.declare_parameter('frame_id', 'geiger').value

        self.source = COUNT_SOURCES[name](node=self, background_cpm=background)
        self.window = CpmWindow(window_s=window_s, tick_s=TICK_S)
        self.add_on_set_parameters_callback(self.on_params)
        self.pub = self.create_publisher(Radiation, '/ranger/radiation', 10)
        self.create_timer(TICK_S, self.tick)
        self.get_logger().info(
            f'count_source={name} claim={self.source.claim} '
            f'background={background} CPM window={window_s}s')

    def on_params(self, params):
        for p in params:
            if p.name == 'hotspot_cpm':
                if p.value < 0:
                    return SetParametersResult(successful=False, reason='hotspot_cpm must be >= 0')
                self.source.hotspot_cpm = float(p.value)
                self.get_logger().info(f'hotspot_cpm={p.value}')
        return SetParametersResult(successful=True)

    def tick(self):
        self.window.add(self.source.counts(TICK_S))
        msg = Radiation()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        for field, value in radiation_fields(
                self.window.cpm(), self.usvh_per_cpm, self.source.claim).items():
            setattr(msg, field, value)
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = RadiationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 13-sensor-sim ───

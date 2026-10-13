# ─── RANGER V3 START: 13-sensor-sim ───
"""Sim-mode stand-ins for the SDS011 and the MPU6050 board (F13 sim parity).

Publishes, always labelled SIMULATED:
    /ranger/air_quality  ranger_msgs/AirQuality  1 Hz   (SDS011 rate)
    /ranger/imu_baro     ranger_msgs/ImuBaro     10 Hz  (ingest throttles to 5 Hz)

    python3 sensor_sim.py --ros-args -p site:=nairobi

Started by stack_up.sh in sim mode only. Live mode gets the real sensor
nodes (5c) instead; this file never runs on a live robot.
"""
import rclpy
from rclpy.node import Node
from ranger_msgs.msg import AirQuality, ImuBaro

from sensor_sources import SITE_ALTITUDE_M, SimAirQuality, SimImuBaro

IMU_DT_S = 0.1


class SensorSim(Node):
    def __init__(self):
        super().__init__('sensor_sim')
        site = self.declare_parameter('site', 'nairobi').value
        if site not in SITE_ALTITUDE_M:
            raise SystemExit(f'site {site!r} unknown; have {sorted(SITE_ALTITUDE_M)}')
        pm25_mean = self.declare_parameter('pm25_mean', 15.0).value
        self.aq = SimAirQuality(pm25_mean=pm25_mean)
        self.imu = SimImuBaro(altitude_m=SITE_ALTITUDE_M[site])
        self.aq_pub = self.create_publisher(AirQuality, '/ranger/air_quality', 10)
        self.imu_pub = self.create_publisher(ImuBaro, '/ranger/imu_baro', 10)
        self.create_timer(1.0, self.tick_aq)
        self.create_timer(IMU_DT_S, self.tick_imu)
        self.get_logger().info(f'site={site} pm25_mean={pm25_mean} (SIMULATED)')

    def _publish(self, pub, msg, frame_id, fields):
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = frame_id
        for field, value in fields.items():
            setattr(msg, field, value)
        pub.publish(msg)

    def tick_aq(self):
        self._publish(self.aq_pub, AirQuality(), 'sds011', self.aq.step())

    def tick_imu(self):
        self._publish(self.imu_pub, ImuBaro(), 'imu', self.imu.step(IMU_DT_S))


def main():
    rclpy.init()
    node = SensorSim()
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

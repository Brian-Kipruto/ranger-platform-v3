# ─── RANGER V3 START: 13-imu ───
"""10-DOF board -> ranger_msgs/ImuBaro on /ranger/imu_baro, 10 Hz (F13 5c).

MPU6050 (roll, pitch) + QMC5883L (heading) + BMP180 (pressure, altitude) on
I2C bus 7, header pins 3 (SDA) / 5 (SCL), VCC on pin 1 (3.3 V).

    python3 imu_node.py --ros-args -p bus:=7

Mount: ~/ranger/config/imu_mount.json (from robot/config/imu_mount.json) says
which sensor axes point forward/up. Missing -> the node refuses to start.

Heading: published as NaN until ~/ranger/config/mag_cal.json exists. The raw
(uncalibrated) heading is printed in the 1 Hz log line so you can see the
magnetometer respond; it never goes on the topic. See imu_math.py.

The MPU6050's I2C bypass (which puts the QMC5883L on the main bus) resets on
power-cycle, so it is set on every start.
"""
import math
import time

import rclpy
from rclpy.node import Node
from ranger_msgs.msg import ImuBaro

import imu_math as im

try:
    from smbus2 import SMBus
except ImportError:  # python3-smbus from apt: same calls used here
    from smbus import SMBus

BMP_WAIT_S = {0: 0.005, 1: 0.008, 2: 0.014, 3: 0.026}
RATE_HZ = 10
BARO_EVERY = 10  # ticks: pressure ~1 Hz, each read blocks ~30 ms at oss=3


class ImuNode(Node):
    def __init__(self):
        super().__init__('imu_node')
        bus = self.declare_parameter('bus', 7).value
        self.oss = self.declare_parameter('oss', 3).value
        cal_path = self.declare_parameter('mag_cal', '~/ranger/config/mag_cal.json').value
        mount_path = self.declare_parameter('mount', '~/ranger/config/imu_mount.json').value
        try:
            self.mount = im.load_mount(mount_path)
        except (OSError, ValueError, KeyError) as exc:
            raise SystemExit(f'imu mount: {exc}')
        self.frame_id = self.declare_parameter('frame_id', 'imu').value

        self.cal = im.load_mag_cal(cal_path)  # malformed file -> raises, node stops
        self.bus = SMBus(bus)
        self._init_chips()
        self.bmp_cal = im.Bmp180Cal.from_eeprom(
            self.bus.read_i2c_block_data(im.BMP_ADDR, 0xAA, 22))

        self.pressure_hpa = self.alt_m = math.nan
        self.tick_n = 0
        self.errors = 0
        self.pub = self.create_publisher(ImuBaro, '/ranger/imu_baro', 10)
        self.create_timer(1.0 / RATE_HZ, self.tick)
        state = f'calibrated ({cal_path})' if self.cal else 'NOT calibrated: yaw published as NaN'
        self.get_logger().info(
            f'bus {bus}: MPU6050 + QMC5883L + BMP180 ok · mount forward={self.mount.forward} '
            f'up={self.mount.up} · heading {state}')

    def _init_chips(self):
        b = self.bus
        who = b.read_byte_data(im.MPU_ADDR, 0x75)
        if who != im.MPU_WHO_AM_I:
            raise SystemExit(f'MPU6050 WHO_AM_I {who:#04x}, expected {im.MPU_WHO_AM_I:#04x}')
        b.write_byte_data(im.MPU_ADDR, 0x6B, 0x00)  # PWR_MGMT_1: wake
        time.sleep(0.05)
        b.write_byte_data(im.MPU_ADDR, 0x1A, 0x03)  # CONFIG: DLPF ~44 Hz
        b.write_byte_data(im.MPU_ADDR, 0x1C, 0x00)  # ACCEL_CONFIG: +-2 g
        b.write_byte_data(im.MPU_ADDR, 0x6A, 0x00)  # USER_CTRL: I2C master off
        b.write_byte_data(im.MPU_ADDR, 0x37, 0x02)  # INT_PIN_CFG: bypass on
        time.sleep(0.01)
        chip = b.read_byte_data(im.BMP_ADDR, 0xD0)
        if chip != im.BMP_CHIP_ID:
            raise SystemExit(f'BMP180 chip id {chip:#04x}, expected {im.BMP_CHIP_ID:#04x}')
        qmc = b.read_byte_data(im.QMC_ADDR, 0x0D)
        if qmc != im.QMC_CHIP_ID:
            raise SystemExit(f'QMC5883L id {qmc:#04x}, expected {im.QMC_CHIP_ID:#04x} (bypass not on?)')
        b.write_byte_data(im.QMC_ADDR, 0x0B, 0x01)  # SET/RESET period
        b.write_byte_data(im.QMC_ADDR, 0x09, 0x1D)  # OSR 512, 8 G, 50 Hz, continuous

    def _read_baro(self):
        b = self.bus
        b.write_byte_data(im.BMP_ADDR, 0xF4, 0x2E)
        time.sleep(0.005)
        t = b.read_i2c_block_data(im.BMP_ADDR, 0xF6, 2)
        _, b5 = im.bmp180_temperature((t[0] << 8) | t[1], self.bmp_cal)
        b.write_byte_data(im.BMP_ADDR, 0xF4, 0x34 + (self.oss << 6))
        time.sleep(BMP_WAIT_S[self.oss])
        r = b.read_i2c_block_data(im.BMP_ADDR, 0xF6, 3)
        up = ((r[0] << 16) | (r[1] << 8) | r[2]) >> (8 - self.oss)
        pa = im.bmp180_pressure_pa(up, b5, self.bmp_cal, self.oss)
        self.pressure_hpa, self.alt_m = pa / 100.0, im.altitude_m(pa)

    def tick(self):
        try:
            accel = im.decode_accel_g(self.bus.read_i2c_block_data(im.MPU_ADDR, 0x3B, 6))
            mag_block = self.bus.read_i2c_block_data(im.QMC_ADDR, 0x00, 7)
            if self.tick_n % BARO_EVERY == 0:
                self._read_baro()
        except OSError as exc:
            self.errors += 1
            if self.errors in (1, 10, 100) or self.errors % 1000 == 0:
                self.get_logger().warn(f'I2C read failed ({self.errors} so far): {exc}')
            return
        self.tick_n += 1

        mag = im.decode_mag(mag_block)
        roll, pitch, yaw, raw_heading = im.attitude(
            accel, mag, self.mount, self.cal,
            mag_overflow=bool(mag_block[6] & 0x02))  # STATUS OVL: field beyond range

        msg = ImuBaro()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        for k, v in im.imu_fields(roll, pitch, yaw, self.pressure_hpa, self.alt_m).items():
            setattr(msg, k, v)
        self.pub.publish(msg)

        if self.tick_n % RATE_HZ == 0:
            self.get_logger().info(
                f'roll {roll:+6.1f} pitch {pitch:+6.1f} · yaw {yaw:6.1f} · '
                f'heading_raw {raw_heading:6.1f} (uncalibrated, log only) · '
                f'mag {mag} · {self.pressure_hpa:7.2f} hPa {self.alt_m:7.1f} m')


def main():
    rclpy.init()
    node = ImuNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.bus.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 13-imu ───

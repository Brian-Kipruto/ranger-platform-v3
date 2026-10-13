# RANGER V3 - F13 (ADR-0020) - /ranger/imu_baro -> ImuBaroLog
# Field names are a contract with ranger_backend/ros_bridge/readings.py
# (test_msg_contract.py fails if they drift). NaN for any missing value.
string SOURCE_LIVE="live"
string SOURCE_SIMULATED="simulated"

std_msgs/Header header
float64 roll             # degrees
float64 pitch            # degrees
float64 yaw              # compass heading: degrees clockwise from MAGNETIC north, [0, 360)
float64 pressure_hpa     # hPa
float64 altitude_m       # metres, barometric
string source            # the robot's claim: SOURCE_LIVE or SOURCE_SIMULATED

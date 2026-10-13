# RANGER V3 - F13 (ADR-0020) - /ranger/air_quality -> AirQualityLog
# Field names are a contract with ranger_backend/ros_bridge/readings.py
# (test_msg_contract.py fails if they drift).
string SOURCE_LIVE="live"
string SOURCE_SIMULATED="simulated"

std_msgs/Header header
float64 pm25             # ug/m3, NaN if missing
float64 pm10             # ug/m3, NaN if missing
string source            # the robot's claim: SOURCE_LIVE or SOURCE_SIMULATED

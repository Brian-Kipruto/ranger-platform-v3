# RANGER V3 - F13 (ADR-0020) - /ranger/radiation -> RadiationLog
# Field names are a contract with ranger_backend/ros_bridge/readings.py
# (test_msg_contract.py fails if they drift).
string SOURCE_LIVE="live"
string SOURCE_SIMULATED="simulated"

std_msgs/Header header   # robot time of the count window's end
float64 cpm              # counts per minute
float64 dose_rate_usvh   # NaN if not computed
string source            # the robot's claim: SOURCE_LIVE or SOURCE_SIMULATED

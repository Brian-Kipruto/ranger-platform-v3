# ─── RANGER V3 START: 14-teleop ───
"""Forward console drive commands to the robot: channel layer -> rosbridge /ranger/cmd_vel.

One relay per robot, separate from ros_ingest (a crashed relay must not stop rows
landing, and ingest stays as F13 left it). It reads teleop_channel(robot.pk) and
publishes each fresh, valid command once. It never repeats or invents a command, so
when commands stop arriving, cmd_vel goes silent and uno_bridge stops the robot.

    python manage.py teleop_relay --robot RANGER-PRIME-001

Exit (Ctrl-C) publishes one zero Twist on the way out.
"""
import asyncio
import time
from collections import Counter

import roslibpy
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand, CommandError

from core.models import Robot
from ros_bridge.teleop import relay_one, teleop_channel, twist

REPORT_S = 5.0


class Command(BaseCommand):
    help = "Relay console teleop commands to the robot's /ranger/cmd_vel (rosbridge)."

    def add_arguments(self, parser):
        parser.add_argument("--robot", default="RANGER-PRIME-001")
        parser.add_argument("--host", default="192.168.55.1")
        parser.add_argument("--port", type=int, default=9090)
        parser.add_argument("--topic", default="/ranger/cmd_vel")
        parser.add_argument("--max-messages", type=int, default=0, help="tests: stop after N")

    def handle(self, *args, **opts):
        try:
            robot = Robot.objects.get(robot_id_str=opts["robot"])
        except Robot.DoesNotExist:
            raise CommandError(f"No robot with robot_id_str={opts['robot']!r}")
        channel = teleop_channel(robot.pk)

        client = roslibpy.Ros(host=opts["host"], port=opts["port"])
        try:
            client.run(timeout=10)
        except Exception as exc:
            raise CommandError(f"Cannot reach rosbridge at {opts['host']}:{opts['port']}: {exc}")
        topic = roslibpy.Topic(client, opts["topic"], "geometry_msgs/msg/Twist")
        topic.advertise()
        self.stdout.write(
            f"teleop_relay {robot.robot_id_str}: {channel} -> {opts['topic']} "
            f"via rosbridge {opts['host']}:{opts['port']}")

        counts = Counter()
        try:
            asyncio.run(self._loop(channel, topic, counts, opts["max_messages"]))
        except KeyboardInterrupt:
            pass
        finally:
            try:
                topic.publish(roslibpy.Message(twist(0.0, 0.0)))
                time.sleep(0.2)  # let the reactor flush the stop before closing
                topic.unadvertise()
            finally:
                client.terminate()
            self.stdout.write(f"teleop_relay stopped: {dict(counts)}")

    async def _loop(self, channel, topic, counts, max_messages):
        layer = get_channel_layer()
        publish = lambda t: topic.publish(roslibpy.Message(t))  # noqa: E731
        last_report = time.monotonic()
        handled = 0
        while not max_messages or handled < max_messages:
            outcome = await relay_one(layer, channel, publish, time.time)
            handled += 1
            if counts["sent"] == 0 and outcome == "sent":
                self.stdout.write("first command relayed")
            counts[outcome] += 1
            if outcome != "sent":
                self.stderr.write(f"dropped command: {outcome}")
            if time.monotonic() - last_report >= REPORT_S:
                self.stdout.write(f"relay counts: {dict(counts)}")
                last_report = time.monotonic()
# ─── RANGER V3 END: 14-teleop ───

# 017 — pytest dies at startup: ROS 2 on PYTHONPATH loads a Python 3.10 plugin into the 3.11 venv

*Date: 2026-08-03*

---

## What we saw

F10.1 CP5. First-ever `pytest` run in the repo, venv active:

```
$ pytest --create-db
Traceback (most recent call last):
  ...
  File ".../pluggy/_manager.py", line 416, in load_setuptools_entrypoints
    plugin = ep.load()
  File "/opt/ros/humble/lib/python3.10/site-packages/launch_testing/__init__.py", line 15
    from . import tools
  ...
  File "/opt/ros/humble/lib/python3.10/site-packages/launch/utilities/type_utils.py", line 29
    import yaml
ModuleNotFoundError: No module named 'yaml'
```

Zero tests collected. The traceback never touches RANGER code — it's entirely
inside `/opt/ros/humble/`.

## What caused it

Sourcing `/opt/ros/humble/setup.bash` (from `~/.bashrc`, for rover work) puts
ROS's site-packages on `PYTHONPATH`:

```
/opt/ros/humble/lib/python3.10/site-packages
```

`PYTHONPATH` is honoured **in addition to** the venv, so a Python 3.11 venv can
still see ROS's Python 3.10 packages.

pytest then auto-loads every installed `pytest11` setuptools entry point it can
find. ROS registers `launch_testing` as one. pytest imports it, the import chain
reaches `import yaml` — installed for ROS's interpreter, not in this venv — and
pytest exits before collecting anything.

Note this affects **pytest only**. `manage.py`, `runserver`, and `migrate` were
all fine throughout, because Django doesn't scan entry points.

## How we fixed it

Clear `PYTHONPATH` for the pytest process:

```bash
cd ~/projects/ranger-platform-v3/ranger_backend
PYTHONPATH= pytest
```

48 tests collected, all passing.

Durable version — an alias:

```bash
echo "alias rpytest='PYTHONPATH= pytest'" >> ~/.bashrc
```

Alternative considered: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, which blocks ROS's
plugin — but also blocks `pytest-django`, so it must then be loaded explicitly
(`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p pytest_django`). More precise, more
typing. The alias won.

## How to prevent it

Check `echo "$PYTHONPATH"` first whenever a Python tool fails with an import
error naming a path you didn't expect. If it mentions `/opt/ros/`, that's this.

**Carry-forward — this gets harder at F08/F09.** Today ROS is only a nuisance on
the path. When the `ros_bridge` app stops being a stub and needs real `rclpy`,
we'll have ROS built for Python 3.10 and the backend venv on 3.11, and "just
source ROS inside the venv" will not work. The options — a separate bridge
process communicating over MQTT/WebSocket, a matched interpreter version, or a
containerized bridge — are an architectural decision for the F08 spec, not a
workaround to improvise later.

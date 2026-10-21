# 038 — `gemini2.launch.py` SyntaxError at line 47

*Date: 2026-10-19*

---

## What we saw

```
File ".../orbbec_camera/launch/gemini2.launch.py", line 47
    DeclareLaunchArgument('color_denoising_level', default_value='-1')
SyntaxError: invalid syntax. Perhaps you forgot a comma?
```

on `ros2 launch orbbec_camera gemini2.launch.py --show-args`, with the source tree
clean (`git status` empty) at `9b69bbfa` on `v2-main`.

## The cause

An upstream bug: line 47 of the launch file (the `color_denoising_level` argument)
lacks its trailing comma. The install copy is a plain file (no `--symlink-install`),
built from the same source, so it carries the bug too.

## The fix

A one-character local patch, applied to `src/` and copied to `install/` (no rebuild
of a package that otherwise works), guarded so it only touches the right line:

```bash
F=~/ros2_ws/src/OrbbecSDK_ROS2/orbbec_camera/launch/gemini2.launch.py
I=~/ros2_ws/install/orbbec_camera/share/orbbec_camera/launch/gemini2.launch.py
cmp "$F" "$I" && sed -n 47p "$F" | grep -q color_denoising_level \
  && sed -i '47s/)[[:space:]]*$/),/' "$F" \
  && python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$F" \
  && cp "$F" "$I"
```

sha256 `a61077c5…` on both copies. Recorded in F14's install record. The first
attempt targeted line 46 (an off-by-one reading a `sed -n 40,48p` listing) and
changed nothing; the line guard and the parse check exist because of it.

## Prevention

- `stack_up.sh` refuses to start video if the installed launch file doesn't parse —
  a re-pull or rebuild without the patch fails at preflight, not mid-start.
- Pin and record the commit of any vendored ROS package you patch.

#!/usr/bin/env python3
"""Live viewfinder with a focus slider and a live sharpness number.

Built because the two instruments we had each answered half the question. The
sweep script measures well but shows nothing, so a null result is hard to trust;
the camera app shows a picture but is somebody else's program, and its preview is
scaled far enough down to hide a modest change in sharpness. This does both at
once and owns the whole path, so nothing else can touch the camera or the lens
while it runs.

There is no autofocus here and nothing to disable: the only thing that ever
writes the focus control is the slider.

The sharpness number is the same metric focus-sweep.py uses - mean squared
gradient between same-colour neighbours over a centred crop - so a reading here
can be compared with one from there.
"""
import os
import subprocess
import sys
import threading

import numpy as np

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GLib, GdkPixbuf  # noqa: E402

import fcntl
import struct

WIDTH, HEIGHT = 4032, 3024
ROW_BYTES = WIDTH * 10 // 8
FRAME_BYTES = ROW_BYTES * HEIGHT
CROP_W, CROP_H = 1024, 768
PREVIEW_WIDTH = 640       # roughly how many pixels wide the on-screen image is
MAX_ZOOM = 16.0           # at 16x one screen pixel is one sensor pixel

# The sensor is mounted rotated 270 degrees on this board (the device tree says
# so), so the raw frame arrives on its side. Rotating by 90 puts it upright.
DEFAULT_ROTATE = 1        # quarter-turns counter-clockwise

# Linear sensor values look far too dark on a display, which expects roughly
# sRGB-encoded data. One 256-entry table costs nothing per frame.
GAMMA_LUT = (255.0 * (np.arange(256) / 255.0) ** (1 / 2.2)).astype(np.uint8)

VIDIOC_S_CTRL = 0xc008561c
VIDIOC_G_CTRL = 0xc008561b
V4L2_CID_FOCUS_ABSOLUTE = 0x009a090a
CAMSS_SINKS = ('msm_csiphy0', 'msm_csid0', 'msm_ispif0', 'msm_vfe0_rdi0')

# Column indices of the high byte of each pixel. The frame is MIPI-packed
# 10-bit: four pixels in five bytes, the fifth holding their low bits. Dropping
# it costs two bits and makes everything here an 8-bit array operation.
_cols = np.arange(ROW_BYTES)
HIGH_COLS = _cols[_cols % 5 != 4]


def find_lens_subdev():
    for entry in sorted(os.listdir('/dev')):
        if not entry.startswith('v4l-subdev'):
            continue
        path = '/dev/' + entry
        try:
            out = subprocess.run(['v4l2-ctl', '-d', path, '-l'],
                                 capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if 'focus_absolute' in out:
            return path
    return None


def focus_range(subdev):
    out = subprocess.run(['v4l2-ctl', '-d', subdev, '-l'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'focus_absolute' in line:
            lo = hi = None
            for f in line.split():
                if f.startswith('min='):
                    lo = int(f[4:])
                elif f.startswith('max='):
                    hi = int(f[4:])
            if lo is not None and hi is not None:
                return lo, hi
    raise SystemExit('focus_absolute has no min/max')


def setup_pipeline(media='/dev/media0'):
    """Without this STREAMON fails -EPIPE from a cold boot."""
    fmt = '[fmt:SRGGB10_1X10/%dx%d]' % (WIDTH, HEIGHT)
    for e in CAMSS_SINKS:
        subprocess.run(['media-ctl', '-d', media, '-V', "'%s':0 %s" % (e, fmt)],
                       check=True, capture_output=True)


class Focus:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)

    def set(self, v):
        fcntl.ioctl(self.fd, VIDIOC_S_CTRL,
                    struct.pack('Ii', V4L2_CID_FOCUS_ABSOLUTE, int(v)))

    def get(self):
        b = fcntl.ioctl(self.fd, VIDIOC_G_CTRL,
                        struct.pack('Ii', V4L2_CID_FOCUS_ABSOLUTE, 0))
        return struct.unpack('Ii', b)[1]


class Camera(threading.Thread):
    """Keep only the newest frame.

    Python cannot keep up with the sensor, so the pipe would otherwise build a
    queue and the picture would lag the slider by seconds - which is exactly the
    kind of delay that makes a real effect look like no effect.
    """

    daemon = True

    def __init__(self, video='/dev/video0'):
        super().__init__()
        self.proc = subprocess.Popen(
            ['v4l2-ctl', '-d', video,
             '--set-fmt-video=width=%d,height=%d,pixelformat=pRAA' % (WIDTH, HEIGHT),
             '--stream-mmap=3', '--stream-count=100000', '--stream-to=-'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.latest = None
        self.lock = threading.Lock()
        self.frames = 0

    def run(self):
        while True:
            buf = bytearray(FRAME_BYTES)
            view = memoryview(buf)
            got = 0
            while got < FRAME_BYTES:
                n = self.proc.stdout.readinto(view[got:])
                if not n:
                    return
                got += n
            with self.lock:
                self.latest = bytes(buf)
                self.frames += 1

    def take(self):
        with self.lock:
            f, self.latest = self.latest, None
            return f


def demosaic(a, x0, y0, vw, vh, step):
    """Turn the raw Bayer window into a small RGB image.

    The sensor is SRGGB10: a repeating 2x2 quad of R, G, G, B. Taking one quad
    per output pixel is the cheapest correct demosaic there is - half the linear
    resolution of the window, no interpolation, and no false colour, which is
    what a viewfinder needs. Anything better would cost more per frame than the
    whole rest of this program.

    Grey-world white balance follows, because raw RGGB is strongly green and the
    picture is otherwise unrecognisable, and then gamma, because sensor data is
    linear and a display is not.
    """
    ys = slice(y0, y0 + vh, step)
    ys1 = slice(y0 + 1, y0 + vh, step)
    cr = HIGH_COLS[x0:x0 + vw:step]
    cg = HIGH_COLS[x0 + 1:x0 + vw:step]
    n = min(len(cr), len(cg))
    cr, cg = cr[:n], cg[:n]

    r = a[ys][:, cr]
    g1 = a[ys][:, cg]
    g2 = a[ys1][:, cr]
    b = a[ys1][:, cg]
    h = min(r.shape[0], g2.shape[0])
    r, g1, g2, b = r[:h], g1[:h], g2[:h], b[:h]

    g = ((g1.astype(np.uint16) + g2) // 2).astype(np.uint8)

    gm = float(g.mean()) or 1.0
    rm = float(r.mean()) or 1.0
    bm = float(b.mean()) or 1.0
    r = np.clip(r.astype(np.float32) * (gm / rm), 0, 255).astype(np.uint8)
    b = np.clip(b.astype(np.float32) * (gm / bm), 0, 255).astype(np.uint8)

    rgb = np.dstack((r, g, b))
    return GAMMA_LUT[rgb]


def analyse(frame, zoom=1.0):
    """Return (preview 2-D uint8, sharpness, mean) for the zoomed-in region.

    Zoom is a centred crop, not a resample: at 1x the whole frame is decimated
    down to screen size, at 16x a screen pixel is a sensor pixel. Decimating
    throws away exactly the fine detail that focus changes, so a lens that moves
    a little can be invisible at 1x and obvious at 8x - which is the point of
    having this control at all.

    The sharpness number is measured over the *visible* region at full
    resolution, so the number and the picture always describe the same thing.
    """
    a = np.frombuffer(frame, np.uint8).reshape(HEIGHT, ROW_BYTES)

    zoom = max(1.0, min(MAX_ZOOM, zoom))
    vw = max(64, int(WIDTH / zoom)) & ~3
    vh = max(64, int(HEIGHT / zoom)) & ~3
    # Both origins must be even, or the 2x2 Bayer quad below lands on the wrong
    # phase and the colours come out swapped.
    x0 = ((WIDTH - vw) // 2) & ~1
    y0 = ((HEIGHT - vh) // 2) & ~1

    step = max(1, (vw // PREVIEW_WIDTH)) & ~1 or 2
    preview = demosaic(a, x0, y0, vw, vh, step)

    # Sharpness over the centre of what is on screen, at full resolution.
    cw = min(CROP_W, vw)
    ch = min(CROP_H, vh)
    cx = x0 + (vw - cw) // 2
    cy = y0 + (vh - ch) // 2
    crop = a[cy:cy + ch][:, HIGH_COLS[cx:cx + cw]].astype(np.int16)
    # Same-colour neighbours: raw Bayer puts a different colour plane next door,
    # so comparing x with x+1 would measure the scene's colour, not focus.
    d = crop[:, :-2] - crop[:, 2:]
    return preview, float((d.astype(np.int32) ** 2).mean()), float(crop.mean())


def main():
    subdev = find_lens_subdev()
    if not subdev:
        raise SystemExit('no subdev exposes focus_absolute - is the driver bound?')
    lo, hi = focus_range(subdev)
    focus = Focus(subdev)
    setup_pipeline()
    cam = Camera()
    cam.start()

    app = Gtk.Application(application_id='org.fp3.FocusView')

    def on_activate(a):
        win = Gtk.ApplicationWindow(application=a, title='Focus view')
        win.set_default_size(360, 640)
        # On a phone the compositor gives the window the whole screen, so the
        # window must never *demand* more than it is given: anything wider is
        # simply cut off, controls first, with no scrollbar to reveal it.
        win.maximize()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + m)(8)

        pic = Gtk.Picture()
        pic.set_vexpand(True)
        pic.set_can_shrink(True)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        box.append(pic)

        # ☠️ Two labels, wrapping, and no size="large". As one long tnum line
        # this readout was wider than the screen on its own and pushed the
        # sliders off the right-hand edge - which looks like a broken app, not
        # like a layout that asked for 900 px.
        readout = Gtk.Label()
        readout.set_wrap(True)
        readout.set_justify(Gtk.Justification.CENTER)
        readout.set_markup('<span font_features="tnum">waiting for a frame…</span>')
        box.append(readout)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        scale.set_value(focus.get())
        scale.set_draw_value(False)
        for m in (lo, (lo + hi) // 2, hi):
            scale.add_mark(m, Gtk.PositionType.BOTTOM, str(m))
        box.append(scale)

        state = {'pos': focus.get(), 'zoom': 1.0, 'n': 0,
                 'rotate': DEFAULT_ROTATE}

        def on_change(s):
            state['pos'] = int(s.get_value())
            try:
                focus.set(state['pos'])
            except OSError as e:
                readout.set_markup('<span color="red">write failed: %s</span>' % e)
            return False

        scale.connect('value-changed', on_change)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.set_homogeneous(True)
        for name, val in (('%d' % lo, lo), ('%d' % ((lo + hi) // 2), (lo + hi) // 2),
                          ('%d' % hi, hi)):
            b = Gtk.Button(label=name)
            b.connect('clicked', lambda _b, v=val: scale.set_value(v))
            row.append(b)
        box.append(row)

        # Focus is sharp over a narrow band of the range, so the slider alone is
        # too coarse to sit on the peak: one pixel of travel is several counts.
        fine = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fine.set_homogeneous(True)
        for label, delta in (('−10', -10), ('−1', -1), ('+1', 1), ('+10', 10)):
            b = Gtk.Button(label=label)
            b.connect('clicked', lambda _b, d=delta:
                      scale.set_value(max(lo, min(hi, scale.get_value() + d))))
            fine.append(b)
        box.append(fine)

        zoom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        zoom_label = Gtk.Label()
        zoom_label.set_markup('<span font_features="tnum">zoom 1.0x</span>')
        zoom_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                              1.0, MAX_ZOOM, 0.1)
        zoom_scale.set_value(1.0)
        zoom_scale.set_draw_value(False)
        zoom_scale.set_hexpand(True)
        for m in (1, 4, 8, 16):
            zoom_scale.add_mark(m, Gtk.PositionType.BOTTOM, '%dx' % m)

        def on_zoom(s_):
            state['zoom'] = s_.get_value()
            zoom_label.set_markup('<span font_features="tnum">zoom %.1fx</span>'
                                  % state['zoom'])
            return False

        zoom_scale.connect('value-changed', on_zoom)
        zoom_row.append(zoom_label)
        zoom_row.append(zoom_scale)
        rot = Gtk.Button(label='rotate')

        def do_rotate(_b):
            state['rotate'] = (state['rotate'] + 1) % 4

        rot.connect('clicked', do_rotate)
        zoom_row.append(rot)
        box.append(zoom_row)

        # Pinch as well as the slider: on a phone the slider is fiddly with the
        # hand that is also holding the target still.
        pinch = Gtk.GestureZoom.new()

        def on_pinch_begin(_g, _s):
            state['pinch_base'] = state['zoom']

        def on_pinch(_g, scale_delta):
            base = state.get('pinch_base', state['zoom'])
            zoom_scale.set_value(max(1.0, min(MAX_ZOOM, base * scale_delta)))

        pinch.connect('begin', on_pinch_begin)
        pinch.connect('scale-changed', on_pinch)
        pic.add_controller(pinch)

        def tick():
            frame = cam.take()
            if frame is None:
                return True
            preview, sharp, mean = analyse(frame, state['zoom'])
            rgb = np.ascontiguousarray(np.rot90(preview, state['rotate']))
            h, w = rgb.shape[:2]
            pb = GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(rgb.tobytes()), GdkPixbuf.Colorspace.RGB,
                False, 8, w, h, w * 3)
            pic.set_pixbuf(pb)
            state['n'] += 1
            readout.set_markup(
                '<span font_features="tnum">'
                'focus %4d   zoom %4.1fx\n'
                'sharpness %.1f   brightness %.1f   frames %d'
                '</span>' % (state['pos'], state['zoom'], sharp, mean,
                             cam.frames))
            return True

        GLib.timeout_add(120, tick)
        win.set_child(box)
        win.present()

    app.connect('activate', on_activate)
    app.run([])


if __name__ == '__main__':
    main()

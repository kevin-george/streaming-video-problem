#!/usr/bin/env python3

import sys
import gi
import numpy as np
import cv2

gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib, GObject

SERVER_IP = "127.0.0.1"
RTSP_PORT = "5051"
MOUNT_POINT = "/come-and-get-it"
RTSP_URL = f"rtsp://{SERVER_IP}:{RTSP_PORT}{MOUNT_POINT}"

# OpenCV Red Detection HSV Range (Tune these values for your specific lighting/camera)
# Red wraps around 0/180 in HSV, so we need two ranges
LOWER_RED_1 = np.array([0, 100, 100])    # Lower bound for Hue=0 range
UPPER_RED_1 = np.array([10, 255, 255])   # Upper bound for Hue=0 range
LOWER_RED_2 = np.array([160, 100, 100])  # Lower bound for Hue=180 range
UPPER_RED_2 = np.array([179, 255, 255])  # Upper bound for Hue=180 range (OpenCV Hue max is 179)
MIN_CONTOUR_AREA = 500 # Minimum area to consider a contour as an object

pipeline = None
appsrc = None
textoverlay = None
loop = None
# State for FPS calculation
fps_probe_state = {'prev_pts': Gst.CLOCK_TIME_NONE, 'current_fps': 0.0}
# Store caps from appsink to configure appsrc
last_caps = None

def process_frame_opencv(frame):
    """Detects red objects and draws rectangles."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Create masks for red ranges
    mask1 = cv2.inRange(hsv, LOWER_RED_1, UPPER_RED_1)
    mask2 = cv2.inRange(hsv, LOWER_RED_2, UPPER_RED_2)
    mask = cv2.bitwise_or(mask1, mask2)

    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Draw rectangles around significant contours
    for contour in contours:
        if cv2.contourArea(contour) > MIN_CONTOUR_AREA:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2) # Draw green rectangle

    return frame

def on_new_sample(appsink):
    """Callback function for the appsink's 'new-sample' signal."""
    global appsrc, last_caps
    sample = appsink.emit("pull-sample")
    if sample:
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        if caps is None:
            print("Warning: No caps found on sample", file=sys.stderr)
            return Gst.FlowReturn.OK # Keep processing

        # Store caps if they change (needed for appsrc)
        if last_caps is None or not caps.is_equal(last_caps):
             print(f"Updating appsrc caps to: {caps.to_string()}")
             last_caps = caps
             if appsrc:
                 appsrc.set_caps(last_caps) # Configure appsrc

        # Get buffer map and image dimensions
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            print("Error: Failed to map buffer", file=sys.stderr)
            return Gst.FlowReturn.ERROR

        # Get dimensions from caps structure
        struct = caps.get_structure(0)
        height = struct.get_value("height")
        width = struct.get_value("width")

        # Wrap buffer data in NumPy array (assuming BGR format from videoconvert)
        frame = np.ndarray(
            (height, width, 3), # Shape (check channels based on format)
            buffer=map_info.data,
            dtype=np.uint8
        )

        processed_frame = process_frame_opencv(frame.copy()) # Process a copy

        if appsrc is not None:
            # Create a new Gst.Buffer from the processed NumPy array
            # Use tobytes() for contiguous data
            new_buffer = Gst.Buffer.new_wrapped(processed_frame.tobytes())

            # Copy timestamps and other metadata
            new_buffer.pts = buffer.pts
            new_buffer.dts = buffer.dts
            new_buffer.duration = buffer.duration
            new_buffer.offset = buffer.offset

            # Emit the buffer through appsrc
            retval = appsrc.emit("push-buffer", new_buffer)
            if retval != Gst.FlowReturn.OK:
                 print(f"Warning: appsrc push-buffer returned {retval}", file=sys.stderr)

        # Unmap the original buffer
        buffer.unmap(map_info)

        return Gst.FlowReturn.OK
    return Gst.FlowReturn.ERROR


def fps_probe_callback(pad, info, user_data):
    """ Callback function for the buffer probe to calculate FPS """
    global fps_probe_state, textoverlay
    buffer = info.get_buffer()
    if buffer is None or textoverlay is None: # Check if textoverlay is available
        return Gst.PadProbeReturn.OK

    current_pts = buffer.pts # Presentation timestamp in nanoseconds

    if fps_probe_state['previous_pts'] != Gst.CLOCK_TIME_NONE:
        delta_ns = current_pts - fps_probe_state['prev_pts']
        fps = 1_000_000_000 / delta_ns  # Assuming monotonically increasing clock
        fps_probe_state['current_fps'] = fps
    else:
        # Initial state
        fps_probe_state['current_fps'] = 0.0

    # Update previous PTS for next calculation
    fps_probe_state['prev_pts'] = current_pts

    fps_display_text = f"FPS: {fps_probe_state['current_fps']:.1f}"
    try:
        # Update the text property of the textoverlay element
        textoverlay.set_property("text", fps_display_text)
    except Exception as e:
        print(f"Error setting textoverlay property: {e}", file=sys.stderr)

    return Gst.PadProbeReturn.OK # Let the buffer pass through

def on_pad_added(element, pad, target_sink_pad):
    """Handles dynamically added pads from decodebin"""
    print(f"Dynamic pad '{pad.get_name()}' added by '{element.get_name()}'")
    if pad.is_linked():
        print("Pad already linked. Ignoring.")
        return
    caps = pad.get_current_caps()
    struct = caps.get_structure(0)
    name = struct.get_name()
    if name.startswith("video/x-raw"):
        print(f"Linking video pad to {target_sink_pad.get_parent().get_name()}'s sink pad")
        ret = pad.link(target_sink_pad)
        if ret != Gst.PadLinkReturn.OK:
            print(f"ERROR: Failed to link decodebin video pad: {ret}", file=sys.stderr)
    else:
         print(f"Ignoring non-raw-video pad: {name}")

def main():
    global pipeline, appsrc, textoverlay, loop

    # Initialize GStreamer
    Gst.init(sys.argv[1:] if len(sys.argv) > 1 else None)

    # Create a GLib Main Loop
    loop = GLib.MainLoop()

    pipeline = Gst.Pipeline.new("opencv-consumer-pipeline")
    if not pipeline:
        print("ERROR: Could not create pipeline.", file=sys.stderr)
        sys.exit(1)

    # Input elements
    rtspsrc = Gst.ElementFactory.make("rtspsrc", "rtspsrc-source")
    decodebin = Gst.ElementFactory.make("decodebin", "decoder")
    videoconvert_in = Gst.ElementFactory.make("videoconvert", "convert-in")
    appsink = Gst.ElementFactory.make("appsink", "opencv-sink")

    # Output elements
    appsrc = Gst.ElementFactory.make("appsrc", "opencv-source")
    videoconvert_out = Gst.ElementFactory.make("videoconvert", "convert-out")
    identity_probe = Gst.ElementFactory.make("identity", "probe-point")
    textoverlay = Gst.ElementFactory.make("textoverlay", "fps-overlay") # Assign to global
    videosink = Gst.ElementFactory.make("autovideosink", "display-sink")

    if not all([pipeline, rtspsrc, decodebin, videoconvert_in, appsink,
                appsrc, videoconvert_out, identity_probe, textoverlay, videosink]):
        print("ERROR: Not all elements could be created.", file=sys.stderr)
        sys.exit(1)

    rtspsrc.set_property("location", RTSP_URL)
    rtspsrc.set_property("latency", 100) # Buffer latency

    # Configure appsink: request BGR format, emit signals for new samples
    appsink_caps = Gst.Caps.from_string("video/x-raw,format=BGR")
    appsink.set_property("caps", appsink_caps)
    appsink.set_property("emit-signals", True)
    appsink.set_property("max-buffers", 1) # Process one buffer at a time
    appsink.set_property("drop", True)     # Drop old buffers if processing is slow
    appsink.connect("new-sample", on_new_sample)

    # Configure appsrc: stream type, time format (important!)
    appsrc.set_property("stream-type", GstApp.AppStreamType.STREAM)
    appsrc.set_property("format", Gst.Format.TIME)
    # appsrc caps will be set dynamically based on appsink caps
    appsrc.set_property("is-live", True)
    appsrc.set_property("do-timestamp", True) # Let appsrc handle timestamps if needed? No, copy manually.

    # Configure textoverlay
    textoverlay.set_property("font-desc", "Sans, 24")
    textoverlay.set_property("valignment", "top")
    textoverlay.set_property("halignment", "left")

    # Configure final sink
    videosink.set_property("sync", False)

    pipeline.add(rtspsrc)
    pipeline.add(decodebin)
    pipeline.add(videoconvert_in)
    pipeline.add(appsink)
    pipeline.add(appsrc)
    pipeline.add(videoconvert_out)
    pipeline.add(identity_probe)
    pipeline.add(textoverlay)
    pipeline.add(videosink)

    print("Linking static elements...")
    # Input pipeline part 1 (rtspsrc -> decodebin)
    if not rtspsrc.link(decodebin):
        print("ERROR: Could not link rtspsrc to decodebin.", file=sys.stderr)
        sys.exit(1)

    # Input pipeline part 2 (videoconvert -> appsink) - decodebin links here dynamically
    convert_in_sinkpad = videoconvert_in.get_static_pad("sink")
    if not videoconvert_in.link(appsink):
         print("ERROR: Could not link videoconvert_in to appsink.", file=sys.stderr)
         sys.exit(1)

    # Output pipeline (appsrc -> ... -> videosink)
    if not appsrc.link(videoconvert_out):
         print("ERROR: Could not link appsrc to videoconvert_out.", file=sys.stderr)
         sys.exit(1)
    if not videoconvert_out.link(identity_probe):
         print("ERROR: Could not link videoconvert_out to identity_probe.", file=sys.stderr)
         sys.exit(1)
    if not identity_probe.link(textoverlay):
         print("ERROR: Could not link identity_probe to textoverlay.", file=sys.stderr)
         sys.exit(1)
    if not textoverlay.link(videosink):
         print("ERROR: Could not link textoverlay to videosink.", file=sys.stderr)
         sys.exit(1)

    # Connect the 'pad-added' signal from decodebin to our handler
    # Pass the sink pad of the next element (videoconvert_in) as user data
    decodebin.connect("pad-added", on_pad_added, convert_in_sinkpad)

    probe_pad = identity_probe.get_static_pad("src")
    if not probe_pad:
        print("ERROR: Could not get src pad of identity_probe", file=sys.stderr)
        sys.exit(1)
    probe_pad.add_probe(Gst.PadProbeType.BUFFER, fps_probe_callback, None) # Pass None initially, textoverlay is global
    print("FPS probe added successfully")

    # Add a bus watcher to handle messages
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message, loop)

    print("Starting pipeline...")
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("ERROR: Unable to set the pipeline to the playing state.", file=sys.stderr)
        pipeline.set_state(Gst.State.NULL)
        sys.exit(1)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("Ctrl+C pressed, stopping...")
    finally:
        print("Stopping pipeline...")
        pipeline.set_state(Gst.State.NULL)
        print("Pipeline stopped")

def on_message(bus, message, loop):
    """ Callback for messages on the pipeline bus """
    mtype = message.type
    if mtype == Gst.MessageType.EOS:
        print("End-of-stream reached.")
        loop.quit()
    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error received from element {message.src.get_name()}: {err.message}", file=sys.stderr)
        print(f"Debugging information: {debug if debug else 'none'}", file=sys.stderr)
        loop.quit()
    elif mtype == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(f"Warning received from element {message.src.get_name()}: {err.message}", file=sys.stderr)
        print(f"Debugging information: {debug if debug else 'none'}", file=sys.stderr)
    elif mtype == Gst.MessageType.STATE_CHANGED:
         # We are only interested in state-changed messages from the pipeline
        if message.src == Gst.Element.get_parent(message.src): # Check if source is the pipeline
             old_state, new_state, pending_state = message.parse_state_changed()
             print(f"Pipeline state changed from {Gst.Element.state_get_name(old_state)} to {Gst.Element.state_get_name(new_state)}")
    # else:
    #     print(f"Received message of type {mtype} from {message.src.get_name()}")

    return True # Continue watching for messages


if __name__ == '__main__':
    main()

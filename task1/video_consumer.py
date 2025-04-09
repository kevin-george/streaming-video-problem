#!/usr/bin/env python3

import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

SERVER_IP = "127.0.0.1"
RTSP_PORT = "5051"
MOUNT_POINT = "/come-and-get-it"
RTSP_URL = f"rtsp://{SERVER_IP}:{RTSP_PORT}{MOUNT_POINT}"

# rtspsrc handles connection and receiving RTP data
# It automatically handles depayloading based on SDP negotiation,
# so we often don't need rtph264depay explicitly *immediately* after it,
# but we need a decoder. Using decodebin is robust.
RTSP_SOURCE_ELEMENT = f"rtspsrc location={RTSP_URL} latency=100" # latency helps buffer
DECODE_ELEMENT = "decodebin" # Automatically selects appropriate depayloader/decoder
# Identity element to attach probe for FPS calculation
PROBE_IDENTITY_ELEMENT = "identity name=probe_point"
VIDEO_CONVERT_ELEMENT = "videoconvert"
# Text overlay element to display FPS
TEXT_OVERLAY_ELEMENT = "textoverlay name=cons_fps_overlay font-desc=\"Sans, 24\" valignment=top halignment=left"
VIDEO_SINK_ELEMENT = "autovideosink sync=false" # This element displays the video

# Probe Callback to overlay frame rate onto the image
def probe_callback(_, info, user_data):
    """ Callback function for the buffer probe """
    probe_state, textoverlay_element = user_data # Unpack user data
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK # Ignore empty buffers

    current_pts_ns = buffer.pts # Presentation timestamp in nanoseconds

    if probe_state['previous_pts'] != Gst.CLOCK_TIME_NONE:
        delta_ns = current_pts_ns - probe_state['previous_pts']
        fps = 1_000_000_000 / delta_ns # Assuming monotonically increasing clock
        probe_state['current_fps'] = fps
    else:
        # Initial state
        probe_state['current_fps'] = 0.0

    # Update previous PTS for next calculation
    probe_state['previous_pts'] = current_pts_ns

    fps_display_text = f"Consumer FPS: {probe_state['current_fps']:.1f}"

    try:
        # Update the text property of the textoverlay element
        textoverlay_element.set_property("text", fps_display_text)
    except Exception as e:
        print(f"Error setting textoverlay property: {e}", file=sys.stderr)

    return Gst.PadProbeReturn.OK # Let the buffer pass through

def main():
    # Initialize GStreamer
    Gst.init(sys.argv[1:] if len(sys.argv) > 1 else None)

    # Using decodebin simplifies handling different payload types negotiated via RTSP
    pipeline_str = (
        f"{RTSP_SOURCE_ELEMENT} ! "
        f"{DECODE_ELEMENT} ! "
        f"{PROBE_IDENTITY_ELEMENT} ! " # Probe point after decoding
        f"{VIDEO_CONVERT_ELEMENT} ! "
        f"{TEXT_OVERLAY_ELEMENT} ! "   # Overlay FPS
        f"{VIDEO_SINK_ELEMENT}"
    )
    print(f"Using pipeline: {pipeline_str}")
    pipeline = Gst.parse_launch(pipeline_str)

    # Check if pipeline creation was successful
    if not pipeline:
        print("ERROR: Could not create pipeline.", file=sys.stderr)
        sys.exit(1)

    # Add the probe for FPS calculation
    try:
        probe_element = pipeline.get_by_name("probe_point")
        if not probe_element:
            raise Exception("Could not get 'probe_point' element")

        textoverlay = pipeline.get_by_name("cons_fps_overlay")
        if not textoverlay:
            raise Exception("Could not get 'cons_fps_overlay' element")

        pad = probe_element.get_static_pad("src")
        if not pad:
            raise Exception("Could not get src pad of 'probe_point'")

        # State dictionary to store previous PTS and current FPS
        probe_state = {'previous_pts': Gst.CLOCK_TIME_NONE, 'current_fps': 0.0}
        # Pass state and overlay element to the callback
        probe_user_data = (probe_state, textoverlay)

        pad.add_probe(Gst.PadProbeType.BUFFER, probe_callback, probe_user_data)
        print("FPS probe added successfully")

    except Exception as e:
        print(f"ERROR: Failed to setup FPS probe: {e}", file=sys.stderr)

    # Create a GLib Main Loop
    loop = GLib.MainLoop()

    # Add a bus watcher to handle messages
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message, loop)

    print("Starting pipeline...")
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("ERROR: Unable to set the pipeline to the playing state", file=sys.stderr)
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

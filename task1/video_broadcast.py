#!/usr/bin/env python3

import sys
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# Define the video source
SOURCE_ELEMENT = "v4l2src device=/dev/video0"

# Encoding and RTP payloading settings
ENCODER_ELEMENT = "x264enc tune=zerolatency bitrate=1000 speed-preset=medium"
RTP_PAYLOADER_ELEMENT = "rtph264pay name=pay0 pt=96" # name=pay0 is important

# Text Overlay Settings
TEXT_OVERLAY_ELEMENT = "textoverlay name=broad_fps_overlay font-desc=\"Sans, 24\" valignment=bottom halignment=left"

# RTSP Server Settings
RTSP_PORT = "5051"
MOUNT_POINT = "/come-and-get-it" # Clients will connect to rtsp://<server_ip>:5051/come-and-get-it

# Probe Callback to overlay frame rate onto the image
def probe_callback(_, info, user_data):
    probe_state, textoverlay_element = user_data # Unpack user data
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK # Ignore empty buffers

    current_pts_ns = buffer.pts # Presentation timestamp in nanoseconds

    if probe_state['previous_pts'] != Gst.CLOCK_TIME_NONE:
        delta_ns = current_pts_ns - probe_state['previous_pts']
        fps = 1_000_000_000 / delta_ns # Assuming monotonically increasing clock
        probe_state['current_fps'] = fps # Store calculated FPS
    else:
        # Initial state
        probe_state['current_fps'] = 0.0

    # Update previous PTS for next calculation
    probe_state['previous_pts'] = current_pts_ns

    fps_display_text = f"Broadcast FPS: {probe_state['current_fps']:.1f}"

    try:
        # Update the text property of the textoverlay element
        textoverlay_element.set_property("text", fps_display_text)
    except Exception as e:
        print(f"Error setting textoverlay property: {e}", file=sys.stderr)

    return Gst.PadProbeReturn.OK # Let the buffer pass through

# This factory creates the GStreamer pipeline for each client connection
class RtspStreamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(RtspStreamFactory, self).__init__(**properties)
        # This is because a new pipeline per client would cause contention over the single device
        self.set_shared(True)

    def do_create_element(self, _):
        # Define the pipeline string with overlay and identity element for probe
        # Convert to RGB before textoverlay, then back to I420 for encoder
        pipeline_str = (
            f"{SOURCE_ELEMENT} ! "
            f"queue ! " # Add queue for thread decoupling
            f"videoconvert ! "
            f"video/x-raw,format=RGB ! " # Convert to RGB for textoverlay
            f"identity name=probe_point ! " # Element to attach probe to
            f"{TEXT_OVERLAY_ELEMENT} ! "
            f"videoconvert ! " # Convert back to I420 for encoder
            f"video/x-raw,format=I420 ! "
            f"{ENCODER_ELEMENT} ! "
            f"{RTP_PAYLOADER_ELEMENT}"
        )
        print(f"Creating pipeline: {pipeline_str}")
        pipeline_bin = Gst.parse_launch(pipeline_str)

        if not pipeline_bin:
            print("ERROR: Could not create pipeline bin", file=sys.stderr)
            return None # Return None on failure
        
        # Add the probe
        try:
            # Get the identity element where the probe will be attached
            probe_element = pipeline_bin.get_by_name("probe_point")
            if not probe_element:
                print("ERROR: Could not get 'probe_point' element", file=sys.stderr)
                return None

            # Get the textoverlay element to pass its reference to the probe
            textoverlay = pipeline_bin.get_by_name("broad_fps_overlay")
            if not textoverlay:
                print("ERROR: Could not get 'broad_fps_overlay' element", file=sys.stderr)
                return None

            # Get the source pad of the identity element
            pad = probe_element.get_static_pad("src")
            if not pad:
                print("ERROR: Could not get src pad of 'probe_point'", file=sys.stderr)
                return None

            # State dictionary to store previous PTS and current FPS
            probe_state = {'previous_pts': Gst.CLOCK_TIME_NONE, 'current_fps': 0.0}
            # Pass state and overlay element to the callback
            probe_user_data = (probe_state, textoverlay)

            # Gst.ProbeType.BUFFER ensures we probe when a buffer passes and also is non-blocking
            # probe_callback is the function to execute
            # textoverlay is passed as user_data to the callback
            pad.add_probe(Gst.PadProbeType.BUFFER, probe_callback, probe_user_data)

            print("New pipeline created successfully")

        except Exception as e:
             print(f"ERROR: Failed to setup probe: {e}", file=sys.stderr)
             return None # Return None if probe setup fails

        return pipeline_bin # Return the fully configured Gst.Bin

# --- Main Server Logic ---
def main():
    # Initialize GStreamer
    Gst.init(sys.argv[1:] if len(sys.argv) > 1 else None)

    # Create a GLib Main Loop
    loop = GLib.MainLoop()

    # Create an RTSP server instance
    server = GstRtspServer.RTSPServer()
    server.set_service(RTSP_PORT)

    # Get the default mount points object
    mounts = server.get_mount_points()

    # Create an instance of our media factory
    stream_factory = RtspStreamFactory()

    # Add the factory to the mount points, defining the URL path
    mounts.add_factory(MOUNT_POINT, stream_factory)

    # Attach the server to the default GLib main context
    server.attach(None)

    server_address = server.get_address() or "localhost" # Get bound address if possible
    print(f"RTSP server ready at rtsp://{server_address}:{RTSP_PORT}{MOUNT_POINT}")
    print("Streaming pipeline template:")
    print(f" {SOURCE_ELEMENT} ! videoconvert ! video/x-raw,format=I420 ! {ENCODER_ELEMENT} ! {RTP_PAYLOADER_ELEMENT}")

    try:
        print("Starting server loop (Ctrl+C to stop)...")
        loop.run()
    except KeyboardInterrupt:
        print("Ctrl+C pressed, stopping server...")
    finally:
        # Cleanup happens automatically when loop exits?
        # Explicitly removing mount points might be needed in complex scenarios
        print("Server stopped.")

if __name__ == '__main__':
    main()

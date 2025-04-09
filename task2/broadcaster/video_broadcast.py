#!/usr/bin/env python3

import sys
import time
import argparse
import requests
import json
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# Encoding and RTP payloading settings
ENCODER_ELEMENT = "x264enc tune=zerolatency bitrate=1000 speed-preset=medium"
RTP_PAYLOADER_ELEMENT = "rtph264pay name=pay0 pt=96" # name=pay0 is important

# Text Overlay Settings
TEXT_OVERLAY_ELEMENT = "textoverlay name=broad_fps_overlay font-desc=\"Sans, 24\" valignment=bottom halignment=left"

# RTSP Server Settings
RTSP_PORT = "5051"

DISCOVERY_SERVER_URL = "http://127.0.0.1:5000"

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

def register_broadcaster(broadcaster_id, server_address):
    endpoint = f"{DISCOVERY_SERVER_URL}/broadcasts"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "broadcaster_id": broadcaster_id,
        "stream_url": f"rtsp://{server_address}:{RTSP_PORT}{broadcaster_id}"
    }
    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        broadcast_data = response.json()
        print("Broadcaster registration successful!")
        print("Response Body:")
        print(json.dumps(broadcast_data, indent=4))
    except requests.exceptions.RequestException as e:
        print(f"Error registering broadcaster: {e}")
        if response is not None:
            print(f"Status Code: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error Details: {json.dumps(error_data, indent=4)}")
            except json.JSONDecodeError:
                print(f"Error Response Text: {response.text}")
        return None
    
def deregister_broadcaster(broadcaster_id):
    endpoint = f"{DISCOVERY_SERVER_URL}/broadcasts/{broadcaster_id}"
    try:
        response = requests.delete(endpoint)
        response.raise_for_status()
        print(f"\nSuccessfully deleted broadcaster: {broadcaster_id}")
    except requests.exceptions.RequestException as e:
        print(f"Error deleting broadcaster {broadcaster_id}: {e}")
        if response is not None:
            print(f"Status Code: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error Details: {json.dumps(error_data, indent=4)}")
            except json.JSONDecodeError:
                print(f"Error Response Text: {response.text}")

# This factory creates the GStreamer pipeline for each client connection
class RtspStreamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, args, **properties):
        super(RtspStreamFactory, self).__init__(**properties)
        self.args = args
        # This is because a new pipeline per client would cause contention over the single device
        self.set_shared(True)

    def do_create_element(self, _):
        # Define the pipeline string with overlay and identity element for probe
        # Convert to RGB before textoverlay, then back to I420 for encoder
        if self.args.src_type == 'webcam':
            pipeline_str = (
                f"v4l2src device={self.args.src} ! "
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
            print(f"Creating a webcam pipeline for client: {pipeline_str}")
            pipeline_bin = Gst.parse_launch(pipeline_str)
        elif self.args.src_type == 'disk':
            # Create a bin to hold the elements for this client
            pipeline_bin = Gst.Bin.new(f"file-pipeline-{int(time.time())}")

            # Create elements manually
            filesrc = Gst.ElementFactory.make("filesrc", "file-source")
            decodebin = Gst.ElementFactory.make("decodebin", "decoder")
            queue = Gst.ElementFactory.make("queue", "queue")
            videoconvert_rgb = Gst.ElementFactory.make("videoconvert", "convert-rgb")
            identity_probe = Gst.ElementFactory.make("identity", "probe_point")
            textoverlay = Gst.ElementFactory.make("textoverlay", "broad_fps_overlay")
            videoconvert_i420 = Gst.ElementFactory.make("videoconvert", "convert-i420")
            encoder = Gst.ElementFactory.make("x264enc", "encoder")
            payloader = Gst.ElementFactory.make("rtph264pay", "payloader")

            if not all([filesrc, decodebin, queue, videoconvert_rgb, identity_probe,
                        textoverlay, videoconvert_i420, encoder, payloader]):
                print("ERROR: Failed to create one or more elements for file source", file=sys.stderr)
                return None

            # Configure elements
            filesrc.set_property("location", self.args.src)
            textoverlay.set_property("font-desc", "Sans, 24")
            textoverlay.set_property("valignment", "bottom")
            textoverlay.set_property("halignment", "left")
            # Configure encoder/payloader if needed (using defaults from top)
            encoder.set_property("tune", "zerolatency")
            encoder.set_property("bitrate", 1000)
            encoder.set_property("speed-preset", "medium")
            payloader.set_property("name", "pay0")
            payloader.set_property("pt", 96)
            payloader.set_property("config-interval", 1)

            # Add elements to the bin
            pipeline_bin.add(filesrc)
            pipeline_bin.add(decodebin)
            pipeline_bin.add(queue)
            pipeline_bin.add(videoconvert_rgb)
            pipeline_bin.add(identity_probe)
            pipeline_bin.add(textoverlay)
            pipeline_bin.add(videoconvert_i420)
            pipeline_bin.add(encoder)
            pipeline_bin.add(payloader)

            # Link static parts: filesrc -> decodebin
            if not filesrc.link(decodebin):
                print("ERROR: Could not link filesrc to decodebin", file=sys.stderr)
                return None

            # Link static parts: queue -> ... -> payloader
            if not Gst.Element.link_many(queue, videoconvert_rgb, identity_probe, textoverlay,
                                         videoconvert_i420, encoder, payloader):
                 print("ERROR: Could not link elements from queue onwards", file=sys.stderr)
                 return None

            # Define and connect pad-added handler for decodebin
            queue_sink_pad = queue.get_static_pad("sink") # Get sink pad for linking
            if not queue_sink_pad:
                 print("ERROR: Could not get queue sink pad.", file=sys.stderr)
                 return None

            def on_pad_added_for_file(element, pad, target_pad):
                """Nested handler to link decodebin's dynamic pad."""
                print(f"Dynamic pad '{pad.get_name()}' added by '{element.get_name()}'")
                if pad.is_linked():
                    print("Pad already linked.")
                    return
                caps = pad.query_caps(None) # Check caps
                if caps and caps.to_string().startswith("video/x-raw"):
                    print(f"Linking video pad to queue sink...")
                    ret = pad.link(target_pad)
                    if ret != Gst.PadLinkReturn.OK:
                        print(f"ERROR: Failed to link decodebin video pad: {ret}", file=sys.stderr)
                else:
                    print(f"Ignoring non-raw-video pad: {caps.to_string() if caps else 'None'}")

            decodebin.connect("pad-added", on_pad_added_for_file, queue_sink_pad)
        else:
            print(f"ERROR: Unsupported src_type '{self.args.src_type}'", file=sys.stderr)
            return None

        # Common logic for all source types: Add the probe
        if pipeline_bin:
            try:
                probe_element = pipeline_bin.get_by_name("probe_point")
                textoverlay_element = pipeline_bin.get_by_name("broad_fps_overlay")
                pad = probe_element.get_static_pad("src")

                if not probe_element or not textoverlay_element or not pad:
                     raise Exception("Could not get probe/overlay elements or pad")
                
                # State dictionary to store previous PTS and current FPS
                probe_state = {'previous_pts': Gst.CLOCK_TIME_NONE, 'current_fps': 0.0}
                # Pass state and overlay element to the callback
                probe_user_data = (probe_state, textoverlay_element)

                # Gst.ProbeType.BUFFER ensures we probe when a buffer passes and also is non-blocking
                pad.add_probe(Gst.PadProbeType.BUFFER, probe_callback, probe_user_data)
                print("New pipeline created successfully")

            except Exception as e:
                print(f"ERROR: Failed to setup probe: {e}", file=sys.stderr)

        return pipeline_bin # Return the Gst.Bin or Gst.Pipeline

def main():
    parser = argparse.ArgumentParser(description="Video Broadcaster with configurable source")
    parser.add_argument("--broadcaster_id", required=True, help="A unique name for the broadcaster e.g. live_from_toronto")
    parser.add_argument("--src_type", required=True, choices=['webcam', 'disk'],
                        help="Type of video source ('webcam' or 'disk')")
    parser.add_argument("--src", required=True,
                        help="Source specific details (e.g., '/dev/video0' for webcam, '/path/to/video.mp4' for disk)")
    args = parser.parse_args()
    
    # Initialize GStreamer
    Gst.init(None)

    # Create a GLib Main Loop
    loop = GLib.MainLoop()

    # Create an RTSP server instance
    server = GstRtspServer.RTSPServer()
    server.set_service(RTSP_PORT)

    # Get the default mount points object
    mounts = server.get_mount_points()

    # Create an instance of our media factory
    stream_factory = RtspStreamFactory(args)

    # Add the factory to the mount points, defining the URL path
    mounts.add_factory(args.broadcaster_id, stream_factory)

    # Attach the server to the default GLib main context
    server.attach(None)

    server_address = server.get_address() or "localhost" # Get bound address if possible
    print(f"RTSP server ready at rtsp://{server_address}:{RTSP_PORT}{args.broadcaster_id}")
    print(f"Using source type: {args.src_type}, source: {args.src}")

    # Time to register this broadcaster with the discovery server
    register_broadcaster(args.broadcaster_id, server_address)

    try:
        print("Starting server loop (Ctrl+C to stop)...")
        loop.run()
    except KeyboardInterrupt:
        print("Ctrl+C pressed, stopping server...")
    finally:
        # Time to de-register this broadcaster with the discovery server
        deregister_broadcaster(args.broadcaster_id)
        print("Server stopped")

if __name__ == '__main__':
    main()
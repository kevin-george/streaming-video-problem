# Task 1

- This problem needs an architecture that can scale easily in performance. In order to avoid the GIL issues, I started with a prototype using ROS2(which internally uses multiprocessing) but quickly saw the better alternative in Gstreamer as it's purpose built for video streaming pipelines. In order to make this usable over a network/cloud, I've chosen RTSP as the protocol to serve the stream over.
- The pipeline architecture of Gstreamer is highly optimized as it's written in C and supports most codecs. The only disadvantage I can see is having to figure out the intricacies of the framework but that's what the weekend's for, right?
- There will be two scripts, one for broadcasting the video stream from webcam and another for consuming the stream to display it. Multiple instances of the second script can be used.

## Installation on Ubuntu 24.10

```
# GStreamer Core & Plugins
sudo apt install \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-rtsp \
    libgstreamer-plugins-base1.0-dev -y

# GObject Introspection & Python Bindings
sudo apt install \
    python3-gi \
    python3-gst-1.0 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gst-rtsp-server-1.0 \
    gir1.2-glib-2.0 -y

# Dependencies needed to run video_consumer_with_opencv.py
sudo apt install python3-opencv python3-numpy -y

# Ensure your user has access to webcam device
sudo usermod -aG video $USER
```

## Usage of scripts
```
python3 video_broadcast.py # This creates a broadcaster so a single instance is needed
    
python3 video_consumer.py
OR
python3 video_consumer_with_opencv.py 
```
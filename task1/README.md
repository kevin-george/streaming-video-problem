# Task 1

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
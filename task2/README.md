# Task 2

- I'm continuing to use the Gstreamer design from Task 1
- In order to handle many broadcasters & consumers in a scalable manner, I've chosen to go with a webserver design. 
    - This allows each broadcaster to handle it's own source and let's consumers query which broadcasters are available choose which of them they'd like to subscribe to. 
    - The reliance on the stream URL for broadcasters should help with the scalability and let gstreamer continue to handle pipelines like it was designed to. 
- Since there isn't a need for bi-directional streaming, other alternatives like gRPC or websockets weren't considered.

## Usage of discovery server
Run the following commands to setup & start the discovery server

```
    cd discovery/
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    
    python3 app.py
```

## Usage of broadcasters
Run the following command to start the broadcaster. Create more instances as needed
```
    cd broadcaster/
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    
    python3 video_broadcast.py --src_type=webcam --src=/dev/video0
    OR
    python3 video_broadcast.py --src_type=disk --src=/home/kevin/sample_vid.mp4
```

## Usage of consumers
```
    cd consumer/
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    
    python3 video_consumer.py
    OR
    python3 video_consumer.py --broadcaster_id=broadcast-abc-123
```

## Further development
1. How do we handle stale consumers that registered but don't consume the stream anymore?
2. Do we need to rate-limit consumers or can we assume good faith actors?
3. How do we handle authentication?
4. Versioning of APIs

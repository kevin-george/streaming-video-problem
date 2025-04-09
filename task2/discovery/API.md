## API endpoints of discovery server

1. Register a broadcast - `/broadcasts` POST method
    
    a. Request
    ```
    {
        "broadcaster_id": "user123", // Identifier of the broadcaster
        "stream_url": "rtsp://<server_ip>:5051/come-and-get-it" // URL for the video stream
    }
    ```
    b. Response - Returns Success & replaces silently if there's a duplicate registration
    ```
    {
        "broadcaster_id": "user123",
        "stream_url": "rtsp://<server_ip>:5051/come-and-get-it",
        "status": "active", // or "inactive", etc.
        "created_at": "2025-04-08T16:01:38Z"
    }
    ```
    c. Test using
    ```
    curl -X POST -H "Content-Type: application/json" -d '{"broadcaster_id": "user123", "stream_url": "rtsp://127.0.0.1:5051/come-and-get-it"}' http://127.0.0.1:5000/broadcasts
    ```


2. Delete a broadcast - `/broadcasts/{broadcaster_id}` DELETE method

    a. Returns Not Found if the broadcast hasn't been registered yet
    ```
    {
        "error": "Broadcast not found"
    }
    ```

    b. Returns Success otherwise
    ```
    {
    }
    ```

    c. Test using
    ```
    curl -X DELETE http://127.0.0.1:5000/broadcasts/the-unique-identifier
    ```

3. List all active broadcasts -  `/broadcasts` GET method
   
    a. Always Returns Success
    ```
    [
        {
            "broadcaster_id": "user123",
            "stream_url": "rtsp://<server_ip>:5051/come-and-get-it",
            "status": "active",
            "created_at": "2025-04-08T16:01:38Z"
        },
        {
            "broadcaster_id": "user789",
            "stream_url": "rtsp://<server_ip>:5051/whos-a-goodboy",
            "status": "active",
            "created_at": "2025-04-08T15:00:00Z"
        }
        // ... more subscribed broadcasts
    ]
    ```

    b. Test using
    ```
    curl http://127.0.0.1:5000/broadcasts
    ```
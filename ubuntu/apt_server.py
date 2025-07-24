'''
apt_server.py

This module provides a simple HTTP server for serving Debian packages from a specified directory.
The server is built using Python's built-in `http.server` and `socketserver` modules, and it can
be run in a separate thread to allow for concurrent operations.
'''
import http.server
import socketserver
import threading
import os
import socket
from color_logger import logger


class AptServer:
    def __init__(self, port=8000, directory="debian_packages", max_retries=10):
        """
        Initialize the AptServer with configuration parameters.

        Args:
        -----
        - port (int, optional): Starting port number to attempt. Defaults to 8000.
        - directory (str, optional): Directory containing Debian packages to serve.
                                     Defaults to "debian_packages".
        - max_retries (int, optional): Maximum number of port retries before failing.
                                       Defaults to 10.
        """
        self.port = port
        self.directory = directory
        self.max_retries = max_retries

    def start(self):
        """
        Start the HTTP server in a separate daemon thread.

        Attempts to start the server, incrementing the port number if the current
        port is in use. Will attempt up to max_retries different ports before failing.

        Returns:
        --------
        - threading.Thread: The thread running the server (running as daemon)

        Raises:
        -------
        - RuntimeError: If server could not be started after max_retries attempts
        - Exception: For any non-port-related errors during server startup
        """

        for attempt in range(self.max_retries):
            self.port = self.port + 1
            try:
                handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=self.directory, **kwargs)
                httpd = socketserver.TCPServer(("", self.port), handler)
                logger.debug(f"Serving {self.directory} as HTTP on port {self.port}...")
                server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                server_thread.start()
                return server_thread
            except OSError as e:
                print(e)
                if isinstance(e, socket.error) or "Address already in use" in str(e):
                    logger.warning(f"Port {self.port} is in use. Retrying... ({attempt + 1}/{self.max_retries})")
                else:
                    raise Exception(e)

        raise RuntimeError(f"Could not start server on port {self.port} after {self.max_retries} retries.")

import os

# Keep OpenCV's internal probing messages out of the console/log
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

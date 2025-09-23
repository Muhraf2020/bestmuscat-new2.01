import os
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
RUN_DISCOVERY = os.getenv("RUN_DISCOVERY", "false").lower() == "true"

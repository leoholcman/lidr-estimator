import os

# Los tests no llaman a ningún proveedor: basta con una key de mentira.
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

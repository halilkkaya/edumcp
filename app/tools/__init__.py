from importlib import import_module

tool_modules = [
    "quiz_generator",
    "pdf_summarizer",
    "video_summarizer",
    "audio_transcriber"
]

for module_name in tool_modules:
    try:
        import_module(f"app.tools.{module_name}")
    except ImportError as e:
        print(f"Tool modülü yüklenemedi: {module_name} - {e}") 
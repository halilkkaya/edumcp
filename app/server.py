# education_mcp/app/server.py
import os
import importlib.util
from flask import Flask, request, jsonify
from app.config import GEMINI_API_KEY

app = Flask(__name__)

REGISTERED_TOOLS = {}

def load_tools():
    tools_dir = os.path.join(os.path.dirname(__file__), 'tools')
    for filename in os.listdir(tools_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            file_path = os.path.join(tools_dir, filename)

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for item_name in dir(module):
                item = getattr(module, item_name)
                if callable(item) and not item_name.startswith('__'):
                    REGISTERED_TOOLS[item_name] = item
                    print(f"Registered tool: {item_name}")

@app.route('/execute_tool', methods=['POST'])
def execute_tool():
    data = request.json
    tool_name = data.get('tool_name')
    args = data.get('args', {})

    if tool_name not in REGISTERED_TOOLS:
        return jsonify({"error": f"Tool '{tool_name}' not found."}), 404

    tool_function = REGISTERED_TOOLS[tool_name]
    try:
        result = tool_function(**args)
        return jsonify({"result": result}), 200
    except TypeError as e:
        return jsonify({"error": f"Invalid arguments for tool '{tool_name}': {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred during tool execution: {e}"}), 500

@app.route('/')
def index():
    return "Education MCP Server is running!"

if __name__ == '__main__':
    load_tools()
    app.run(debug=True, port=5000)

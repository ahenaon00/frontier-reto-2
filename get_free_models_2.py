import urllib.request
import json
req = urllib.request.Request('https://openrouter.ai/api/v1/models')
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    gemini_free = [m['id'] for m in data['data'] if m['pricing']['prompt'] == '0' and 'gemini' in m['id']]
    print("Gemini:", gemini_free)
    llama_free = [m['id'] for m in data['data'] if m['pricing']['prompt'] == '0' and 'llama' in m['id']]
    print("Llama:", llama_free)
    qwen_free = [m['id'] for m in data['data'] if m['pricing']['prompt'] == '0' and 'qwen' in m['id']]
    print("Qwen:", qwen_free)

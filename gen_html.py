import json
import codecs

with open(r'/mnt/c/Users/andres/.gemini/antigravity/brain/2ae463c2-0f5e-45ab-9485-8280e921ddcd/plan_arquitectura.md', 'r', encoding='utf-8') as f:
    markdown = f.read()

# safely pass the markdown to JS via json dumps
js_string = json.dumps(markdown)

html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Plan de Arquitectura</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 40px; }}
        h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
        pre, code {{ background-color: #f6f8fa; border-radius: 6px; }}
        pre {{ padding: 16px; overflow: auto; }}
        .mermaid {{ text-align: center; margin: 2em 0; }}
        @media print {{ body {{ padding: 0; max-width: 100%; }} }}
    </style>
</head>
<body>
    <div id="content"></div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: false }});
        
        const markdown = {js_string};
        
        const renderer = new marked.Renderer();
        const originalCode = renderer.code.bind(renderer);
        renderer.code = (code, language) => {{
            if (language === 'mermaid') {{
                return '<div class="mermaid">' + code + '</div>';
            }}
            return originalCode(code, language);
        }};
        marked.use({{ renderer }});
        
        document.getElementById('content').innerHTML = marked.parse(markdown);
        mermaid.run({{ querySelector: '.mermaid' }});
    </script>
</body>
</html>
'''

with codecs.open(r'/mnt/c/Users/andres/Downloads/frontier-reto-2/Plan_Arquitectura.html', 'w', encoding='utf-8') as f:
    f.write(html)

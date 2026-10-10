import json
import codecs

markdown = """# Arquitectura: El Genio Matemático (Zero-Knowledge)

## 1. El Desafío y las Restricciones
Nos enfrentamos a un servicio tipo "caja negra" con estrictas restricciones de uso (Rate-Limits). **No sabemos cuáles son las reglas** de validación, ni sabemos **qué va a pasar** en el futuro si los operadores del servicio deciden cambiar el formato, añadir nuevos campos o alterar la matemática oculta.

Si nuestro sistema intentara descubrir cómo funciona el servicio enviando cientos de peticiones aleatorias (fuzzing masivo) para ver qué responde, agotaríamos nuestra cuota de la API inmediatamente y sobrecargaríamos su servidor.

## 2. Decisiones Arquitectónicas (El "Por Qué")
Para resolver esto de forma segura e inteligente, la arquitectura se basa en **Inducción Pura y Offloading Local**.

*   **Cero Asunciones (Zero-Knowledge):** No pre-programaremos ninguna regla humana (como "los controles son de dos dígitos"). La Inteligencia Artificial actúa como un analista criptográfico: solo recibe datos crudos (lo que entró y lo que salió con éxito) y debe deducir todo el patrón desde cero.
*   **Protección del Servidor Real:** El 99% del razonamiento (crear hipótesis, formular matemáticas, fallar y reescribir) ocurre **100% de forma local** en nuestra memoria. La IA usa nuestro historial de éxitos para validar sus teorías matemáticas sin tocar la red. Esto garantiza que no sobrecargamos la caja negra mientras la IA aprende.
*   **Pruebas Quirúrgicas:** Solo cuando la IA está matemáticamente segura de que su fórmula replica toda la historia conocida, se le autoriza hacer 1 o 2 peticiones a la Caja Negra con casos nunca antes vistos para confirmar la teoría.
*   **Aprendizaje Reactivo:** Si el servidor rechaza la prueba, significa que hay un patrón oculto que desconocemos. En lugar de iterar contra el servidor bombardeándolo, el sistema detiene la red, incorpora el nuevo fracaso a su conocimiento local y vuelve a la fase de pizarrón (explorar alternativas lógicas).

## 3. Diagrama de Flujo (Bucle Inductivo)

`mermaid
flowchart TD
    A[(Dataset Crudo\\nCasos Exitosos Conocidos)] --> B[1. IA: Inferencia Matemática Pura]
    B -->|Genera Fórmula Python| C{2. Sandbox Local\\n¿Pasa el 100% del dataset?}
    C -->|Falla (Replantea Matemática)| B
    C -->|Pasa (Alta Confianza)| D(3. Inventa 2 Casos Inéditos)
    D --> E{4. Petición Quirúrgica\\n(Red Real)}
    E -->|ÉXITO: Teoría Comprobada| F[5. Despliega Lógica Descubierta]
    E -->|FALLO: El patrón real difiere| G[6. Exploración de Alternativas]
    G -->|Añade la Excepción al Dataset| A
`

## 4. Beneficios del Enfoque
1. **Conservación de Rate-Limits:** Minimizamos al máximo las peticiones HTTPS. Resolvemos el puzzle en casa.
2. **Resiliencia al Cambio:** Si las reglas cambian mañana, el agente está diseñado para dudar. Al recibir el primer fallo, automáticamente tomará las respuestas válidas recientes y re-descubrirá el nuevo patrón, sin necesidad de reprogramación humana.
3. **Inmunidad a Alucinaciones:** Al obligar a la IA a pasar un test estricto local antes de hacer peticiones reales, filtramos cualquier lógica "alucinada" o incorrecta desde la raíz.
"""

js_string = json.dumps(markdown)

html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Arquitectura: Genio Matemático</title>
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
    <div id="content">Cargando documento...</div>
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

with codecs.open(r'/mnt/c/Users/andres/Downloads/frontier-reto-2/Documento_Genio_Matematico.html', 'w', encoding='utf-8') as f:
    f.write(html)

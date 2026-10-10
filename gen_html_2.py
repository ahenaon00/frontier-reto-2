import json
import codecs

markdown = """# Arquitectura del Agente Deductor (Enfoque Científico)

En lugar de saturar el servicio real con cientos de peticiones a ciegas, hemos cambiado el enfoque hacia un **Bucle de Hipótesis y Verificación Offline**. El Agente actuará como un científico o matemático: deducirá las fórmulas basándose estrictamente en los ejemplos exitosos que ya poseemos, probará su código localmente, y solo usará la red para comprobar mutaciones específicas.

## Diagrama del Flujo Científico

`mermaid
flowchart TD
    A[(Casos Exitosos Conocidos)] --> B[1. Agente IA: Genera Hipótesis Matemática]
    B -->|Escribe 'motor_hash.py'| C{2. Verificación Local}
    C -->|Falla en replicar éxitos| B
    C -->|Pasa 100%| D[3. Generación de Mutaciones]
    D -->|Peticiones Quirúrgicas| E(Caja Negra Real)
    E --> F{4. Respuesta de API}
    F -->|Error Controlado| G[5. Documentar Regla de Validación]
    F -->|Fallo Inesperado| B
    G --> H[(Servidor Réplica Actualizado)]
`

## Las Dos Fases del Agente

### Fase 1: Anclaje de Éxito (Zero-Cost)
El LLM recibe nuestros pares de *Input -> Output* comprobados.
Su misión es escribir un algoritmo en Python (motor_hash.py) que produzca **exactamente** esas mismas salidas. Este proceso ocurre en un bucle cerrado (Verificación Local). No se dispara ni una sola petición a la API real hasta que el agente logre un "ajuste perfecto" para los casos que sabemos que son correctos.

### Fase 2: Exploración de Fronteras
Una vez que el algoritmo local es capaz de imitar a la perfección el comportamiento positivo del servicio, el Agente empieza a deformar deliberadamente las peticiones para entender los bordes del sistema.
Ejemplos de mutaciones:
- Vaciar argumentos intencionalmente (Buscando entender qué dispara E104).
- Enviar tipos de datos erróneos o símbolos prohibidos (Buscando entender E201).
- Enviar un formato correcto pero con una matemática desfasada a propósito (Buscando entender E202).

## Ecosistema Desplegado
Para que este agente pueda operar de forma autónoma, el entorno se divide en tres componentes:
1. **motor_hash.py (El Cerebro)**: Contiene la lógica matemática (Semillas, Hash Horner). Es el **único** archivo que el Agente reescribirá automáticamente cuando descubra un nuevo patrón.
2. **servidor.py (La Capa API)**: Un servidor web FastAPI que envuelve al cerebro y lo expone como una API REST idéntica a la Caja Negra.
3. **cli.py (La Sonda)**: Interfaz de terminal para que tanto nosotros como el Agente disparemos pruebas contra la réplica y comparemos resultados cómodamente.
"""

js_string = json.dumps(markdown)

html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Plan: Agente Científico</title>
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

with codecs.open(r'/mnt/c/Users/andres/Downloads/frontier-reto-2/Plan_Agente_Cientifico.html', 'w', encoding='utf-8') as f:
    f.write(html)

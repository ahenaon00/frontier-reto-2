import json
import codecs

markdown = """# Arquitectura de Despliegue: Réplica Autónoma y Agente Matemático

Esta documentación define la estructura física y topológica del sistema. Separamos la "Fuerza Bruta" (el servidor de producción) del "Cerebro" (el agente que infiere reglas), garantizando máxima seguridad, alta disponibilidad y latencia cero.

## 1. Topología del Sistema (Estructura Dockerizada)

El ecosistema se divide en **tres componentes principales** montados mediante Docker:

### A. Volumen Compartido (La Memoria Persistente)
Un almacenamiento en disco que enlaza ambos contenedores. Mantiene:
- casos_exito.jsonl: La base de datos empírica con peticiones reales confirmadas válidas.
- motor_hash.py: El script de Python que contiene la fórmula matemática actual y aprobada.

### B. Contenedor de Producción (La Réplica API)
- **Tecnología:** Servidor FastAPI (uvicorn con modo --reload).
- **Función:** Ejecutarse 24/7. Recibe el tráfico masivo de las aplicaciones internas simulando ser el servicio real.
- **Comportamiento:** Carece de inteligencia propia y **no gasta cuota de la red externa**. Aplica instantáneamente la lógica descrita en motor_hash.py.

### C. Contenedor Sandbox (Agente Inteligente en Aislamiento)
- **Tecnología:** Script Worker en Python + Integración LLM (OpenRouter).
- **Función:** Opera como un proceso en segundo plano (Cronjob o reacciona ante alertas). Lee el dataset empírico, infiere patrones y descubre anomalías.
- **Seguridad Vital:** Al ejecutar código de Python generado por la IA (mediante exec o subprocesos), debe estar estrictamente aislado. Si la IA alucina código inestable o malicioso, el sandbox absorbe el fallo sin colgar ni vulnerar el contenedor de Producción.

## 2. Diagrama Arquitectónico de Despliegue

`mermaid
flowchart TD
    subgraph Volumen_Compartido [Volumen Compartido (Disco)]
        D[(Dataset: casos_exito.jsonl)]
        M[motor_hash.py (Lógica Viva)]
    end

    subgraph Contenedor_Replica [Contenedor de Producción (FastAPI)]
        API[Servidor Réplica en Puerto 8000]
        M -.->|Uvicorn Hot-Reload| API
        Clientes(Nuestras Apps Internas) <-->|Tráfico 24/7 de Alta Velocidad| API
    end

    subgraph Contenedor_Worker [Contenedor Sandbox Aislado (Agente Científico)]
        O[Script Orquestador]
        D -.->|1. Entrena con Historial| O
        O <-->|2. Intercambio Prompt/Código| LLM((Cerebro LLM\\nOpenRouter))
        O <-->|3. Test Matemático Local| Sandbox[Ejecutor Seguro de Python]
        Sandbox -.->|4. Petición Quirúrgica| CajaNegra{Caja Negra Real}
        CajaNegra -.->|5. Verificación| O
        O ==>|6. Aprueba y Sobrescribe| M
    end
`

## 3. El Ciclo de Auto-Sanación (Self-Healing)

1. **Detección del Cambio:** El servicio "Caja Negra" real cambia sus parámetros. Los nuevos casos válidos se inyectan silenciosamente al dataset.
2. **Razonamiento Aislado:** El Contenedor Sandbox arranca. El Orquestador exige a la IA un nuevo algoritmo que explique este cambio.
3. **Validación en Cuarentena:** El Sandbox evalúa la nueva fórmula de la IA contra todos los historiales localmente. Solo dispara peticiones a la Caja Negra para confirmar bordes nuevos.
4. **Despliegue Caliente (Zero Downtime):** Una vez que el modelo acierta al 100%, el Orquestador sobrescribe motor_hash.py en el Volumen Compartido. El contenedor FastAPI detecta el cambio en el archivo, se recarga internamente en un milisegundo y el sistema de producción se auto-repara sin intervención humana.
"""

js_string = json.dumps(markdown)

html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Topología de Despliegue</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 950px; margin: 0 auto; padding: 40px; }}
        h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
        pre, code {{ background-color: #f6f8fa; border-radius: 6px; }}
        pre {{ padding: 16px; overflow: auto; }}
        .mermaid {{ text-align: center; margin: 2em 0; }}
        @media print {{ body {{ padding: 0; max-width: 100%; }} }}
    </style>
</head>
<body>
    <div id="content">Generando documento...</div>
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

with codecs.open(r'/mnt/c/Users/andres/Downloads/frontier-reto-2/Arquitectura_Despliegue.html', 'w', encoding='utf-8') as f:
    f.write(html)

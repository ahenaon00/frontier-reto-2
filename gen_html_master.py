import json
import codecs

markdown = """# Arquitectura Completa del Sistema: Réplica Autónoma y Agente Inductivo

Este documento consolida la visión completa de nuestro sistema: cómo piensa la Inteligencia Artificial (Lógica Inductiva) y cómo está montado físicamente en servidores (Topología de Despliegue) para ser seguro, infalible y respetuoso con los límites de la red.

---

## 1. El Desafío y Nuestra Filosofía (Zero-Knowledge)
Nos enfrentamos a un servicio externo tipo "caja negra" con límites estrictos de peticiones por segundo y por día. **No conocemos sus reglas internas**, y sabemos que **dichas reglas pueden cambiar en el futuro**.

Si el sistema intentara descubrir los patrones usando *fuerza bruta* o *fuzzing* directo contra el servidor real, saturaríamos la cuota y nos bloquearían.

**La Solución:** Un modelo puramente empírico y offline. La IA no da nada por sentado (Cero Asunciones). Actúa como un científico que revisa nuestro historial de "lo que ha funcionado", crea una fórmula matemática localmente, y solo usa la red real para comprobar su trabajo en el último milisegundo.

---

## 2. El Bucle de Razonamiento de la IA

La Inteligencia Artificial pasa por fases muy estrictas para evitar falsos positivos:
1. **Razonamiento Local:** Recibe los datos crudos (casos_exito.jsonl) y genera una hipótesis matemática en código Python.
2. **Cuarentena (Verificación Local):** El código se prueba contra el historial completo en nuestra máquina. Si falla en un solo caso, la IA debe reescribir su fórmula. No se toca internet.
3. **Prueba Quirúrgica:** Solo cuando la fórmula es perfecta localmente, inventa 2 casos nuevos y los dispara a la Caja Negra.
4. **Resiliencia al Fracaso:** Si la Caja Negra los rechaza, significa que el servicio tiene una regla oculta (o cambió). La IA toma este fallo como un nuevo dato para su entrenamiento y repite el proceso.

---

## 3. Topología de Despliegue Físico

Para que este proceso sea seguro y no detenga las operaciones de la empresa, el sistema se divide físicamente usando **Docker Containers**:

*   **El Volumen Compartido (Disco persistente):** Almacena el historial y el archivo clave motor_hash.py, que es el "cerebro" matemático validado.
*   **Contenedor de Producción (La Réplica API):** Un servidor web superrápido (FastAPI). Corre 24/7 sin inteligencia ni conexión a LLMs. Su única función es servir las respuestas correctas a nuestras aplicaciones internas leyendo el motor_hash.py. Si ese archivo cambia, se recarga en caliente sin interrupciones.
*   **Contenedor Sandbox (El Agente Inductivo):** Un entorno aislado de máxima seguridad. Aquí es donde se evalúa el código Python creado por el "Modelo Grande" (LLM). Si la IA alucina código destructivo, el Sandbox absorbe el golpe, protegiendo a la Réplica de Producción.

---

## 4. Diagrama Unificado: Infraestructura y Flujo Lógico

El siguiente diagrama ilustra cómo se integra la estructura física de despliegue con el bucle de toma de decisiones del Agente.

`mermaid
flowchart TD
    %% Infraestructura Física
    subgraph Host [Infraestructura Dockerizada]

        subgraph Storage [Volumen Compartido (Memoria)]
            D[(Historial Empírico:\\ncasos_exito.jsonl)]
            M[Reglas Validadas:\\nmotor_hash.py]
        end

        subgraph Replica [Contenedor 1: Producción (API Gateway)]
            API[Servidor FastAPI\\nPuerto 8000]
            API -.->|Lee Lógica en Hot-Reload| M
        end

        subgraph Sandbox [Contenedor 2: Worker Aislado (Agente Científico)]
            O[Orquestador\\nPython]
            EXEC[Sandbox Local\\nEvaluación Segura]
        end
    end

    %% Actores Externos
    Apps((Nuestras\\nAplicaciones)) <==>|Tráfico Constante\\nLatencia Cero| API
    LLM((Modelo Grande LLM\\nOpenRouter))
    CajaNegra{Caja Negra Real\\n(Servicio Externo)}

    %% Flujo Lógico
    O -.->|1. Analiza Casos| D
    O <==>|2. Pide Hipótesis Matemática| LLM
    O -->|3. Valida Hipótesis| EXEC
    
    EXEC -->|Fallo: Replantea| O
    EXEC -.->|4. Petición Quirúrgica (Pasa Local)| CajaNegra
    
    CajaNegra -.->|5. Resultado Real| O
    O ==>|6. Despliega Nueva Regla| M
`

### El Ciclo de Vida en la Práctica
Si la Caja Negra actualiza sus políticas mañana, nuestras peticiones de producción empezarán a fallar. Inmediatamente, el **Contenedor 2 (Sandbox)** se despierta, descarga el error, dialoga con el **Modelo Grande** para entender la nueva matemática, prueba la solución localmente, y finalmente sobrescribe motor_hash.py. El **Contenedor 1 (Producción)** detecta el cambio, se actualiza solo, y el sistema queda reparado de forma totalmente autónoma.
"""

js_string = json.dumps(markdown)

html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Arquitectura Completa Unificada</title>
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
    <div id="content">Generando documento maestro...</div>
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

with codecs.open(r'/mnt/c/Users/andres/Downloads/frontier-reto-2/Arquitectura_Completa_Sistema.html', 'w', encoding='utf-8') as f:
    f.write(html)

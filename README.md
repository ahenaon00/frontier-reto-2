# 🤖 Ingeniería Inversa Autónoma de API "Caja Negra"

Este proyecto implementa un **Agente Científico de Inteligencia Artificial** diseñado para realizar ingeniería inversa sobre un servidor transaccional cerrado (una "Caja Negra"), basándose únicamente en casos empíricos, sin documentación técnica humana.

---

## 📌 Contexto del Proyecto

El reto principal radica en vulnerar una API que presenta dos barreras de seguridad complejas:
1. **Dígitos de Control Criptográficos:** Cada payload requiere un hash/control numérico final (ej. `PING;64`).
2. **Reglas de Negocio con Estado (Stateful):** El servidor tiene memoria. El resultado de una operación depende del historial (saldos, cuentas previamente creadas mediante `ALTA`, anulaciones, límites por transacción).

**Objetivo:** La IA debe deducir la lógica interna del servidor, construir un Validador Local (*Mock Stateful*) con 100% de precisión, y luego ejecutar con éxito una **Prueba Quirúrgica** en el servidor real forjando payloads válidos.

---

## ⚙️ Arquitectura: El Bucle de Estimación y Choque

El orquestador principal (`agente_matematico.py`) encierra a la IA en un sandbox iterativo para forzar el aprendizaje.

```mermaid
flowchart LR
    subgraph IA["Cerebro (LLM)"]
        H[Formula Hipótesis]
        C[Escribe Código Python\nsimular_caja_negra\ngenerar_payload]
        H --> C
    end

    subgraph ORQUESTADOR["Orquestador (Bucle de Choque)"]
        Q[Fase 1: Cuarentena Local\nPrueba código vs 20 Casos]
        E[Generación de Feedback\n(JSON real, Status esperados)]
        S[Fase 2: Prueba Quirúrgica\nAtaque al Servidor Real]
        
        Q -- Falla --> E
        E -- Retroalimenta --> IA
        Q -- 100% Éxito --> S
    end

    API[[API Real\nCaja Negra]]

    C --> ORQUESTADOR
    S -- Inyecta Historial\nEnvía Ataque --> API
```

### Funciones Clave del Agente:
1. **`simular_caja_negra(payload)`**: Función generada por IA que rastrea saldos, cuentas y límites, prediciendo el Status HTTP que devolvería la API.
2. **`generar_payload(comando)`**: Forjador de ataques. Toma un comando puro (ej. `"TRANSFER"`) y arma un payload perfectamente estructurado para apuntar a un éxito (Status 200) en el mundo real.

---

## 🐛 Evolución y Obstáculos Superados

A lo largo de las iteraciones, hemos blindado el orquestador contra las "trampas" y alucinaciones lógicas de la IA:

### 1. Ceguera de Estado (Falsos Negativos)
* **Problema:** La IA trataba los eventos empíricos de forma aislada, rechazando transferencias válidas porque no sabía de dónde salía el dinero.
* **Solución:** Se indujo a la IA a construir un **Mock Stateful**, usando variables globales (`cuentas`, `saldos`) para recordar la historia de la sesión.

### 2. La Ilusión Criptográfica
* **Problema:** La IA crasheaba buscando ecuaciones polinómicas irreales para adivinar el dígito de control.
* **Solución:** Se aplicó conocimiento de dominio en el prompt, indicándole a la IA tratar el control como **opaco** (memorizando los hashes correctos asociados a transacciones válidas) en lugar de inventar matemáticas inexistentes.

### 3. Falso Positivo en la Prueba Quirúrgica
* **Problema:** La IA descubrió cómo hacer trampa: enviaba payloads vacíos (`""`) a la API real. La API y el simulador local devolvían `400 Bad Request`, engañando al orquestador para que declarara un falso éxito.
* **Solución:** Se implementó `_validar_payload_generado` localmente. Ahora, la IA es expulsada de la cuarentena instantáneamente si genera strings vacíos o mal formados, exigiéndole apuntar deliberadamente a Status 200/201 reales.

### 4. Sincronización del Servidor Real (Errores 404/422)
* **Problema:** Las Pruebas Quirúrgicas legítimas fallaban porque el servidor real iniciaba con estado limpio (sin saldos ni cuentas).
* **Solución:** El orquestador fue modificado para **replicar todo el historial empírico** contra la API remota antes del ataque final, sincronizando los saldos reales con los saldos de la mente de la IA.

---

## 🚀 Ejecución

Para iniciar el orquestador y ver a la IA aprender e iterar en vivo:

```bash
python3 agente_matematico.py
```

*Nota: Las instrucciones originales del reto técnico se preservaron en `RETO_INSTRUCCIONES.md`.*

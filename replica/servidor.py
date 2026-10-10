from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import motor_hash

app = FastAPI(title="Réplica Caja Negra API")

class Peticion(BaseModel):
    comando: str
    argumentos: str = ""
    control: str

@app.post("/procesar")
def procesar_peticion(req: Peticion):
    # 1. Regla E104: Segmento vacío
    if not req.comando:
        raise HTTPException(status_code=400, detail={"error": "E104", "msg": "segmento vacío"})
    
    # 2. Regla E201: Control mal formado
    # No puede tener más de 2 dígitos, ni símbolos, ni empezar con 0 extraños (salvo 00)
    if not req.control.isdigit() or len(req.control) != 2:
        raise HTTPException(status_code=400, detail={"error": "E201", "msg": "control mal formado"})
        
    # PING siempre es exitoso si su control está bien formado (ignorando su valor real)
    if req.comando.upper() == "PING":
        return {"status": "success", "mensaje": "PING OK"}
        
    # 3. Regla E202: Control inválido (Fallo matemático)
    control_esperado = motor_hash.calcular_digito_control(req.comando, req.argumentos)
    if req.control != control_esperado:
        raise HTTPException(
            status_code=400, 
            detail={"error": "E202", "msg": f"control inválido. Esperado: {control_esperado}"}
        )
        
    # Todo verde: Réplica exitosa
    return {"status": "success", "mensaje": f"{req.comando} procesado exitosamente"}

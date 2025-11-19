import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "contabilidad_v3.db"  # Nombre nuevo para evitar conflictos


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Agregamos columna 'empresa'
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cuentas_balance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        nombre TEXT NOT NULL,
        monto REAL NOT NULL,
        tipo TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historial_resultados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        utilidad_neta REAL
    )
    ''')

    conn.commit()
    conn.close()


init_db()


# --- Modelos ---

class CuentaBalance(BaseModel):
    empresa: str
    nombre: str
    monto: float
    tipo: str


class CuentaBalanceUpdate(BaseModel):
    nombre: str
    monto: float
    tipo: str


class DatosEstadoResultados(BaseModel):
    empresa: str
    ventas_totales: float
    dev_ventas: float
    desc_ventas: float
    inventario_inicial: float
    compras: float
    gastos_compra: float
    dev_compras: float
    desc_compras: float
    inventario_final: float
    gastos_venta: float
    gastos_admin: float
    productos_financieros: float
    gastos_financieros: float
    otros_gastos: float
    otros_productos: float


# --- Endpoints ---

# === BALANCE GENERAL ===

@app.get("/balance/calcular")
def obtener_balance(empresa: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Filtramos por empresa
    cursor.execute("SELECT * FROM cuentas_balance WHERE empresa = ?", (empresa,))
    filas = cursor.fetchall()
    conn.close()

    balance = {
        "activo": {"circulante": [], "fijo": [], "diferido": [], "total": 0.0},
        "pasivo": {"circulante": [], "fijo": [], "diferido": [], "total": 0.0},
        "capital_contable": 0.0
    }

    for f in filas:
        # f = (id, empresa, nombre, monto, tipo)
        item = {"id": f[0], "nombre": f[2], "monto": f[3], "tipo": f[4]}  # Enviamos ID para poder editar
        monto = f[3]
        tipo = f[4]

        if tipo.startswith("ACTIVO"):
            balance["activo"]["total"] += monto
            if "CIRCULANTE" in tipo:
                balance["activo"]["circulante"].append(item)
            elif "FIJO" in tipo:
                balance["activo"]["fijo"].append(item)
            elif "DIFERIDO" in tipo:
                balance["activo"]["diferido"].append(item)

        elif tipo.startswith("PASIVO"):
            balance["pasivo"]["total"] += monto
            if "CIRCULANTE" in tipo:
                balance["pasivo"]["circulante"].append(item)
            elif "FIJO" in tipo:
                balance["pasivo"]["fijo"].append(item)
            elif "DIFERIDO" in tipo:
                balance["pasivo"]["diferido"].append(item)

    balance["capital_contable"] = balance["activo"]["total"] - balance["pasivo"]["total"]
    return balance


@app.post("/balance/agregar")
def agregar_cuenta(cuenta: CuentaBalance):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cuentas_balance (empresa, nombre, monto, tipo) VALUES (?, ?, ?, ?)",
                   (cuenta.empresa, cuenta.nombre, cuenta.monto, cuenta.tipo))
    conn.commit()
    conn.close()
    return {"msg": "Agregado"}


@app.put("/balance/editar/{id_cuenta}")
def editar_cuenta(id_cuenta: int, cuenta: CuentaBalanceUpdate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE cuentas_balance SET nombre=?, monto=?, tipo=? WHERE id=?",
                   (cuenta.nombre, cuenta.monto, cuenta.tipo, id_cuenta))
    conn.commit()
    conn.close()
    return {"msg": "Actualizado"}


@app.delete("/balance/borrar-todo")
def limpiar_balance(empresa: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cuentas_balance WHERE empresa = ?", (empresa,))
    conn.commit()
    conn.close()
    return {"msg": "Balance reiniciado para la empresa"}


# === ESTADO DE RESULTADOS ===
@app.post("/resultados/calcular")
def calcular_resultados(d: DatosEstadoResultados):
    # Lógica idéntica, solo guardamos la empresa en el historial
    ventas_netas = d.ventas_totales - (d.dev_ventas + d.desc_ventas)
    compras_totales = d.compras + d.gastos_compra
    compras_netas = compras_totales - (d.dev_compras + d.desc_compras)
    suma_mercancias = d.inventario_inicial + compras_netas
    costo_vendido = suma_mercancias - d.inventario_final
    utilidad_bruta = ventas_netas - costo_vendido

    utilidad_operacion_base = utilidad_bruta - (d.gastos_venta + d.gastos_admin)
    financiero_neto = d.productos_financieros - d.gastos_financieros
    otros_neto = d.otros_productos - d.otros_gastos

    utilidad_antes_impuestos = utilidad_operacion_base + financiero_neto + otros_neto
    isr = utilidad_antes_impuestos * 0.33
    ptu = utilidad_antes_impuestos * 0.10
    utilidad_neta = utilidad_antes_impuestos - (isr + ptu)

    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT INTO historial_resultados (empresa, utilidad_neta) VALUES (?, ?)",
                          (d.empresa, utilidad_neta))
    conn.commit()
    conn.close()

    return {
        "ventas_netas": ventas_netas,
        "compras_totales": compras_totales,
        "compras_netas": compras_netas,
        "suma_mercancias": suma_mercancias,
        "costo_vendido": costo_vendido,
        "utilidad_bruta": utilidad_bruta,
        "utilidad_operacion": utilidad_operacion_base,
        "financiero_neto": financiero_neto,
        "otros_neto": otros_neto,
        "utilidad_antes_impuestos": utilidad_antes_impuestos,
        "isr": isr,
        "ptu": ptu,
        "utilidad_neta": utilidad_neta
    }


# ... (resto del código anterior) ...

@app.get("/empresas")
def listar_empresas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Buscamos empresas únicas tanto en balances como en resultados
    # Usamos UNION para combinar ambas tablas y DISTINCT para quitar duplicados
    cursor.execute('''
        SELECT DISTINCT empresa FROM cuentas_balance
        UNION
        SELECT DISTINCT empresa FROM historial_resultados
    ''')

    filas = cursor.fetchall()
    conn.close()

    # Devolvemos una lista simple de strings: ["Empresa A", "Empresa B"]
    lista_empresas = [f[0] for f in filas if f[0]]
    return lista_empresas

@app.delete("/balance/borrar-cuenta/{id_cuenta}")
def borrar_cuenta_individual(id_cuenta: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cuentas_balance WHERE id = ?", (id_cuenta,))
    conn.commit()
    conn.close()
    return {"msg": "Cuenta eliminada correctamente"}
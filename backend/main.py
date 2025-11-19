import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "contabilidad_v2.db"


# --- 1. Configuración de BD ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Actualizamos la tabla para soportar tipos específicos
    # Nota: Si ya tienes la BD creada, sqlite es flexible con los tipos de texto,
    # pero se recomienda borrar el archivo .db para empezar limpio con la nueva lógica.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cuentas_balance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        monto REAL NOT NULL,
        tipo TEXT NOT NULL -- Ej: 'ACTIVO_CIRCULANTE', 'PASIVO_FIJO', etc.
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historial_resultados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        utilidad_neta REAL
    )
    ''')

    conn.commit()
    conn.close()


init_db()


# --- 2. Modelos ---

class CuentaBalance(BaseModel):
    nombre: str
    monto: float
    tipo: str  # Ahora recibirá strings específicos como 'ACTIVO_CIRCULANTE'


class DatosEstadoResultados(BaseModel):
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


# --- 3. Endpoints ---

# === A. BALANCE GENERAL DETALLADO ===
@app.post("/balance/agregar")
def agregar_cuenta_balance(cuenta: CuentaBalance):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cuentas_balance (nombre, monto, tipo) VALUES (?, ?, ?)",
                   (cuenta.nombre, cuenta.monto, cuenta.tipo))
    conn.commit()
    conn.close()
    return {"msg": "Cuenta agregada"}


@app.get("/balance/calcular")
def obtener_balance():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cuentas_balance")
    filas = cursor.fetchall()
    conn.close()

    # Estructura para clasificar
    balance = {
        "activo": {
            "circulante": [],
            "fijo": [],
            "diferido": [],
            "total": 0.0
        },
        "pasivo": {
            "circulante": [],
            "fijo": [],
            "diferido": [],
            "total": 0.0
        },
        "capital_contable": 0.0
    }

    for f in filas:
        # f = (id, nombre, monto, tipo)
        nombre = f[1]
        monto = f[2]
        tipo = f[3]  # Ej: "ACTIVO_CIRCULANTE"

        item = {"nombre": nombre, "monto": monto}

        # Lógica de clasificación
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


@app.delete("/balance/limpiar")
def limpiar_balance():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cuentas_balance")
    conn.commit()
    conn.close()
    return {"msg": "Balance reiniciado"}


# === B. ESTADO DE RESULTADOS (Igual que antes) ===
@app.post("/resultados/calcular")
def calcular_estado_resultados(d: DatosEstadoResultados):
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
    conn.cursor().execute("INSERT INTO historial_resultados (utilidad_neta) VALUES (?)", (utilidad_neta,))
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
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot de Tránsito (empaquetado)
- Menú principal con banner por llenadora (sin mostrar pin)
- 📦 Carga de datos (Cargar, Ver)  [Modificar/Eliminar se pueden añadir luego]
- 🚚 Reportar tránsito (solo Llenadora -> Canastas -> Pin cuando aplique)
- Generación de clave de envase con hora actual, juliano, vencimiento y SKU
- Pin sugerido por medida (editable), validaciones por medida
- Resumen elegante con cálculo de cajas, opción "ver clave" por lote
- Persistencia simple en JSON (catálogo, configuración por chat, etc.)

Requisitos:
- Python 3.9+
- TOKEN en variable de entorno: BOT_TOKEN
"""

import os
import time
import json
import threading
from datetime import datetime, timedelta
import requests

# =========================
# Configuración
# =========================
TOKEN_TELEGRAM = os.getenv(BOT_TOKEN)
API_URL = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}"
POLL_TIMEOUT = 25
last_update_id = None

# Persistencia
CATALOGO_SKUS_PATH    = "catalogo_skus.json"   # catálogo institucional (producto|medida|mercado) -> {sku, vida_util_meses,...}
CONFIG_TURNO_PATH     = "config_turno.json"    # por chat_id: asignación por llenadora
ORDENES_SEMANA_PATH   = "ordenes_semana.json"  # metas por semana (opcional, estructura lista)
PROGRESO_SEMANA_PATH  = "progreso_semana.json" # producido acumulado por semana (opcional, estructura lista)

_json_lock = threading.Lock()

# Estados en memoria
estados_usuarios = {}  # por chat_id: estado conversacional

# =========================
# Conversión de cajas / canasta
# =========================
CAJAS_POR_CANASTA = {
    "4oz":  {"grande": 0,   "pequeño": 110},
    "8oz":  {"grande": 68,  "pequeño": 93.5},
    "14oz": {"grande": 80,  "pequeño": 110},
    "16oz": {"grande": 0,   "pequeño": 165},
    "28oz": {"grande": 58,  "pequeño": 0},
    "35oz": {"grande": 53,  "pequeño": 0},
    "40oz": {"grande": 48,  "pequeño": 0},
    "80oz": {"grande": 53,  "pequeño": 0},
    "4lbs": {"único": 81},  # Chub
}

# =========================
# Pin sugerido y reglas
# =========================
DEFAULT_PIN_BY_MEDIDA = {
    "4oz":  "pequeño",
    "8oz":  "pequeño",
    "14oz": "pequeño",
    "16oz": "pequeño",
    "28oz": "grande",
    "35oz": "grande",
    "80oz": "grande",
    # "40oz":  "grande",  # descomenta si aplica
}

PIN_PERMITIDO_POR_MEDIDA = {
    "4oz":  {"pequeño"},
    "8oz":  {"pequeño"},
    "14oz": {"pequeño"},
    "16oz": {"pequeño"},
    "28oz": {"grande"},
    "35oz": {"grande"},
    "40oz": {"grande"},
    "80oz": {"grande"},
    "4lbs": {"único"},   # Chub
}

def pin_sugerido_para_medida(medida):
    return DEFAULT_PIN_BY_MEDIDA.get(medida)

def pin_es_valido(medida, pin):
    return pin in PIN_PERMITIDO_POR_MEDIDA.get(medida, set())

# =========================
# Utilidades JSON y tiempo
# =========================
def _load_json(path, default):
    try:
        with _json_lock:
            if not os.path.exists(path):
                return default
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    try:
        with _json_lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
    except Exception:
        return False

def tz_now_gt():
    # Ajusta si el host no está en Guatemala; aquí usamos hora local del sistema
    return datetime.now()

def semana_iso_id(dt=None):
    dt = dt or tz_now_gt()
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"

def dia_juliano(dt):
    return dt.timetuple().tm_yday

MESES_ES = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"]
MESES_EN = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

def mes_es(idx):  # 1..12
    return MESES_ES[idx-1]

def mes_en(idx):  # 1..12
    return MESES_EN[idx-1]

def sumar_meses(dt, meses):
    y = dt.year + (dt.month - 1 + meses) // 12
    m = (dt.month - 1 + meses) % 12 + 1
    # día 15 fijo
    return datetime(y, m, 15, dt.hour, dt.minute)

def calcular_vencimiento(fecha_prod, vida_util_meses):
    return sumar_meses(fecha_prod, vida_util_meses)

# =========================
# Catálogo y configuración
# =========================
def get_catalogo():
    return _load_json(CATALOGO_SKUS_PATH, {})

def set_catalogo(data):
    return _save_json(CATALOGO_SKUS_PATH, data)

def get_config_turno():
    return _load_json(CONFIG_TURNO_PATH, {})

def set_config_turno(data):
    return _save_json(CONFIG_TURNO_PATH, data)

def combo_key(producto, medida, mercado):
    return f"{producto}|{medida}|{mercado}"

# =========================
# Clave de envase
# =========================
LETRA_LLENADORA = {"M1":"B", "M2":"C", "M3":"D"}  # Chub pendiente

def generar_clave_envase(llenadora, mercado, sku, vida_util_meses, fecha_ref=None, letra_chub=None):
    ahora = fecha_ref or tz_now_gt()
    yy = ahora.year % 100
    hhmm = ahora.strftime("%H:%M")
    ddd = dia_juliano(ahora)

    # línea 1 (incluye hora)
    if llenadora == "Chub":
        letra = letra_chub if letra_chub else "—"  # pendiente
    else:
        letra = LETRA_LLENADORA.get(llenadora, "—")
    linea1 = f"{letra} {hhmm} {yy:02d} L {ddd}"

    # vencimiento
    venc = calcular_vencimiento(ahora, vida_util_meses)
    yy_v = venc.year % 100
    if mercado == "FDA":
        mes_txt = mes_en(venc.month)
        pref = "BEST BY"
    else:
        mes_txt = mes_es(venc.month)
        pref = "EXP"
    linea2 = f"{pref} 15 {mes_txt} {yy_v:02d}"

    # SKU final
    linea3 = f"6173 {sku}"

    return f"{linea1}\n{linea2}\n{linea3}"

# =========================
# Markdown y helpers UI
# =========================
def md_escape(texto: str) -> str:
    return str(texto).replace('_', r'\_').replace('*', r'\*').replace('[', r'\[').replace('`', r'\`')

def send_msg(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    requests.post(f"{API_URL}/sendMessage", json=payload)

def answer_callback(callback_query_id):
    requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": callback_query_id})

def teclado_inline(filas):
    return {"inline_keyboard": filas}

# =========================
# Banner de /menu
# =========================
def banner_estado_llenadoras(chat_id: int) -> str:
    cfg = get_config_turno()
    estado_ll = cfg.get(str(chat_id), {})

    def fmt(ll: str) -> str:
        combo = estado_ll.get(ll)
        if combo and all(k in combo for k in ("producto", "medida", "mercado")):
            return f"{ll}: {combo['producto']} {combo['medida']} {combo['mercado']}"
        return f"{ll}: —"

    lineas = [
        "📋 Estado actual por llenadora:",
        fmt("M1"),
        fmt("M2"),
        fmt("M3"),
        fmt("Chub"),
    ]
    return "\n".join(lineas)

def mostrar_menu(chat_id):
    banner = banner_estado_llenadoras(chat_id)
    filas = [
        [{"text": "📦 Carga de datos",    "callback_data": "carga_menu"}],
        [{"text": "🚚 Reportar tránsito", "callback_data": "transito"}],
    ]
    send_msg(chat_id, f"{banner}\n\n🛠️ Selecciona una herramienta:", teclado_inline(filas))

# =========================
# Carga de datos (Cargar y Ver)
# =========================
def mostrar_menu_carga(chat_id):
    filas = [
        [{"text": "➕ Cargar", "callback_data": "carga_nuevo"},
         {"text": "👁 Ver",   "callback_data": "carga_ver"}],
        # Futuro: Modificar / Eliminar
        [{"text": "⬅️ Volver", "callback_data": "volver_menu"}]
    ]
    send_msg(chat_id, "📦 Carga de datos — elige una opción:", teclado_inline(filas))

def iniciar_carga(chat_id):
    # Paso 1: Llenadora
    filas = [
        [{"text": "M1", "callback_data": "c_n_ll_M1"},
         {"text": "M2", "callback_data": "c_n_ll_M2"}],
        [{"text": "M3", "callback_data": "c_n_ll_M3"},
         {"text": "Chub", "callback_data": "c_n_ll_Chub"}],
    ]
    estados_usuarios[chat_id] = {"paso":"carga_ll", "tmp":{}}
    send_msg(chat_id, "Selecciona la *llenadora* para este registro:", teclado_inline(filas), parse_mode="Markdown")

def teclado_productos():
    # Ajusta a tu lista real
    base = [
        {"text": "FND", "callback_data": "c_n_p_FND"},
        {"text": "FRD", "callback_data": "c_n_p_FRD"},
        {"text": "FRS", "callback_data": "c_n_p_FRS"},
        {"text": "FNA", "callback_data": "c_n_p_FNA"},
        {"text": "FNP", "callback_data": "c_n_p_FNP"},
        {"text": "FRP", "callback_data": "c_n_p_FRP"},
        {"text": "FNE", "callback_data": "c_n_p_FNE"},
        {"text": "FRE", "callback_data": "c_n_p_FRE"},
    ]
    filas = [base[i:i+2] for i in range(0, len(base), 2)]
    return teclado_inline(filas)

def teclado_medidas():
    medidas = ["4oz","8oz","14oz","16oz","28oz","35oz","40oz","80oz","4lbs"]
    filas = [[{"text": m, "callback_data": f"c_n_m_{m}"} for m in medidas[i:i+3]] for i in range(0, len(medidas), 3)]
    return teclado_inline(filas)

def teclado_mercados():
    filas = [[
        {"text":"RTCA 🇬🇹", "callback_data":"c_n_me_RTCA"},
        {"text":"FDA 🇺🇸",  "callback_data":"c_n_me_FDA"},
    ]]
    return teclado_inline(filas)

def carga_ver(chat_id):
    cfg = get_config_turno()
    estado_ll = cfg.get(str(chat_id), {})
    catalogo = get_catalogo()

    llenadoras = ["M1","M2","M3","Chub"]
    lineas = ["👁 *Registros cargados (por llenadora):*"]
    hay_algo = False

    for ll in llenadoras:
        combo = estado_ll.get(ll)
        if combo:
            hay_algo = True
            p, m, me = combo["producto"], combo["medida"], combo["mercado"]
            k = combo_key(p,m,me)
            cat = catalogo.get(k, {})
            sku = cat.get("sku")
            vida = cat.get("vida_util_meses")
            if sku and vida:
                clave = generar_clave_envase(ll, me, sku, vida)
                lineas.append(
                    f"\n*{ll}* → {p} {m} {me}\n"
                    f"SKU: `{sku}` | Vida útil: {vida}m\n"
                    f"🔑 *Clave (ahora):*\n```\n{clave}\n```"
                )
            else:
                faltan = []
                if not sku: faltan.append("SKU")
                if not vida: faltan.append("vida útil")
                lineas.append(
                    f"\n*{ll}* → {p} {m} {me}\n"
                    f"⚠️ Falta completar en catálogo: {', '.join(faltan)}"
                )
        else:
            lineas.append(f"\n*{ll}* → —")

    if not hay_algo:
        filas = [[{"text":"➕ Cargar ahora","callback_data":"carga_nuevo"}],
                 [{"text":"⬅️ Volver","callback_data":"carga_menu"}]]
        send_msg(chat_id, "👁 No hay registros cargados.\nUsa *Cargar* para crear el primero.", teclado_inline(filas), parse_mode="Markdown")
    else:
        send_msg(chat_id, "\n".join(lineas), parse_mode="Markdown")

# =========================
# Reportar tránsito
# =========================
def mostrar_llenadoras_transito(chat_id):
    filas = [
        [{"text": "M1", "callback_data": "t_ll_M1"},
         {"text": "M2", "callback_data": "t_ll_M2"}],
        [{"text": "M3", "callback_data": "t_ll_M3"},
         {"text": "Chub", "callback_data": "t_ll_Chub"}],
    ]
    send_msg(chat_id, "Selecciona llenadora:", teclado_inline(filas))

def mostrar_teclado_pin(chat_id, cantidad, medida):
    sugerido = pin_sugerido_para_medida(medida)
    b_peq = "🔩 Pin Pequeño"
    b_gra = "🔩 Pin Grande"
    if sugerido == "pequeño":
        b_peq = "⭐ " + b_peq
    elif sugerido == "grande":
        b_gra = "⭐ " + b_gra
    filas = [[
        {"text": b_peq, "callback_data": "pin_pequeño"},
        {"text": b_gra, "callback_data": "pin_grande"},
    ]]
    texto = f"✅ Canastas: {cantidad}\n📏 Medida: {medida}\n\n"
    if sugerido:
        texto += f"💡 Sugerido: *{sugerido}* (puedes cambiarlo)\n\n"
    texto += "🔧 Selecciona el tamaño del pin:"
    send_msg(chat_id, texto, teclado_inline(filas), parse_mode="Markdown")

def mostrar_teclado_otro_lote_con_clave(chat_id, estado, prefijo_texto=""):
    txt = prefijo_texto.strip()
    # si hay datos suficientes para clave
    cfg = get_config_turno().get(str(chat_id), {})
    ll = estado.get("llenadora")
    combo = cfg.get(ll, {})
    catalogo = get_catalogo()
    k = combo_key(combo.get("producto",""), combo.get("medida",""), combo.get("mercado",""))
    cat = catalogo.get(k, {})
    sku, vida = cat.get("sku"), cat.get("vida_util_meses")

    if sku and vida and all(k in estado for k in ("pin",)) and combo.get("mercado"):
        clave = generar_clave_envase(ll, combo["mercado"], sku, vida)
        if txt:
            txt += "\n\n"
        txt += f"🔑 Clave sugerida: *\n{md_escape(clave)}\n*"

    filas = [[
        {"text": "🔑 Ver clave del envase", "callback_data": "ver_clave"},
    ],[
        {"text": "✅ Sí", "callback_data": "otro_si"},
        {"text": "❌ No", "callback_data": "otro_no"},
    ]]
    send_msg(chat_id, (txt + "\n\n➕ ¿Deseas agregar otro lote?").strip(), teclado_inline(filas), parse_mode=None)

def construir_resumen_elegante(reportes, chat_id):
    por_llenadora = {}
    total_cajas = 0.0
    total_canastas = 0
    lineas = ["✅ *Resumen del turno:*"]
    for idx, r in enumerate(reportes, 1):
        llenadora = r["llenadora"]
        canastas  = int(r["canastas"])
        pin       = r["pin"]

        # combo desde config_turno
        cfg = get_config_turno().get(str(chat_id), {})
        combo = cfg.get(llenadora, {})
        producto = combo.get("producto","—")
        medida   = combo.get("medida","—")
        mercado  = combo.get("mercado","—")

        por_pin = CAJAS_POR_CANASTA.get(medida, {}).get(pin, 0)
        cajas = canastas * por_pin

        d = por_llenadora.setdefault(llenadora, {"cajas": 0.0, "canastas": 0})
        d["cajas"] += cajas
        d["canastas"] += canastas
        total_cajas += cajas
        total_canastas += canastas

        lineas.append(
            f"\n📦 *Lote {idx}*\n"
            f"🔹 Llenadora: {md_escape(llenadora)}\n"
            f"📏 Medida: {md_escape(medida)}\n"
            f"🍲 Producto: {md_escape(producto)}\n"
            f"🌎 Mercado: {md_escape(mercado)}\n"
            f"🧺 Canastas: {canastas} | 🔩 Pin: {md_escape(pin)}\n"
            f"📦 Cajas: *{int(cajas) if cajas.is_integer() else f'{cajas:.1f}'}* (≈ {int(por_pin) if isinstance(por_pin,(int,float)) and float(por_pin).is_integer() else por_pin} x canasta)"
        )

    lineas.append("\n— — —")
    lineas.append("*Totales por llenadora*:")
    for ll, d in por_llenadora.items():
        cajas_fmt = int(d["cajas"]) if d["cajas"].is_integer() else f"{d['cajas']:.1f}"
        lineas.append(f"• {md_escape(ll)} → 🧺 {d['canastas']} | 📦 {cajas_fmt}")

    total_fmt = int(total_cajas) if total_cajas.is_integer() else f"{total_cajas:.1f}"
    lineas.append("\n*Totales generales:*")
    lineas.append(f"🧺 Canastas: *{total_canastas}*")
    lineas.append(f"📦 Cajas: *{total_fmt}*")

    return "\n".join(lineas)

# =========================
# Bot
# =========================
def revisar_mensajes():
    global last_update_id
    while True:
        try:
            params = {"timeout": POLL_TIMEOUT}
            if last_update_id is not None:
                params["offset"] = last_update_id
            res = requests.get(f"{API_URL}/getUpdates", params=params, timeout=POLL_TIMEOUT+5)
            data = res.json()

            for update in data.get("result", []):
                last_update_id = update["update_id"] + 1

                # Mensajes
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    texto = (message.get("text") or "").strip()
                    estado = estados_usuarios.get(chat_id)

                    if texto in ("/start", "/menu"):
                        mostrar_menu(chat_id)
                        continue

                    # Paso cantidad (tránsito)
                    if estado and estado.get("paso") == "t_cantidad":
                        try:
                            cantidad = int(texto)
                            if cantidad <= 0:
                                raise ValueError
                            estado["canastas"] = cantidad
                            ll = estado.get("llenadora")

                            if ll == "Chub":
                                estado["pin"] = "único"
                                # Validación
                                # Recuperar medida desde config
                                cfg = get_config_turno().get(str(chat_id), {})
                                medida = cfg.get(ll, {}).get("medida","")
                                if not pin_es_valido(medida, estado["pin"]):
                                    send_msg(chat_id, f"⚠️ Configuración inconsistente: {medida} no admite pin {estado['pin']}. Corrige la medida en Carga de datos.", parse_mode="Markdown")
                                    estados_usuarios.pop(chat_id, None)
                                    continue
                                estado["paso"] = "t_otro"
                                mostrar_teclado_otro_lote_con_clave(
                                    chat_id, estado,
                                    f"✅ Canastas: {cantidad}\nPin asignado automáticamente: único 🔩"
                                )
                            elif ll == "M3":
                                estado["pin"] = "grande"
                                cfg = get_config_turno().get(str(chat_id), {})
                                medida = cfg.get(ll, {}).get("medida","")
                                if not pin_es_valido(medida, estado["pin"]):
                                    send_msg(chat_id, f"⚠️ Configuración inconsistente: {medida} no admite pin {estado['pin']}. Corrige la medida en Carga de datos.", parse_mode="Markdown")
                                    estados_usuarios.pop(chat_id, None)
                                    continue
                                estado["paso"] = "t_otro"
                                mostrar_teclado_otro_lote_con_clave(
                                    chat_id, estado,
                                    f"✅ Canastas: {cantidad}\nPin asignado automáticamente: grande 🔩"
                                )
                            else:
                                # M1/M2 pedir pin
                                estado["paso"] = "t_pin"
                                cfg = get_config_turno().get(str(chat_id), {})
                                medida = cfg.get(ll, {}).get("medida","—")
                                mostrar_teclado_pin(chat_id, cantidad, medida)

                        except ValueError:
                            send_msg(chat_id, "❗ Ingresa un número válido de canastas (entero positivo).", parse_mode=None)

                # Callbacks
                elif "callback_query" in update:
                    cq = update["callback_query"]
                    chat_id = cq["message"]["chat"]["id"]
                    callback_data = cq["data"]
                    answer_callback(cq["id"])
                    estado = estados_usuarios.get(chat_id)

                    # Menú principal
                    if callback_data == "transito":
                        estados_usuarios[chat_id] = {"paso": "t_ll"}
                        mostrar_llenadoras_transito(chat_id)

                    elif callback_data == "carga_menu":
                        mostrar_menu_carga(chat_id)

                    elif callback_data == "volver_menu":
                        mostrar_menu(chat_id)

                    # Carga de datos: iniciar
                    elif callback_data == "carga_nuevo":
                        iniciar_carga(chat_id)

                    # Carga de datos: Ver
                    elif callback_data == "carga_ver":
                        carga_ver(chat_id)

                    # Carga NUEVO: elegir llenadora
                    elif callback_data.startswith("c_n_ll_"):
                        ll = callback_data.split("_", 2)[2]
                        estados_usuarios[chat_id] = {"paso":"carga_producto", "tmp":{"llenadora": ll}}
                        send_msg(chat_id, f"✅ Llenadora: {ll}\n\nElige *producto*:", teclado_productos(), parse_mode="Markdown")

                    # Carga NUEVO: producto
                    elif callback_data.startswith("c_n_p_"):
                        p = callback_data.split("_", 2)[2]
                        if estado and estado.get("paso") == "carga_producto":
                            estado["tmp"]["producto"] = p
                            estado["paso"] = "carga_medida"
                            send_msg(chat_id, f"✅ Producto: {p}\n\nElige *medida*:", teclado_medidas(), parse_mode="Markdown")

                    # Carga NUEVO: medida
                    elif callback_data.startswith("c_n_m_"):
                        m = callback_data.split("_", 2)[2]
                        if estado and estado.get("paso") == "carga_medida":
                            estado["tmp"]["medida"] = m
                            estado["paso"] = "carga_mercado"
                            send_msg(chat_id, f"✅ Medida: {m}\n\nElige *mercado*:", teclado_mercados(), parse_mode="Markdown")

                    # Carga NUEVO: mercado -> guardar asignación si existe en catálogo
                    elif callback_data.startswith("c_n_me_"):
                        me = callback_data.split("_", 3)[3]
                        if estado and estado.get("paso") == "carga_mercado":
                            tmp = estado["tmp"]
                            tmp["mercado"] = me
                            p, m, me = tmp["producto"], tmp["medida"], tmp["mercado"]
                            k = combo_key(p,m,me)
                            catalogo = get_catalogo()
                            cat = catalogo.get(k)
                            if not cat or "sku" not in cat or "vida_util_meses" not in cat:
                                # No existe en catálogo -> pedir completar (MVP: mensaje)
                                send_msg(chat_id, f"⚠️ Este combo no existe en catálogo o está incompleto:\n{k}\nAgrega en {CATALOGO_SKUS_PATH} el *sku* y *vida_util_meses* y vuelve a intentar.", parse_mode="Markdown")
                                estados_usuarios.pop(chat_id, None)
                            else:
                                # Guardar en config_turno por chat y llenadora
                                cfg = get_config_turno()
                                por_chat = cfg.get(str(chat_id), {})
                                por_chat[tmp["llenadora"]] = {"producto": p, "medida": m, "mercado": me}
                                cfg[str(chat_id)] = por_chat
                                set_config_turno(cfg)

                                # Vista previa de clave
                                clave = generar_clave_envase(tmp["llenadora"], me, cat["sku"], cat["vida_util_meses"])
                                send_msg(chat_id, f"✅ Configuración guardada para *{tmp['llenadora']}* → {p} {m} {me}\n\n🔑 Clave (ahora):\n```\n{clave}\n```", parse_mode="Markdown")
                                estados_usuarios.pop(chat_id, None)
                                # refrescar menú con banner
                                mostrar_menu(chat_id)

                    # Tránsito: elegir llenadora
                    elif callback_data.startswith("t_ll_"):
                        ll = callback_data.split("_", 2)[2]
                        # Verificar si hay config para esa llenadora
                        cfg = get_config_turno().get(str(chat_id), {})
                        combo = cfg.get(ll)
                        if not combo:
                            filas = [[{"text":"➕ Crear registro ahora","callback_data":"carga_nuevo"}],
                                     [{"text":"⬅️ Volver","callback_data":"volver_menu"}]]
                            send_msg(chat_id, f"⚠️ No hay registro para {ll}.\nUsa *Cargar* para asignar un producto/medida/mercado.", teclado_inline(filas), parse_mode="Markdown")
                        else:
                            # Pasar a pedir canastas
                            estados_usuarios[chat_id] = {"paso":"t_cantidad", "llenadora": ll, "reportes": []}
                            send_msg(chat_id, f"✅ {ll}: {combo['producto']} {combo['medida']} {combo['mercado']}\n\n🔢 ¿Cuántas canastas se reportaron?", parse_mode="Markdown")

                    # Tránsito: selección de pin manual (M1/M2)
                    elif callback_data.startswith("pin_"):
                        pin = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "t_pin":
                            ll = estado.get("llenadora")
                            cfg = get_config_turno().get(str(chat_id), {})
                            medida = cfg.get(ll, {}).get("medida","—")
                            if not pin_es_valido(medida, pin):
                                send_msg(chat_id, f"⚠️ El pin *{pin}* no es válido para {medida}.", parse_mode="Markdown")
                                mostrar_teclado_pin(chat_id, estado.get("canastas"), medida)
                                continue
                            estado["pin"] = pin
                            estado["paso"] = "t_otro"
                            mostrar_teclado_otro_lote_con_clave(chat_id, estado, f"✅ Pin: {pin}")

                    # Tránsito: ver clave del envase (según config asignada)
                    elif callback_data == "ver_clave":
                        cfg = get_config_turno().get(str(chat_id), {})
                        estado = estados_usuarios.get(chat_id, {})
                        ll = estado.get("llenadora")
                        combo = cfg.get(ll, {})
                        catalogo = get_catalogo()
                        k = combo_key(combo.get("producto",""), combo.get("medida",""), combo.get("mercado",""))
                        cat = catalogo.get(k, {})
                        sku, vida = cat.get("sku"), cat.get("vida_util_meses")
                        if ll and combo and sku and vida:
                            clave = generar_clave_envase(ll, combo["mercado"], sku, vida)
                            send_msg(chat_id, f"🔑 Clave (ahora):\n```\n{clave}\n```", parse_mode=None)
                        else:
                            send_msg(chat_id, "⚠️ Falta información en catálogo o configuración para generar la clave.")

                    # Tránsito: otro lote / finalizar
                    elif callback_data.startswith("otro_"):
                        if estado and estado.get("paso") in ("t_otro","t_pin","t_cantidad"):
                            # Necesitamos: llenadora, canastas, pin y combo desde config
                            ll = estado.get("llenadora")
                            cfg_all = get_config_turno()
                            cfg = cfg_all.get(str(chat_id), {})
                            combo = cfg.get(ll, {})
                            if not (ll and "canastas" in estado and "pin" in estado and combo):
                                send_msg(chat_id, "⚠️ Faltan datos para cerrar el lote.", parse_mode=None)
                                estados_usuarios.pop(chat_id, None)
                                continue

                            # Acumular en reportes del estado
                            if "reportes" not in estado:
                                estado["reportes"] = []
                            estado["reportes"].append({
                                "llenadora": ll,
                                "canastas": int(estado["canastas"]),
                                "pin": estado["pin"],
                            })

                            if callback_data == "otro_si":
                                # Nuevo lote
                                estados_usuarios[chat_id] = {"paso":"t_ll"}  # permite cambiar de llenadora si se desea
                                mostrar_llenadoras_transito(chat_id)
                            else:
                                # Resumen final
                                texto = construir_resumen_elegante(estado["reportes"], chat_id)
                                send_msg(chat_id, texto, parse_mode="Markdown")
                                estados_usuarios.pop(chat_id, None)

        except Exception as e:
            print("❗ Error:", e)
            time.sleep(2)

# =========================
# Main
# =========================
if __name__ == "__main__":
    if TOKEN_TELEGRAM.startswith("REEMPLAZA_") or not TOKEN_TELEGRAM:
        print("⚠️ Define la variable de entorno BOT_TOKEN antes de ejecutar en producción.")
    else:
        print("Bot de Tránsito empaquetado 🚀 (long-polling)")
    # Inicializa archivos JSON si no existen
    for path, default in [
        (CATALOGO_SKUS_PATH, {}),
        (CONFIG_TURNO_PATH, {}),
        (ORDENES_SEMANA_PATH, {}),
        (PROGRESO_SEMANA_PATH, {}),
    ]:
        if not os.path.exists(path):
            _save_json(path, default)
    # Loop
    revisar_mensajes()

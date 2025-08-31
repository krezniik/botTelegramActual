import os
import time
import json
import math
import datetime
import requests

# =========================
# Config
# =========================
TOKEN_TELEGRAM = os.getenv(BOT_TOKEN)
API_URL = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}"
GROUP_ID = -1002710248563  # grupo para enviar el resumen elegante
POLL_TIMEOUT = 25  # segundos para long-polling
last_update_id = None

# Estados por chat
estados_usuarios = {}

# Conversión cajas / canasta
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
# Helpers
# =========================
def md_escape(texto: str) -> str:
    """
    Escapa caracteres conflictivos de Markdown para evitar errores de parseo.
    (Markdown 'normal'; si cambias a MarkdownV2, añade escapes extra)
    """
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

def mostrar_menu(chat_id):
    filas = [[{"text": "📦 Reportar tránsito", "callback_data": "transito"}]]
    send_msg(chat_id, "Menú principal\n\n🛠️ Selecciona una herramienta:", teclado_inline(filas))

def mostrar_llenadoras(chat_id):
    filas = [
        [{"text": "⚙️ M1", "callback_data": "llenadora_M1"},
         {"text": "⚙️ M2", "callback_data": "llenadora_M2"}],
        [{"text": "⚙️ M3", "callback_data": "llenadora_M3"},
         {"text": "⚙️ Chub", "callback_data": "llenadora_Chub"}],
    ]
    send_msg(chat_id, "Selecciona la llenadora:", teclado_inline(filas))

def mostrar_teclado_pin(chat_id, cantidad):
    filas = [[
        {"text": "🔩 Pin Pequeño", "callback_data": "pin_pequeño"},
        {"text": "🔩 Pin Grande",  "callback_data": "pin_grande"},
    ]]
    send_msg(chat_id, f"✅ Canastas: {cantidad}\n\n🔧 Selecciona el tamaño del pin:", teclado_inline(filas))

def mostrar_teclado_otro_lote(chat_id, extra_texto=""):
    filas = [[
        {"text": "✅ Sí", "callback_data": "otro_si"},
        {"text": "❌ No", "callback_data": "otro_no"},
    ]]
    txt = "➕ ¿Deseas agregar otro lote?"
    if extra_texto:
        txt = extra_texto + "\n\n" + txt
    send_msg(chat_id, txt, teclado_inline(filas))

def productos_por_llenadora(llenadora):
    base = [
        {"text": "FND", "callback_data": "producto_FND"},
        {"text": "FRD", "callback_data": "producto_FRD"},
        {"text": "FRS", "callback_data": "producto_FRS"},
        {"text": "FNA", "callback_data": "producto_FNA"},
        {"text": "FNP", "callback_data": "producto_FNP"},
        {"text": "FRP", "callback_data": "producto_FRP"},
    ]
    if llenadora in ("M1", "Chub"):
        base += [
            {"text": "FNE", "callback_data": "producto_FNE"},
            {"text": "FRE", "callback_data": "producto_FRE"},
        ]
    # 2 columnas
    filas = [base[i:i+2] for i in range(0, len(base), 2)]
    return teclado_inline(filas)

def teclado_medidas():
    medidas = ["4oz", "8oz", "14oz", "16oz", "28oz", "35oz", "40oz", "80oz"]
    filas = [[{"text": m, "callback_data": f"medida_{m}"} for m in medidas[i:i+2]] for i in range(0, len(medidas), 2)]
    return teclado_inline(filas)

def guardar_json_resumen(resumen_dict):
    """Guarda el resumen crudo en un archivo .json con timestamp (local)."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"resumen_turno_{ts}.json"
    try:
        with open(nombre, "w", encoding="utf-8") as f:
            json.dump(resumen_dict, f, ensure_ascii=False, indent=2)
        return nombre
    except Exception as e:
        return None

def formatear_num(n):
    # Muestra enteros sin decimal; fracciones con 1 decimal
    if isinstance(n, float) and not n.is_integer():
        return f"{n:.1f}"
    return str(int(n))

# =========================
# Lógica principal
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

                # Mensajes de texto
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    texto = (message.get("text") or "").strip()
                    estado = estados_usuarios.get(chat_id)

                    if texto in ("/start", "/menu"):
                        mostrar_menu(chat_id)
                        continue

                    # Paso de ingreso de cantidad
                    if estado and estado.get("paso") == "cantidad":
                        try:
                            cantidad = int(texto)
                            if cantidad <= 0:
                                raise ValueError
                            estado["canastas"] = cantidad
                            llenadora = estado.get("llenadora")

                            if llenadora == "Chub":
                                estado["pin"] = "único"
                                estado["paso"] = "otro_lote"
                                mostrar_teclado_otro_lote(chat_id, f"✅ Canastas: {cantidad}\nPin asignado automáticamente: único 🔩")
                            elif llenadora == "M3":
                                estado["pin"] = "grande"
                                estado["paso"] = "otro_lote"
                                mostrar_teclado_otro_lote(chat_id, f"✅ Canastas: {cantidad}\nPin asignado automáticamente: grande 🔩")
                            else:
                                estado["paso"] = "pin"
                                mostrar_teclado_pin(chat_id, cantidad)
                        except ValueError:
                            send_msg(chat_id, "❗ Ingresa un número válido de canastas (entero positivo).", parse_mode=None)

                # Callbacks (botones)
                elif "callback_query" in update:
                    cq = update["callback_query"]
                    callback_data = cq["data"]
                    chat_id = cq["message"]["chat"]["id"]
                    message_id = cq["message"]["message_id"]
                    estado = estados_usuarios.get(chat_id)
                    answer_callback(cq["id"])

                    # Inicio flujo tránsito
                    if callback_data == "transito":
                        estados_usuarios[chat_id] = {"paso": "llenadora", "reportes": []}
                        mostrar_llenadoras(chat_id)

                    # Llenadora seleccionada
                    elif callback_data.startswith("llenadora_"):
                        llenadora = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "llenadora":
                            estado["llenadora"] = llenadora
                            if llenadora == "Chub":
                                # Chub: medida fija, mercado RTCA
                                estado["medida"] = "4lbs"
                                estado["mercado"] = "RTCA"
                                estado["paso"] = "producto"
                                send_msg(chat_id, f"✅ Llenadora: {llenadora}\n📏 Medida: 4lbs\n🌎 Mercado asignado: RTCA\n\n🍲 Selecciona el tipo de producto:", productos_por_llenadora(llenadora))
                            else:
                                estado["paso"] = "medida"
                                send_msg(chat_id, f"✅ Llenadora: {llenadora}\n\n📏 ¿Qué medida estás trabajando?", teclado_medidas())

                    # Medida seleccionada
                    elif callback_data.startswith("medida_"):
                        medida = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "medida":
                            estado["medida"] = medida
                            estado["paso"] = "producto"
                            llenadora = estado.get("llenadora")
                            send_msg(chat_id, f"✅ Medida: {medida}\n\n🍲 Selecciona el tipo de producto:", productos_por_llenadora(llenadora))

                    # Producto seleccionado
                    elif callback_data.startswith("producto_"):
                        producto = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "producto":
                            estado["producto"] = producto
                            llenadora = estado.get("llenadora")

                            if llenadora == "Chub":
                                # Ya se asignó RTCA arriba
                                estado["paso"] = "cantidad"
                                send_msg(chat_id, f"✅ Producto: {producto}\n\n🔢 ¿Cuántas canastas se reportaron?")
                            else:
                                estado["paso"] = "mercado"
                                filas = [[
                                    {"text": "RTCA 🇬🇹", "callback_data": "mercado_RTCA"},
                                    {"text": "FDA 🇺🇸",  "callback_data": "mercado_FDA"},
                                ]]
                                send_msg(chat_id, f"✅ Producto: {producto}\n\n🌎 Selecciona el mercado:", teclado_inline(filas))

                    # Mercado seleccionado
                    elif callback_data.startswith("mercado_"):
                        mercado = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "mercado":
                            estado["mercado"] = mercado
                            estado["paso"] = "cantidad"
                            send_msg(chat_id, f"✅ Mercado: {mercado}\n\n🔢 ¿Cuántas canastas se reportaron?", parse_mode=None)

                    # Pin seleccionado manualmente
                    elif callback_data.startswith("pin_"):
                        pin = callback_data.split("_", 1)[1]
                        if estado and estado.get("paso") == "pin":
                            estado["pin"] = pin
                            estado["paso"] = "otro_lote"
                            mostrar_teclado_otro_lote(chat_id, f"✅ Pin: {pin}")

                    # Otro lote / finalizar
                    elif callback_data.startswith("otro_"):
                        if estado and estado.get("paso") in ("otro_lote", "cantidad", "pin"):
                            # Verificamos que todo esté completo
                            requerido = ("llenadora", "medida", "producto", "mercado", "canastas", "pin")
                            faltantes = [k for k in requerido if k not in estado]
                            if faltantes:
                                send_msg(chat_id, f"❗ Faltan datos: {', '.join(faltantes)}.\nVuelve a intentar el lote.", parse_mode=None)
                                estados_usuarios.pop(chat_id, None)
                                continue

                            # Acumular lote
                            estado["reportes"].append({
                                "llenadora": estado["llenadora"],
                                "medida":    estado["medida"],
                                "producto":  estado["producto"],
                                "mercado":   estado["mercado"],
                                "canastas":  int(estado["canastas"]),
                                "pin":       estado["pin"],
                            })

                            if callback_data == "otro_si":
                                # Reset para nuevo lote
                                estado.update({
                                    "paso": "llenadora"
                                })
                                for k in ("medida", "producto", "mercado", "canastas", "pin"):
                                    estado.pop(k, None)
                                mostrar_llenadoras(chat_id)
                            else:
                                # FIN: generar resumen elegante, guardar JSON y preguntar envío a grupo
                                resumen = estado["reportes"]
                                texto, resumen_crudo = construir_resumen_elegante(resumen)
                                send_msg(chat_id, texto, parse_mode="Markdown")

                                # Guardar JSON crudo
                                archivo = guardar_json_resumen(resumen_crudo)
                                if archivo:
                                    send_msg(chat_id, f"🧾 Resumen crudo guardado en `{archivo}`", parse_mode="Markdown")
                                else:
                                    send_msg(chat_id, "⚠️ No se pudo guardar el archivo JSON.", parse_mode=None)

                                # Preguntar envío a grupo
                                filas = [[
                                    {"text": "📣 Enviar al grupo", "callback_data": "enviar_grupo_si"},
                                    {"text": "Omitir",            "callback_data": "enviar_grupo_no"},
                                ]]
                                send_msg(chat_id, "¿Deseas enviar el resumen al grupo de Telegram?", teclado_inline(filas))
                                estado["paso"] = "enviar_grupo"

                    # Envío a grupo
                    elif callback_data.startswith("enviar_grupo_"):
                        if estado and estado.get("paso") == "enviar_grupo":
                            if callback_data == "enviar_grupo_si":
                                texto, _ = construir_resumen_elegante(estado["reportes"])
                                send_msg(GROUP_ID, texto, parse_mode="Markdown")
                                send_msg(chat_id, "✅ Enviado al grupo.")
                            else:
                                send_msg(chat_id, "Hecho. No se envió al grupo.")
                            estados_usuarios.pop(chat_id, None)

        except Exception as e:
            print("❗ Error:", e)
            time.sleep(2)

# =========================
# Resumen elegante
# =========================
def construir_resumen_elegante(reportes):
    """
    Devuelve (texto_markdown, resumen_crudo_dict)
    Agrupa por llenadora y calcula totales por lote, por llenadora y generales.
    """
    # Totales por llenadora y general
    por_llenadora = {}
    total_cajas = 0.0
    total_canastas = 0

    # Cuerpo por lotes
    lineas = ["✅ *Resumen del turno:*"]
    for idx, r in enumerate(reportes, 1):
        llenadora = r["llenadora"]
        medida    = r["medida"]
        producto  = r["producto"]
        mercado   = r["mercado"]
        canastas  = int(r["canastas"])
        pin       = r["pin"]

        por_pin = CAJAS_POR_CANASTA.get(medida, {}).get(pin, 0)
        cajas = canastas * por_pin

        # Acumular
        d = por_llenadora.setdefault(llenadora, {"cajas": 0.0, "canastas": 0, "lotes": []})
        d["cajas"] += cajas
        d["canastas"] += canastas
        d["lotes"].append(r)

        total_cajas += cajas
        total_canastas += canastas

        cajas_fmt = formatear_num(cajas)
        por_pin_fmt = formatear_num(por_pin)
        lineas.append(
            f"\n📦 *Lote {idx}*\n"
            f"🔹 Llenadora: {md_escape(llenadora)}\n"
            f"📏 Medida: {md_escape(medida)}\n"
            f"🍲 Producto: {md_escape(producto)}\n"
            f"🌎 Mercado: {md_escape(mercado)}\n"
            f"🧺 Canastas: {canastas} | 🔩 Pin: {md_escape(pin)}\n"
            f"📦 Cajas: *{cajas_fmt}* (≈ {por_pin_fmt} x canasta)"
        )

    # Bloques por llenadora
    lineas.append("\n— — —")
    lineas.append("*Totales por llenadora*:")
    for ll, d in por_llenadora.items():
        lineas.append(
            f"• {md_escape(ll)} → 🧺 {d['canastas']} canastas | 📦 {formatear_num(d['cajas'])} cajas"
        )

    # Totales generales
    lineas.append("\n*Totales generales:*")
    lineas.append(f"🧺 Canastas: *{total_canastas}*")
    lineas.append(f"📦 Cajas: *{formatear_num(total_cajas)}*")

    texto = "\n".join(lineas)

    # Resumen crudo para JSON
    resumen_crudo = {
        "timestamp": datetime.datetime.now().isoformat(),
        "totales": {
            "canastas": total_canastas,
            "cajas": total_cajas,
        },
        "por_llenadora": {
            ll: {"canastas": d["canastas"], "cajas": d["cajas"], "lotes": d["lotes"]}
            for ll, d in por_llenadora.items()
        },
        "lotes": reportes,
    }
    return texto, resumen_crudo

# =========================
# Main
# =========================
if __name__ == "__main__":
    if TOKEN_TELEGRAM.startswith("REEMPLAZA_") or not TOKEN_TELEGRAM:
        print("⚠️ Define la variable de entorno BOT_TOKEN antes de ejecutar en producción.")
    print("Bot de tránsito activo 🚀 (long-polling)")
    revisar_mensajes()

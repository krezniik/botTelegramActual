import os
import requests
from flask import Flask, request

app = Flask(__name__)

TOKEN_TELEGRAM = os.getenv("BOT_TOKEN")
if not TOKEN_TELEGRAM:
    raise ValueError("La variable de entorno BOT_TOKEN no está definida")


API_URL = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}"
estados_usuarios = {}

@app.route("/")
def index():
    return "Bot de tránsito activo 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    print(update)

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        texto = message.get("text", "").strip()
        estado = estados_usuarios.get(chat_id)

        if texto == "/menu":
            mostrar_menu(chat_id)

        elif estado and estado["paso"] == "cantidad":
            try:
                cantidad = int(texto)
                estado["canastas"] = cantidad
                llenadora = estado.get("llenadora")

                if llenadora == "Chub":
                    estado["pin"] = "único"
                    estado["paso"] = "otro_lote"
                elif llenadora == "M3":
                    estado["pin"] = "grande"
                    estado["paso"] = "otro_lote"
                else:
                    estado["paso"] = "pin"

                if estado["paso"] == "pin":
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "🔩 Pin Pequeño", "callback_data": "pin_pequeño"},
                             {"text": "🔩 Pin Grande", "callback_data": "pin_grande"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Canastas: {cantidad}\n\n🔧 Selecciona el tamaño del pin:",
                        "reply_markup": teclado
                    })
                else:
                    pin_texto = estado["pin"]
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "✅ Sí", "callback_data": "otro_si"},
                             {"text": "❌ No", "callback_data": "otro_no"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Canastas: {cantidad}\n\nPin asignado automáticamente: {pin_texto} 🔩\n\n➕ ¿Deseas agregar otro lote?",
                        "reply_markup": teclado
                    })

            except ValueError:
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "❗ Ingresa un número válido de canastas."
                })

    elif "callback_query" in update:
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        callback_data = update["callback_query"]["data"]
        estado = estados_usuarios.get(chat_id)

        if callback_data == "transito":
            estados_usuarios[chat_id] = {
                "paso": "llenadora",
                "reportes": []
            }
            mostrar_llenadoras(chat_id)

        elif callback_data.startswith("llenadora_"):
            llenadora = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "llenadora":
                estado["llenadora"] = llenadora

                if llenadora == "Chub":
                    estado["medida"] = "4lbs"
                    estado["paso"] = "producto"
                    productos = [
                        {"text": "FNE", "callback_data": "producto_FNE"},
                        {"text": "FRE", "callback_data": "producto_FRE"}
                    ]
                    teclado = {"inline_keyboard": [[p] for p in productos]}
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "🍲 Selecciona el tipo de producto:",
                        "reply_markup": teclado
                    })
                else:
                    estado["paso"] = "medida"
                    medidas = ["4oz", "8oz", "14oz", "16oz", "28oz", "35oz", "40oz", "80oz"]
                    teclado_medidas = {
                        "inline_keyboard": [
                            [{"text": medida, "callback_data": f"medida_{medida}"} for medida in medidas[i:i+2]]
                            for i in range(0, len(medidas), 2)
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Llenadora: {llenadora}\n\n📏 ¿Qué medida estás trabajando?",
                        "reply_markup": teclado_medidas
                    })

        elif callback_data.startswith("medida_"):
            medida = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "medida":
                estado["medida"] = medida
                estado["paso"] = "producto"
                llenadora = estado.get("llenadora")

                productos = [
                    {"text": "FND", "callback_data": "producto_FND"},
                    {"text": "FRD", "callback_data": "producto_FRD"},
                    {"text": "FRD Seda", "callback_data": "producto_FRS"},
                    {"text": "FND Arreglados", "callback_data": "producto_FNA"},
                    {"text": "FND Picante Medio", "callback_data": "producto_FNP"},
                    {"text": "FRD Picante Medio", "callback_data": "producto_FRP"}
                ]

                if llenadora in ["M1", "Chub"]:
                    productos.append({"text": "FND Entero", "callback_data": "producto_FNE"})
                    productos.append({"text": "FRD Entero", "callback_data": "producto_FRE"})

                teclado_productos = {
                    "inline_keyboard": [productos[i:i+2] for i in range(0, len(productos), 2)]
                }

                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Medida: {medida}\n\n🍲 Selecciona el tipo de producto:",
                    "reply_markup": teclado_productos
                })

        elif callback_data.startswith("producto_"):
            producto = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "producto":
                estado["producto"] = producto
                llenadora = estado.get("llenadora")

                if llenadora == "Chub":
                    estado["mercado"] = "RTCA"
                    estado["paso"] = "cantidad"
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Producto: {producto}\n🌎 Mercado asignado automáticamente: RTCA\n\n🔢 ¿Cuántas canastas se reportaron?"
                    })
                else:
                    estado["paso"] = "mercado"
                    teclado = {
                        "inline_keyboard": [
                            [{"text": "RTCA 🇬🇹", "callback_data": "mercado_RTCA"},
                             {"text": "FDA 🇺🇸", "callback_data": "mercado_FDA"}]
                        ]
                    }
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"✅ Producto: {producto}\n\n🌎 Selecciona el mercado:",
                        "reply_markup": teclado
                    })

        elif callback_data.startswith("mercado_"):
            mercado = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "mercado":
                estado["mercado"] = mercado
                estado["paso"] = "cantidad"
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Mercado: {mercado}\n\n🔢 ¿Cuántas canastas se reportaron?"
                })

        elif callback_data.startswith("pin_"):
            pin = callback_data.split("_", 1)[1]
            if estado and estado["paso"] == "pin":
                estado["pin"] = pin
                estado["paso"] = "otro_lote"
                teclado = {
                    "inline_keyboard": [
                        [{"text": "✅ Sí", "callback_data": "otro_si"},
                         {"text": "❌ No", "callback_data": "otro_no"}]
                    ]
                }
                requests.post(f"{API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Pin: {pin}\n\n➕ ¿Deseas agregar otro lote?",
                    "reply_markup": teclado
                })

        elif callback_data.startswith("otro_"):
            if estado:
                cajas_por_canasta = {
                    "4oz": {"grande": 0, "pequeño": 110},
                    "8oz": {"grande": 68, "pequeño": 93.5},
                    "14oz": {"grande": 80, "pequeño": 110},
                    "16oz": {"grande": 0, "pequeño": 165},
                    "28oz": {"grande": 58, "pequeño": 0},
                    "35oz": {"grande": 53, "pequeño": 0},
                    "40oz": {"grande": 48, "pequeño": 0},
                    "80oz": {"grande": 53, "pequeño": 0},
                    "4lbs": {"único": 81}
                }

                estado["reportes"].append({
                    "llenadora": estado["llenadora"],
                    "medida": estado["medida"],
                    "producto": estado["producto"],
                    "mercado": estado["mercado"],
                    "canastas": estado["canastas"],
                    "pin": estado["pin"]
                })

                if callback_data == "otro_si":
                    estado["paso"] = "llenadora"
                    mostrar_llenadoras(chat_id)
                else:
                    texto = "✅ *Resumen del turno:*\n"
                    for idx, r in enumerate(estado["reportes"], 1):
                        medida = r["medida"]
                        pin = r["pin"]
                        canastas = int(r["canastas"])
                        cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                        cajas = canastas * cajas_por_pin
                        texto += (
                            f"\n*Lote {idx}*\n"
                            f"⚙️ Llenadora: {r['llenadora']}\n"
                            f"📏 Medida: {medida}\n"
                            f"🍲 Producto: {r['producto']}\n"
                            f"🌎 Mercado: {r['mercado']}\n"
                            f"🧺 Canastas: {canastas} | 🔩 Pin: {pin}\n"
                            f"📦 Cajas: {cajas} (≈ {cajas_por_pin} x canasta)"
                        )

                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": texto,
                        "parse_mode": "Markdown"
                    })

                    # Crear y enviar resumen simple al grupo
                    resumen_simple = "*Tránsito 📋*"
                    for r in estado["reportes"]:
                        producto = r["producto"]
                        medida = r["medida"]
                        mercado = r["mercado"]
                        canastas = int(r["canastas"])
                        pin = r["pin"]
                        cajas_por_pin = cajas_por_canasta.get(medida, {}).get(pin, 0)
                        total_cajas = int(canastas * cajas_por_pin)

                        bandera = "🇬🇹" if mercado == "RTCA" else "🇺🇸"

                        resumen_simple += f"\n\n{producto + " 🫘"} {medida} {mercado} {bandera}\n*{total_cajas:,} cajas* 📦"

                    # Enviar al grupo de Telegram
                    requests.post(f"{API_URL}/sendMessage", json={
                        "chat_id": -1002710248563,
                        "text": resumen_simple,
                        "parse_mode": "Markdown"
                    })
                    
                    estados_usuarios.pop(chat_id)

    return '', 200

def mostrar_menu(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "📦 Reportar tránsito", "callback_data": "transito"}]
        ]
    }
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Menú principal\n\n🛠️ Selecciona una herramienta:",
        "reply_markup": teclado
    })

def mostrar_llenadoras(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "⚙️ M1", "callback_data": "llenadora_M1"},
             {"text": "⚙️ M2", "callback_data": "llenadora_M2"}],
            [{"text": "⚙️ M3", "callback_data": "llenadora_M3"},
             {"text": "⚙️ Chub", "callback_data": "llenadora_Chub"}]
        ]
    }
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Selecciona la llenadora:",
        "reply_markup": teclado
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
